import os
import uuid
import tempfile
import requests  # Make sure requests is imported early
from flask import Flask, request, render_template, jsonify, session, Response
import openai
import re
from dotenv import load_dotenv

"""
Configuration Instructions:
--------------------------
1. Create or modify a .env file in the root directory with the following variables:
   OPENAI_API_KEY="your_openai_api_key"
   CARTESIA_API_KEY="your_cartesia_api_key"

2. If the .env file already exists, add the CARTESIA_API_KEY variable.

3. Cartesia API is used for high-quality text-to-speech (TTS) capabilities.
   If no API key is provided, the app will fall back to browser-based TTS.

4. Restart the application after updating the .env file.
"""

# Load environment variables from .env file
load_dotenv()

# Initialize OpenAI API
openai.api_key = os.getenv("OPENAI_API_KEY")
# Initialize Cartesia API key
CARTESIA_API_KEY = os.getenv("CARTESIA_API_KEY", "")

# Check and log API availability
if not CARTESIA_API_KEY:
    print("WARNING: Cartesia API key not found. Text-to-speech will use browser fallback.")
else:
    print("Cartesia API key loaded successfully.")

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(24).hex())

# Store chat sessions (in-memory for simplicity - would use a database in production)
chat_sessions = {}

@app.route('/')
def index():
    # Generate a unique session ID if not present
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
        # Initialize a new chat session
        chat_sessions[session['session_id']] = {
            'messages': [],
            'current_topic': None,
            'generated_questions': []
        }
    return render_template('index.html')

@app.route('/get-cartesia-key', methods=['GET'])
def get_cartesia_key():
    """Securely provide the Cartesia API key to the authenticated client"""
    # Check if user has a valid session
    if 'session_id' not in session:
        print("Error: /get-cartesia-key accessed without valid session")
        return jsonify({'error': 'Not authenticated'}), 401
        
    # Return the API key if available
    print(f"Returning Cartesia API key to client (first 5 chars): {CARTESIA_API_KEY[:5] if CARTESIA_API_KEY else 'Not set'}")
    if CARTESIA_API_KEY:
        return jsonify({
            'available': True,
            'key': CARTESIA_API_KEY
        })
    else:
        print("Warning: Cartesia API key not available")
        return jsonify({
            'available': False,
            'message': 'Cartesia API key not configured'
        })

@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        user_message = data.get('message', '').strip()
        session_id = session.get('session_id')
        
        # Handle invalid session or empty message
        if not session_id or not user_message:
            return jsonify({'error': 'Invalid session or empty message'}), 400
        
        # Get or initialize session data
        if session_id not in chat_sessions:
            chat_sessions[session_id] = {
                'messages': [],
                'current_topic': None,
                'generated_questions': []
            }
        
        session_data = chat_sessions[session_id]
        
        # Add user message to chat history
        session_data['messages'].append({
            'role': 'user',
            'content': user_message
        })
        
        # Determine the state of conversation and next steps
        if session_data['current_topic'] is None:
            # Initial state: Ask about review topic
            response_message, response_text = handle_topic_identification(user_message, session_data)
        else:
            # Topic already provided: Generate or handle questions
            response_message, response_text = handle_ongoing_conversation(user_message, session_data)
            
        # Add assistant's response to chat history
        session_data['messages'].append(response_message)
        
        return jsonify({
            'response': response_text,
            'questions': session_data.get('generated_questions', []),
            'has_topic': session_data['current_topic'] is not None
        })
        
    except openai.APIError as e:
        # Handle OpenAI API-specific errors
        error_message = f"OpenAI API error: {str(e)}"
        print(error_message)
        return jsonify({'error': 'There was an issue connecting to the AI service. Please try again later.'}), 503
    except openai.RateLimitError as e:
        print(f"OpenAI rate limit error: {str(e)}")
        return jsonify({'error': 'The AI service is currently experiencing high demand. Please try again in a moment.'}), 429
    except Exception as e:
        error_message = f"Error in chat endpoint: {str(e)}"
        print(error_message)
        return jsonify({'error': 'An error occurred processing your message. Please try again or try a different topic.'}), 500

@app.route('/next-question', methods=['POST'])
def next_question():
    try:
        data = request.json
        question_index = data.get('question_index', 0)
        session_id = session.get('session_id')
        
        # Handle invalid session
        if not session_id:
            return jsonify({'error': 'Invalid session'}), 400
        
        # Get session data
        if session_id not in chat_sessions:
            return jsonify({'error': 'Session data not found'}), 404
        
        session_data = chat_sessions[session_id]
        questions = session_data.get('generated_questions', [])
        
        # Make sure we have questions
        if not questions:
            return jsonify({'error': 'No questions available'}), 404
        
        # Get the next question (circular if we reach the end)
        if question_index >= len(questions):
            question_index = 0
        
        next_question = questions[question_index]
        
        # Add the question to the chat history
        session_data['messages'].append({
            'role': 'assistant',
            'content': f"Let's try this question: {next_question}"
        })
        
        return jsonify({
            'question': next_question,
            'index': question_index
        })
        
    except Exception as e:
        print(f"Error in next-question endpoint: {str(e)}")
        return jsonify({'error': 'An error occurred processing your request'}), 500

@app.route('/transcribe', methods=['POST'])
def transcribe_audio():
    """
    Transcribe audio using OpenAI's Whisper model
    Accepts direct audio file upload
    """
    try:
        print("Received transcription request")
        
        # Check if a file was uploaded
        if 'audio_file' not in request.files:
            print("Error: No audio file provided")
            return jsonify({'error': 'No audio file provided', 'success': False}), 400
            
        audio_file = request.files['audio_file']
        
        if audio_file.filename == '':
            print("Error: Empty filename")
            return jsonify({'error': 'No selected file', 'success': False}), 400
            
        # Save the file to a temporary location
        with tempfile.NamedTemporaryFile(suffix='.webm', delete=True) as temp_audio:
            audio_file.save(temp_audio.name)
            print(f"Saved uploaded audio to temporary file: {temp_audio.name}")
            
            # Call OpenAI's Whisper model for transcription
            try:
                with open(temp_audio.name, 'rb') as audio_file:
                    print("Calling OpenAI Whisper API...")
                    transcript = openai.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file,
                        language="en"
                    )
                    
                    print(f"Transcription successful: '{transcript.text}'")
                    
                    # Return the transcribed text
                    return jsonify({
                        'text': transcript.text,
                        'success': True
                    })
            except openai.APIError as e:
                error_msg = f"OpenAI API error during transcription: {str(e)}"
                print(error_msg)
                return jsonify({
                    'error': error_msg,
                    'success': False
                }), 500
            except Exception as e:
                error_msg = f"Error during transcription: {str(e)}"
                print(error_msg)
                return jsonify({
                    'error': error_msg,
                    'success': False
                }), 500
    
    except Exception as e:
        error_msg = f"Error in transcribe_audio: {str(e)}"
        print(error_msg)
        return jsonify({
            'error': error_msg,
            'success': False
        }), 500

@app.route('/test-tts', methods=['GET'])
def test_tts_route():
    """
    Simple test endpoint to verify routing works
    """
    print("Test TTS route accessed")
    return jsonify({
        'message': 'TTS test route works!',
        'success': True
    })

@app.route('/text-to-speech', methods=['POST', 'OPTIONS'])
def text_to_speech():
    """
    Convert text to speech using Cartesia API
    """
    # Handle preflight request for CORS
    if request.method == 'OPTIONS':
        response = jsonify({'success': True})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'POST,OPTIONS')
        return response
        
    try:
        print("Received text-to-speech request")
        print(f"Request content type: {request.content_type}")
        print(f"Request data: {request.data[:100]}")
        
        # Parse the JSON data
        try:
            data = request.json
            if data is None:
                print("Warning: request.json is None, trying to parse manually")
                if request.data:
                    import json
                    data = json.loads(request.data)
                else:
                    print("Error: No request data")
                    return jsonify({'error': 'No data provided'}), 400
                    
            print(f"Parsed data: {data}")
        except Exception as e:
            print(f"Error parsing JSON: {str(e)}")
            return jsonify({'error': f'Invalid JSON: {str(e)}'}), 400
        
        text = data.get('text')
        voice = data.get('voice', 'nova')  # Default voice
        
        if not text:
            print("Error: No text provided")
            return jsonify({'error': 'No text provided'}), 400
            
        if not CARTESIA_API_KEY:
            print("Warning: No Cartesia API key set, returning error")
            return jsonify({'error': 'Cartesia API key not configured'}), 503
            
        print(f"Converting to speech: '{text[:50]}...' (truncated)")
        print(f"Using Cartesia API key: {CARTESIA_API_KEY[:5]}...")
        
        # Call Cartesia API - Use the correct HTTP endpoint
        url = "https://api.cartesia.ai/v1/tts"
        headers = {
            "Authorization": f"Bearer {CARTESIA_API_KEY}",
            "Content-Type": "application/json",
            "Cartesia-Version": "2025-04-16"
        }
        
        # Format the request payload according to the SDK standards
        payload = {
            "modelId": "sonic-2",
            "transcript": text,
            "language": "en",
            "outputFormat": {
                "container": "mp3",
                "sampleRate": 24000,
                "bitRate": 128000
            }
        }
        
        # Add voice configuration in the right format
        if isinstance(voice, str):
            payload["voiceId"] = voice
        else:
            payload["voice"] = voice
        
        print(f"Sending request to Cartesia API: {url}")
        print(f"Headers: {headers}")
        print(f"Payload: {payload}")
        
        try:
            response = requests.post(url, json=payload, headers=headers)
            print(f"Cartesia API response status: {response.status_code}")
            print(f"Cartesia API response headers: {response.headers}")
            
            if response.status_code != 200:
                print(f"Cartesia API error: {response.status_code}, {response.text}")
                return jsonify({
                    'error': f'Cartesia API error: {response.status_code}, {response.text}',
                    'success': False
                }), 500
                
            # Return the audio data as a response with proper content type
            audio_data = response.content
            print(f"Successfully generated audio, size: {len(audio_data)} bytes")
            print(f"Content type from Cartesia: {response.headers.get('Content-Type')}")
            
            # Create a Flask response with the audio data
            flask_response = Response(
                audio_data,
                mimetype="audio/mpeg",
                headers={
                    "Content-Disposition": "attachment; filename=speech.mp3"
                }
            )
            
            # Add CORS headers
            flask_response.headers.add('Access-Control-Allow-Origin', '*')
            return flask_response
            
        except requests.RequestException as e:
            print(f"Cartesia API request error: {str(e)}")
            return jsonify({
                'error': f'Cartesia API request error: {str(e)}',
                'success': False
            }), 500
            
    except Exception as e:
        error_msg = f"Error in text_to_speech: {str(e)}"
        print(error_msg)
        return jsonify({
            'error': error_msg,
            'success': False
        }), 500

def handle_topic_identification(user_message, session_data):
    """
    Handle the initial conversation where we identify what topic the user wants to review.
    Returns the assistant's message object and response text.
    """
    # Use the model to analyze the user's topic
    topic_analysis = analyze_review_topic(user_message)
    session_data['current_topic'] = topic_analysis
    
    # Generate questions for this topic
    questions = generate_active_recall_questions(topic_analysis)
    session_data['generated_questions'] = questions
    
    if not questions:
        response_text = f"I'm having trouble generating questions about {topic_analysis}. Could you provide more details about what specific aspects you'd like to review?"
    else:
        # Select first question to start with
        first_question = questions[0]
        
        response_text = f"Great! I'll help you review {topic_analysis} using active recall. I've prepared several questions to test your knowledge.\n\nLet's start with this question: {first_question}\n\nTry to answer it as thoroughly as you can!"
    
    response_message = {
        'role': 'assistant',
        'content': response_text
    }
    
    return response_message, response_text

def handle_ongoing_conversation(user_message, session_data):
    """
    Handle the ongoing conversation after a topic has been identified.
    This could be feedback on questions, requests for hints, or new topic requests.
    """
    # Analyze if the user wants to change the topic
    if is_new_topic_request(user_message):
        # Reset the conversation to start a new topic
        new_topic = extract_new_topic(user_message)
        session_data['current_topic'] = new_topic
        
        # Generate new questions
        questions = generate_active_recall_questions(new_topic)
        session_data['generated_questions'] = questions
        
        response_text = f"Switching to {new_topic}. I've prepared new active recall questions for you to practice with."
    elif "hint" in user_message.lower() or "help" in user_message.lower():
        # The user is asking for a hint
        response_text = generate_hint(user_message, session_data)
    else:
        # Provide feedback on the user's answer to a question
        response_text = generate_feedback_or_hint(user_message, session_data)
    
    response_message = {
        'role': 'assistant',
        'content': response_text
    }
    
    return response_message, response_text

def analyze_review_topic(user_input):
    """
    Use the model to analyze what topic the user wants to review.
    """
    try:
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an educational assistant helping identify study topics."},
                {"role": "user", "content": f"I want to review and practice active recall for this topic: '{user_input}'. Please identify the specific academic subject/topic I want to review, and respond with ONLY the name of that topic. Don't include prefixes, explanations, or any other text."}
            ],
            temperature=0.3,
            max_tokens=50
        )
        
        # Extract the topic
        topic = response.choices[0].message.content.strip()
        return topic
    except Exception as e:
        print(f"Error in analyze_review_topic: {str(e)}")
        # Fallback to using the raw user input as the topic
        return user_input.strip()

def generate_active_recall_questions(topic):
    """
    Generate active recall questions for a specific topic.
    """
    try:
        enhanced_prompt = create_topic_based_prompt(topic)
        
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an expert educator specialized in creating effective active recall questions to promote deep learning and retention."},
                {"role": "user", "content": enhanced_prompt}
            ],
            temperature=0.7,
            max_tokens=1000
        )
        
        # Extract and process questions from the response
        result = response.choices[0].message.content.strip()
        
        # Parse and clean questions
        questions = parse_and_validate_questions(result)
        return questions
    except Exception as e:
        print(f"Error in generate_active_recall_questions: {str(e)}")
        # Return a default question as fallback
        return [f"Can you explain the key concepts of {topic}?"]

def create_topic_based_prompt(topic):
    """
    Create a prompt for generating active recall questions on a specific topic.
    """
    return f"""
I need you to create high-quality active recall questions based on the topic of {topic}.

## What is Active Recall?
Active recall is a principle of effective learning where answering questions forces the retrieval of information from memory, strengthening neural connections and improving long-term retention. Unlike recognition questions, active recall questions require retrieving specific information without being presented with options.

## Guidelines for Creating Active Recall Questions:
1. SPECIFICITY: Focus on specific facts, concepts, mechanisms, and relationships within the topic of {topic}.
2. RETRIEVAL FOCUS: Questions should require retrieving information from memory, not just recognizing it.
3. DIVERSE FORMATS: Include different question types:
   - Definition/explanation questions ("What is...?" "Explain the concept of...")
   - Process/mechanism questions ("How does...?" "Describe the process of...")
   - Compare/contrast questions ("What's the difference between...?")
   - Application questions ("How would you apply...?")
   - Cause/effect questions ("What happens when...?" "What causes...?")
4. COMPLEXITY: Include questions with varying levels of difficulty - from basic recall to more complex application.

## Examples of Good Active Recall Questions:
- "What are the three key components of {topic}?"
- "Explain the mechanism by which [related process] works in {topic}."
- "What are the primary differences between [related concept A] and [related concept B] in {topic}?"

## Examples of Poor Questions to Avoid:
- Questions that are too general ("What is {topic}?")
- Yes/no questions that don't require detailed recall
- Questions answerable without understanding the material

## Instructions:
Generate 10 active recall questions about {topic}. Format each question as a numbered list (1., 2., etc.). Make sure the questions cover different aspects and difficulty levels.
"""

def parse_and_validate_questions(raw_questions):
    """
    Parse the raw questions output and validate that they are 
    properly formatted and useful active recall questions.
    """
    # Initial parsing of numbered questions
    questions = re.findall(r'\d+[\.\)]\s*(.*?)(?=\n\d+[\.\)]|$)', raw_questions, re.DOTALL)
    
    # Clean up and validate each question
    validated_questions = []
    for q in questions:
        # Remove any trailing newlines and extra whitespace
        cleaned = q.strip()
        if cleaned and is_valid_question(cleaned):
            validated_questions.append(cleaned)
    
    # If proper questions were found, return them
    if validated_questions:
        return validated_questions
    
    # Fallback: look for questions by line and question marks
    fallback_questions = []
    for line in raw_questions.split('\n'):
        line = line.strip()
        # Check if it looks like a question (has question mark and reasonable length)
        if '?' in line and len(line) > 15:
            fallback_questions.append(line)
    
    if fallback_questions:
        return fallback_questions[:10]  # Limit to 10 questions
    
    # Last resort: return error message if no questions could be parsed
    return ["Could not generate valid active recall questions. Please try again with a different topic."]

def is_valid_question(question_text):
    """
    Validate if a question is a proper active recall question.
    """
    # Basic validation rules
    if len(question_text) < 15:  # Too short to be meaningful
        return False
    
    # Check for question structure (either has ? or starts with common question words)
    question_markers = ['?', 'what', 'how', 'why', 'describe', 'explain', 'define', 'identify', 'list', 'compare']
    has_marker = '?' in question_text.lower() or any(question_text.lower().startswith(marker) for marker in question_markers)
    
    return has_marker

def is_new_topic_request(message):
    """
    Determine if the user is requesting to change the topic.
    """
    message_lower = message.lower()
    topic_change_phrases = [
        "new topic", "different topic", "change topic", "another topic", 
        "change subject", "new subject", "different subject", "another subject",
        "let's talk about", "can we discuss", "i want to learn about", "i want to review",
        "switch to", "change to", "instead of"
    ]
    
    return any(phrase in message_lower for phrase in topic_change_phrases)

def extract_new_topic(message):
    """
    Extract the new topic from a topic change request.
    """
    try:
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an educational assistant helping identify study topics."},
                {"role": "user", "content": f"The user has indicated they want to change topics with this message: '{message}'. Please identify the specific new academic subject/topic they want to review, and respond with ONLY the name of that topic. Don't include prefixes, explanations, or any other text."}
            ],
            temperature=0.3,
            max_tokens=50
        )
        
        # Extract the topic
        topic = response.choices[0].message.content.strip()
        return topic
    except Exception as e:
        print(f"Error in extract_new_topic: {str(e)}")
        # Fallback to extracting topic directly from message
        # Remove common phrases that indicate topic change
        clean_message = message.lower()
        for phrase in ["let's talk about", "can we discuss", "i want to learn about", "i want to review",
                      "switch to", "change to", "instead of", "new topic", "different topic"]:
            clean_message = clean_message.replace(phrase, "")
        return clean_message.strip()

def generate_feedback_or_hint(user_message, session_data):
    """
    Generate feedback on the user's answer or provide a hint.
    """
    topic = session_data['current_topic']
    questions = session_data['generated_questions']
    chat_history = session_data['messages']
    
    try:
        # Find the last question discussed or most relevant question
        relevant_question = identify_relevant_question(chat_history, questions)
        
        # Construct a prompt that includes the context
        context_messages = chat_history[-6:] if len(chat_history) >= 6 else chat_history
        context_prompt = "\n".join([
            f"{'User' if msg['role'] == 'user' else 'Assistant'}: {msg['content']}" 
            for msg in context_messages if msg['role'] in ['user', 'assistant']
        ])
        
        system_prompt = f"""You are an expert educational assistant helping a student with active recall on the topic of {topic}. 
The student has been asked this question: "{relevant_question or 'a question about ' + topic}"
They've provided an answer attempt. Your job is to:
1. Determine if their answer is correct, partially correct, or incorrect
2. Provide specific, constructive feedback highlighting what they got right and wrong
3. Give encouragement and advice on how to improve their understanding
4. Be concise but educational in your response (max 2-3 sentences)"""
        
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Topic: {topic}\n\nRecent conversation:\n{context_prompt}\n\nThe user's most recent response: \"{user_message}\"\n\nProvide specific, helpful feedback on their answer."}
            ],
            temperature=0.7,
            max_tokens=200
        )
        
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error in generate_feedback_or_hint: {str(e)}")
        # Provide a generic response as fallback
        return "I see your thoughts on this. Can you elaborate more on your understanding of the key concepts involved?"

def identify_relevant_question(chat_history, questions):
    """
    Analyze the chat history to identify which question the user is likely answering.
    """
    if not questions:
        return None
    
    # Look for the most recent question mentioned in the chat
    for msg in reversed(chat_history):
        if msg['role'] == 'assistant':
            content = msg['content'].lower()
            for question in questions:
                # Check if this question (or part of it) appears in the message
                question_start = question.split('?')[0][:30].lower()  # Take the first part before a question mark
                if question_start in content:
                    return question
    
    # If we can't identify a specific question, return the first one
    return questions[0] if questions else None

def generate_hint(user_message, session_data):
    """
    Generate a hint for the user when they're stuck on a question.
    """
    topic = session_data['current_topic']
    questions = session_data['generated_questions']
    chat_history = session_data['messages']
    
    try:
        # Construct a prompt that includes the context
        context_prompt = "\n".join([
            f"Message: {msg['content']}" 
            for msg in chat_history[-6:] if msg['role'] == 'user' or msg['role'] == 'assistant'
        ])
        
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": f"You are an educational assistant helping a student review {topic}. The student is asking for a hint about a question. Provide a helpful hint that guides them without giving away the full answer."},
                {"role": "user", "content": f"Topic being reviewed: {topic}\n\nRecent conversation:\n{context_prompt}\n\nThe user is asking for a hint. Provide a helpful clue that will guide them toward figuring out the answer on their own."}
            ],
            temperature=0.7,
            max_tokens=150
        )
        
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error in generate_hint: {str(e)}")
        # Provide a generic hint as fallback
        return "Think about the key concepts we've discussed so far. What fundamental principles might apply here?"

if __name__ == '__main__':
    # Check if OpenAI API key is set
    if not openai.api_key:
        print("ERROR: OpenAI API key is not set. Please add it to your .env file.")
    else:
        print(f"OpenAI API key loaded successfully (first 5 chars): {openai.api_key[:5]}...")
        
    # Check if Cartesia API key is set
    if not CARTESIA_API_KEY:
        print("WARNING: Cartesia API key is not set. Text-to-speech will use fallback method.")
    else:
        print(f"Cartesia API key loaded successfully (first 5 chars): {CARTESIA_API_KEY[:5]}...")
    
    # Check if SSL certificate files exist
    cert_file = 'localhost+1.pem'
    key_file = 'localhost+1-key.pem'
    ssl_files_exist = os.path.exists(cert_file) and os.path.exists(key_file)
    
    if not ssl_files_exist:
        print(f"WARNING: SSL certificate files not found ({cert_file} and/or {key_file}).")
        print("Running without SSL. This may cause issues with microphone access.")
        app.run(debug=True, host='localhost', port=5001)
    else:
        print(f"SSL certificate files found. Running with HTTPS enabled.")
        app.run(debug=True, host='localhost', port=5001, ssl_context=(cert_file, key_file)) 