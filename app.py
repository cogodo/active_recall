import os
import uuid
import tempfile
import requests  # Make sure requests is imported early
from flask import Flask, request, render_template, jsonify, session, Response, redirect, url_for
import openai
import re
from dotenv import load_dotenv
import time
import json
from flask_socketio import SocketIO, emit, disconnect
import functools

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

# Initialize SocketIO with Flask app
socketio = SocketIO(app, cors_allowed_origins="*")

# Authenticated socket sessions
socket_sessions = {}

def authenticated_only(f):
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        if request.sid not in socket_sessions:
            disconnect()
            return False
        return f(*args, **kwargs)
    return wrapped

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    print(f"Client connected: {request.sid}")
    emit('connection_status', {'status': 'connected', 'sid': request.sid})

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    print(f"Client disconnected: {request.sid}")
    if request.sid in socket_sessions:
        print(f"Removing authenticated session for {request.sid}")
        del socket_sessions[request.sid]

@socketio.on('authenticate')
def handle_authentication(data):
    """Handle client authentication"""
    try:
        print(f"Authentication attempt from {request.sid}")
        token = data.get('token')
        session_id = data.get('session_id')
        
        if not token or not session_id:
            emit('authentication_status', {
                'status': 'error',
                'message': 'Missing token or session_id'
            })
            return
            
        # Verify token and session
        if session_id in chat_sessions and 'websocket_tokens' in chat_sessions[session_id]:
            tokens = chat_sessions[session_id]['websocket_tokens']
            
            if token in tokens:
                token_data = tokens[token]
                
                # Check token expiry
                if token_data['expires_at'] < time.time():
                    emit('authentication_status', {
                        'status': 'error',
                        'message': 'Token expired'
                    })
                    return
                    
                # Store authenticated session
                socket_sessions[request.sid] = {
                    'session_id': session_id,
                    'authenticated_at': time.time(),
                    'token': token,
                    'type': token_data['type']
                }
                
                print(f"Client {request.sid} authenticated for session {session_id}")
                
                # Success response
                emit('authentication_status', {
                    'status': 'success',
                    'message': 'Authenticated successfully',
                    'session_id': session_id
                })
                
                # Join room for this session
                from flask_socketio import join_room
                join_room(session_id)
                
                # Send initial state
                emit('ui_state_update', chat_sessions[session_id].get('ui_state', {}))
                
                return
                
        # If we get here, authentication failed
        emit('authentication_status', {
            'status': 'error',
            'message': 'Invalid token or session'
        })
        
    except Exception as e:
        print(f"Error in authentication: {str(e)}")
        emit('authentication_status', {
            'status': 'error',
            'message': f'Authentication error: {str(e)}'
        })

@socketio.on('ui_state_request')
@authenticated_only
def handle_ui_state_request():
    """Send current UI state to client"""
    session_id = socket_sessions[request.sid]['session_id']
    ui_state = chat_sessions[session_id].get('ui_state', {})
    emit('ui_state_update', ui_state)

@socketio.on('tts_status_request')
@authenticated_only
def handle_tts_status_request():
    """Send current TTS status to client"""
    session_id = socket_sessions[request.sid]['session_id']
    
    tts_queue = chat_sessions[session_id].get('tts_queue', [])
    active_tts = chat_sessions[session_id].get('active_tts')
    
    emit('tts_status_update', {
        'queue_length': len(tts_queue),
        'is_playing': active_tts is not None,
        'active': active_tts
    })

@socketio.on('question_state_request')
@authenticated_only
def handle_question_state_request():
    """Send current question state to client"""
    session_id = socket_sessions[request.sid]['session_id']
    
    question_state = chat_sessions[session_id].get('question_state', {})
    questions = chat_sessions[session_id].get('generated_questions', [])
    
    current_index = question_state.get('current_index', 0)
    current_question = questions[current_index] if questions and current_index < len(questions) else None
    
    emit('question_state_update', {
        'question_state': question_state,
        'current_question': current_question,
        'total_questions': len(questions)
    })

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

@app.route('/questions/state', methods=['GET', 'POST'])
def manage_question_state():
    """
    Comprehensive endpoint for managing question state, history, and progress
    """
    try:
        session_id = session.get('session_id')
        if not session_id:
            return jsonify({'error': 'Invalid session'}), 400
            
        # Initialize question state if not present
        if 'question_state' not in chat_sessions.get(session_id, {}):
            chat_sessions[session_id]['question_state'] = {
                'current_index': 0,
                'answered_questions': [],
                'skipped_questions': [],
                'correct_count': 0,
                'partially_correct_count': 0,
                'incorrect_count': 0,
                'last_answer_evaluation': None,
                'mastery_level': 0.0,  # 0.0-1.0 scale
                'question_history': []
            }
        
        question_state = chat_sessions[session_id]['question_state']
        
        # Handle GET request - return current question state
        if request.method == 'GET':
            # Also include the actual questions
            questions = chat_sessions[session_id].get('generated_questions', [])
            current_question = questions[question_state['current_index']] if questions and question_state['current_index'] < len(questions) else None
            
            return jsonify({
                'question_state': question_state,
                'current_question': current_question,
                'questions': questions,
                'total_questions': len(questions),
                'success': True
            })
        
        # Handle POST request - update question state
        if request.method == 'POST':
            data = request.json
            if not data:
                return jsonify({'error': 'No data provided'}), 400
                
            # Handle different actions based on the request
            action = data.get('action', 'update')
            
            if action == 'next':
                # Move to the next question
                questions = chat_sessions[session_id].get('generated_questions', [])
                if not questions:
                    return jsonify({'error': 'No questions available'}), 400
                    
                # Update current index (wrap around if at the end)
                current_index = question_state['current_index']
                new_index = (current_index + 1) % len(questions)
                question_state['current_index'] = new_index
                
                # Get the next question
                next_question = questions[new_index]
                
                # Add to question history
                question_state['question_history'].append({
                    'question_index': new_index,
                    'question': next_question,
                    'timestamp': time.time()
                })
                
                # Add the question to the chat history
                session_data = chat_sessions[session_id]
                session_data['messages'].append({
                    'role': 'assistant',
                    'content': f"Let's try this question: {next_question}"
                })
                
                return jsonify({
                    'question': next_question,
                    'index': new_index,
                    'total': len(questions),
                    'success': True
                })
                
            elif action == 'previous':
                # Move to the previous question
                questions = chat_sessions[session_id].get('generated_questions', [])
                if not questions:
                    return jsonify({'error': 'No questions available'}), 400
                    
                # Update current index (wrap around if at the beginning)
                current_index = question_state['current_index']
                new_index = (current_index - 1) % len(questions)
                question_state['current_index'] = new_index
                
                # Get the previous question
                prev_question = questions[new_index]
                
                # Add to question history
                question_state['question_history'].append({
                    'question_index': new_index,
                    'question': prev_question,
                    'timestamp': time.time()
                })
                
                # Add the question to the chat history
                session_data = chat_sessions[session_id]
                session_data['messages'].append({
                    'role': 'assistant',
                    'content': f"Let's go back to this question: {prev_question}"
                })
                
                return jsonify({
                    'question': prev_question,
                    'index': new_index,
                    'total': len(questions),
                    'success': True
                })
                
            elif action == 'evaluate':
                # Evaluate an answer
                answer = data.get('answer')
                if not answer:
                    return jsonify({'error': 'No answer provided'}), 400
                    
                questions = chat_sessions[session_id].get('generated_questions', [])
                if not questions:
                    return jsonify({'error': 'No questions available'}), 400
                    
                current_index = question_state['current_index']
                if current_index >= len(questions):
                    return jsonify({'error': 'Invalid question index'}), 400
                    
                current_question = questions[current_index]
                
                # Generate feedback using AI
                session_data = chat_sessions[session_id]
                feedback = generate_feedback_or_hint(answer, session_data)
                
                # Analyze the feedback to determine correctness (this could be made more sophisticated)
                evaluation = 'incorrect'
                if 'correct' in feedback.lower() and not ('not correct' in feedback.lower() or 'incorrect' in feedback.lower()):
                    evaluation = 'correct'
                    question_state['correct_count'] += 1
                elif 'partially' in feedback.lower() or 'partly' in feedback.lower():
                    evaluation = 'partially_correct'
                    question_state['partially_correct_count'] += 1
                else:
                    question_state['incorrect_count'] += 1
                
                # Update question state
                question_state['last_answer_evaluation'] = {
                    'question': current_question,
                    'answer': answer,
                    'feedback': feedback,
                    'evaluation': evaluation,
                    'timestamp': time.time()
                }
                
                # Add to appropriate lists
                if evaluation == 'correct':
                    if current_question not in question_state['answered_questions']:
                        question_state['answered_questions'].append(current_question)
                
                # Update mastery level calculation
                total_answers = question_state['correct_count'] + question_state['partially_correct_count'] + question_state['incorrect_count']
                if total_answers > 0:
                    # Weighted calculation (correct = 1.0, partially = 0.5, incorrect = 0.0)
                    weighted_score = question_state['correct_count'] + (question_state['partially_correct_count'] * 0.5)
                    question_state['mastery_level'] = round(weighted_score / total_answers, 2)
                
                return jsonify({
                    'feedback': feedback,
                    'evaluation': evaluation,
                    'mastery_level': question_state['mastery_level'],
                    'success': True
                })
                
            elif action == 'update':
                # Direct update of question state properties
                allowed_fields = [
                    'current_index', 'answered_questions', 'skipped_questions',
                    'correct_count', 'partially_correct_count', 'incorrect_count'
                ]
                
                for field in allowed_fields:
                    if field in data:
                        question_state[field] = data[field]
                
                return jsonify({
                    'question_state': question_state,
                    'success': True
                })
                
            else:
                return jsonify({'error': f'Unknown action: {action}'}), 400
                
    except Exception as e:
        error_msg = f"Error in manage_question_state: {str(e)}"
        print(error_msg)
        return jsonify({
            'error': error_msg,
            'success': False
        }), 500

@app.route('/next-question', methods=['POST'])
def next_question():
    """
    Get the next question using the enhanced question state management
    """
    try:
        data = request.json
        question_index = data.get('question_index', 0)
        
        # Redirect to the new endpoint with the appropriate action
        return redirect(url_for('manage_question_state'), 
                       code=307,  # 307 preserves the POST method
                       Response=Response(
                           json.dumps({
                               'action': 'next'
                           }), 
                           mimetype='application/json')
                       )
        
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
        voice_id = data.get('voice', 'nova')  # Default voice
        model_id = data.get('model', 'sonic-2')  # Default model
        
        if not text:
            print("Error: No text provided")
            return jsonify({'error': 'No text provided'}), 400
            
        if not CARTESIA_API_KEY:
            print("Warning: No Cartesia API key set, returning error")
            return jsonify({'error': 'Cartesia API key not configured'}), 503
            
        print(f"Converting to speech: '{text[:50]}...' (truncated)")
        print(f"Using Cartesia API key: {CARTESIA_API_KEY[:5]}...")
        print(f"Using voice: {voice_id}")
        print(f"Using model: {model_id}")
        
        # Create properly formatted voice parameter
        voice_param = voice_id
        if isinstance(voice_id, str):
            voice_param = {
                "mode": "id",
                "id": voice_id
            }
        
        # Initialize Cartesia SDK client
        import cartesia
        client = cartesia.Cartesia(api_key=CARTESIA_API_KEY)
        
        try:
            # Generate audio using the Cartesia Python SDK
            print(f"Generating audio with Cartesia SDK...")
            print(f"  - transcript: {text[:50]}...")
            print(f"  - model_id: {model_id}")
            print(f"  - voice: {voice_param}")
            
            audio_generator = client.tts.bytes(
                transcript=text,
                model_id=model_id,
                voice=voice_param,
                language="en"
            )
            
            # Combine all chunks into a single audio output
            audio_data = b"".join(list(audio_generator))
            
            print(f"Successfully generated audio, size: {len(audio_data)} bytes")
            
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
            
        except Exception as e:
            error_msg = f"Cartesia SDK error: {str(e)}"
            print(error_msg)
            return jsonify({
                'error': error_msg,
                'success': False
            }), 500
            
    except Exception as e:
        error_msg = f"Error in text_to_speech: {str(e)}"
        print(error_msg)
        return jsonify({
            'error': error_msg,
            'success': False
        }), 500

@app.route('/text-to-speech/stream', methods=['POST', 'OPTIONS'])
def stream_text_to_speech():
    """
    Stream text to speech using Cartesia API - better for longer texts
    """
    # Handle preflight request for CORS
    if request.method == 'OPTIONS':
        response = jsonify({'success': True})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'POST,OPTIONS')
        return response
        
    try:
        print("Received streaming text-to-speech request")
        
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
        except Exception as e:
            print(f"Error parsing JSON: {str(e)}")
            return jsonify({'error': f'Invalid JSON: {str(e)}'}), 400
        
        text = data.get('text')
        voice_id = data.get('voice', 'nova')  # Default voice
        model_id = data.get('model', 'sonic-2')  # Default model
        
        if not text:
            print("Error: No text provided")
            return jsonify({'error': 'No text provided'}), 400
            
        if not CARTESIA_API_KEY:
            print("Warning: No Cartesia API key set, returning error")
            return jsonify({'error': 'Cartesia API key not configured'}), 503
            
        print(f"Streaming speech for: '{text[:50]}...' (truncated)")
        print(f"Using voice: {voice_id}")
        print(f"Using model: {model_id}")
        
        # Create properly formatted voice parameter
        voice_param = voice_id
        if isinstance(voice_id, str):
            voice_param = {
                "mode": "id",
                "id": voice_id
            }
        
        # Initialize Cartesia SDK client
        import cartesia
        client = cartesia.Cartesia(api_key=CARTESIA_API_KEY)
        
        def generate_audio_chunks():
            """Generator function to yield audio chunks as they become available"""
            try:
                # Use context ID to maintain voice consistency across chunks
                context_id = f"ctx_{int(time.time())}_{uuid.uuid4().hex[:8]}"
                print(f"Using context ID: {context_id}")
                
                # Split text into sentences for better streaming
                sentences = re.split(r'(?<=[.!?])\s+', text)
                print(f"Split text into {len(sentences)} sentences")
                
                # Process first sentence to start the stream
                first_sentence = sentences[0]
                
                print(f"Starting stream with first sentence: '{first_sentence}'")
                # Create websocket client from SDK
                ws_client = client.tts.websocket()
                
                # Connect to the websocket
                yield b'--frame\r\n'
                yield b'Content-Type: audio/mpeg\r\n\r\n'
                
                # Process each sentence
                for i, sentence in enumerate(sentences):
                    is_continuation = i > 0
                    
                    if is_continuation:
                        print(f"Continuing with sentence {i+1}/{len(sentences)}")
                        # Use getattr to avoid conflict with Python's 'continue' keyword
                        continue_method = getattr(ws_client, "continue")
                        audio_chunks = continue_method({
                            "contextId": context_id,
                            "transcript": sentence
                        })
                    else:
                        print(f"Starting with sentence {i+1}/{len(sentences)}")
                        audio_chunks = ws_client.send({
                            "contextId": context_id, 
                            "modelId": model_id,
                            "voice": voice_param,
                            "transcript": sentence,
                            "language": "en"
                        })
                    
                    # Stream chunks as they arrive
                    for chunk in audio_chunks:
                        if chunk.type == "chunk":
                            if hasattr(chunk, 'chunk') and chunk.chunk:
                                yield chunk.chunk + b'\r\n'
                                yield b'--frame\r\n'
                                yield b'Content-Type: audio/mpeg\r\n\r\n'
                    
                    # Small pause between sentences for natural cadence
                    time.sleep(0.1)
                
            except Exception as e:
                print(f"Error in streaming TTS: {str(e)}")
                yield f"Error: {str(e)}".encode() + b'\r\n'
                yield b'--frame\r\n'
        
        return Response(
            generate_audio_chunks(),
            mimetype='multipart/x-mixed-replace; boundary=frame',
            headers={
                'Access-Control-Allow-Origin': '*',
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0'
            }
        )
        
    except Exception as e:
        error_msg = f"Error in stream_text_to_speech: {str(e)}"
        print(error_msg)
        return jsonify({
            'error': error_msg,
            'success': False
        }), 500

@app.route('/text-to-speech/cancel', methods=['POST'])
def cancel_tts():
    """
    Cancel an ongoing TTS generation by context ID
    """
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        context_id = data.get('context_id')
        if not context_id:
            return jsonify({'error': 'No context_id provided'}), 400
            
        if not CARTESIA_API_KEY:
            print("Warning: No Cartesia API key set, returning error")
            return jsonify({'error': 'Cartesia API key not configured'}), 503
            
        # Initialize Cartesia SDK client
        import cartesia
        client = cartesia.Cartesia(api_key=CARTESIA_API_KEY)
        
        try:
            # Cancel the TTS generation with the given context ID
            print(f"Cancelling TTS generation with context ID: {context_id}")
            client.tts.cancel_context({"context_id": context_id})
            
            return jsonify({
                'message': f'TTS generation with context ID {context_id} cancelled',
                'success': True
            })
            
        except Exception as e:
            error_msg = f"Cartesia SDK error during cancellation: {str(e)}"
            print(error_msg)
            return jsonify({
                'error': error_msg,
                'success': False
            }), 500
            
    except Exception as e:
        error_msg = f"Error in cancel_tts: {str(e)}"
        print(error_msg)
        return jsonify({
            'error': error_msg,
            'success': False
        }), 500

@app.route('/text-to-speech/voices', methods=['GET'])
def list_tts_voices():
    """
    List available TTS voices from Cartesia
    """
    try:
        if not CARTESIA_API_KEY:
            print("Warning: No Cartesia API key set, returning error")
            return jsonify({'error': 'Cartesia API key not configured'}), 503
            
        # Initialize Cartesia SDK client
        import cartesia
        client = cartesia.Cartesia(api_key=CARTESIA_API_KEY)
        
        try:
            # Get available voices from Cartesia
            response = client.voices.get_all()
            
            # Format the response to include just the essential information
            voice_list = []
            for voice in response.voices:
                voice_info = {
                    "id": voice.id,
                    "name": voice.name,
                    "description": voice.description,
                    "preview_url": voice.preview_url if hasattr(voice, 'preview_url') else None,
                    "gender": voice.gender if hasattr(voice, 'gender') else None,
                    "language": voice.language if hasattr(voice, 'language') else "en"
                }
                voice_list.append(voice_info)
                
            return jsonify({
                'voices': voice_list,
                'success': True
            })
            
        except Exception as e:
            error_msg = f"Cartesia SDK error: {str(e)}"
            print(error_msg)
            return jsonify({
                'error': error_msg,
                'success': False
            }), 500
            
    except Exception as e:
        error_msg = f"Error in list_tts_voices: {str(e)}"
        print(error_msg)
        return jsonify({
            'error': error_msg,
            'success': False
        }), 500

@app.route('/text-to-speech/preferences', methods=['GET', 'POST'])
def tts_preferences():
    """
    Store and retrieve TTS preferences in the user's session
    """
    try:
        session_id = session.get('session_id')
        if not session_id:
            return jsonify({'error': 'Invalid session'}), 400
            
        # Initialize session preferences if not present
        if 'tts_preferences' not in chat_sessions.get(session_id, {}):
            chat_sessions[session_id]['tts_preferences'] = {
                'voice_id': 'nova',
                'model_id': 'sonic-2',
                'auto_read': False
            }
        
        # Handle GET request - return current preferences
        if request.method == 'GET':
            return jsonify({
                'preferences': chat_sessions[session_id]['tts_preferences'],
                'success': True
            })
        
        # Handle POST request - update preferences
        if request.method == 'POST':
            data = request.json
            if not data:
                return jsonify({'error': 'No data provided'}), 400
                
            preferences = chat_sessions[session_id]['tts_preferences']
            
            # Update preferences with provided values
            if 'voice_id' in data:
                preferences['voice_id'] = data['voice_id']
            if 'model_id' in data:
                preferences['model_id'] = data['model_id']
            if 'auto_read' in data:
                preferences['auto_read'] = bool(data['auto_read'])
                
            print(f"Updated TTS preferences for session {session_id}: {preferences}")
            
            return jsonify({
                'preferences': preferences,
                'success': True
            })
            
    except Exception as e:
        error_msg = f"Error in tts_preferences: {str(e)}"
        print(error_msg)
        return jsonify({
            'error': error_msg,
            'success': False
        }), 500

@app.route('/ui-state', methods=['GET', 'POST'])
def manage_ui_state():
    """
    Store and retrieve UI state in the user's session
    """
    try:
        session_id = session.get('session_id')
        if not session_id:
            return jsonify({'error': 'Invalid session'}), 400
            
        # Initialize UI state if not present
        if 'ui_state' not in chat_sessions.get(session_id, {}):
            chat_sessions[session_id]['ui_state'] = {
                'is_assistant_speaking': False,
                'is_microphone_active': False,
                'is_continuous_listening': False,
                'visualizer_settings': {
                    'num_bars': 20,
                    'sensitivity': 1.0,
                    'color': '#3498db'
                },
                'current_question_index': 0,
                'last_interaction_time': time.time()
            }
        
        # Handle GET request - return current UI state
        if request.method == 'GET':
            # Update last interaction time
            chat_sessions[session_id]['ui_state']['last_interaction_time'] = time.time()
            
            return jsonify({
                'ui_state': chat_sessions[session_id]['ui_state'],
                'success': True
            })
        
        # Handle POST request - update UI state
        if request.method == 'POST':
            data = request.json
            if not data:
                return jsonify({'error': 'No data provided'}), 400
                
            ui_state = chat_sessions[session_id]['ui_state']
            
            # Update with provided values
            for key, value in data.items():
                # For nested objects, merge rather than replace
                if key == 'visualizer_settings' and isinstance(value, dict):
                    ui_state['visualizer_settings'].update(value)
                else:
                    ui_state[key] = value
            
            # Always update last interaction time
            ui_state['last_interaction_time'] = time.time()
            
            print(f"Updated UI state for session {session_id}")
            
            return jsonify({
                'ui_state': ui_state,
                'success': True
            })
            
    except Exception as e:
        error_msg = f"Error in manage_ui_state: {str(e)}"
        print(error_msg)
        return jsonify({
            'error': error_msg,
            'success': False
        }), 500

@app.route('/text-to-speech/queue', methods=['POST', 'GET', 'DELETE'])
def tts_queue():
    """
    Manage TTS queue for the user's session
    """
    try:
        session_id = session.get('session_id')
        if not session_id:
            return jsonify({'error': 'Invalid session'}), 400
            
        # Initialize TTS queue if not present
        if 'tts_queue' not in chat_sessions.get(session_id, {}):
            chat_sessions[session_id]['tts_queue'] = []
            chat_sessions[session_id]['active_tts'] = None
        
        # Handle GET request - return current queue state
        if request.method == 'GET':
            tts_queue = chat_sessions[session_id]['tts_queue']
            active_tts = chat_sessions[session_id]['active_tts']
            
            return jsonify({
                'queue': tts_queue,
                'active': active_tts,
                'queue_length': len(tts_queue),
                'is_playing': active_tts is not None,
                'success': True
            })
        
        # Handle DELETE request - clear queue
        if request.method == 'DELETE':
            chat_sessions[session_id]['tts_queue'] = []
            
            # Also cancel active TTS if there is any
            active_tts = chat_sessions[session_id]['active_tts']
            if active_tts and active_tts.get('context_id'):
                try:
                    # Initialize Cartesia SDK client
                    import cartesia
                    client = cartesia.Cartesia(api_key=CARTESIA_API_KEY)
                    client.tts.cancel_context({"context_id": active_tts['context_id']})
                    print(f"Cancelled active TTS with context ID: {active_tts['context_id']}")
                except Exception as e:
                    print(f"Error cancelling active TTS: {str(e)}")
                    
            chat_sessions[session_id]['active_tts'] = None
            
            # Update UI state to reflect speaking status
            if 'ui_state' in chat_sessions[session_id]:
                chat_sessions[session_id]['ui_state']['is_assistant_speaking'] = False
            
            return jsonify({
                'message': 'TTS queue cleared',
                'success': True
            })
        
        # Handle POST request - add to queue
        if request.method == 'POST':
            data = request.json
            if not data or 'text' not in data:
                return jsonify({'error': 'No text provided'}), 400
                
            # Get preferences
            tts_preferences = chat_sessions[session_id].get('tts_preferences', {
                'voice_id': 'nova',
                'model_id': 'sonic-2'
            })
            
            # Extract request details
            text = data['text']
            voice_id = data.get('voice_id', tts_preferences.get('voice_id', 'nova'))
            model_id = data.get('model_id', tts_preferences.get('model_id', 'sonic-2'))
            priority = data.get('priority', 'normal')  # can be 'high', 'normal', or 'low'
            
            # Create TTS request object
            context_id = f"ctx_{int(time.time())}_{uuid.uuid4().hex[:8]}"
            tts_request = {
                'text': text,
                'voice_id': voice_id,
                'model_id': model_id,
                'context_id': context_id,
                'timestamp': time.time(),
                'priority': priority,
                'is_streaming': len(text) > 100  # Use streaming for longer texts
            }
            
            tts_queue = chat_sessions[session_id]['tts_queue']
            
            # Handle priority queue insertion
            if priority == 'high':
                # Insert at the beginning
                tts_queue.insert(0, tts_request)
            elif priority == 'low':
                # Add to the end
                tts_queue.append(tts_request)
            else:  # normal priority
                # If queue is empty, add to end
                if not tts_queue:
                    tts_queue.append(tts_request)
                else:
                    # Insert after high priority items but before low priority
                    insert_index = 0
                    for i, req in enumerate(tts_queue):
                        if req['priority'] != 'high':
                            insert_index = i
                            break
                        insert_index = i + 1
                    tts_queue.insert(insert_index, tts_request)
            
            print(f"Added TTS request to queue. Queue length: {len(tts_queue)}")
            
            # Immediate response with queue position info
            return jsonify({
                'message': 'Added to TTS queue',
                'context_id': context_id,
                'queue_position': tts_queue.index(tts_request),
                'queue_length': len(tts_queue),
                'success': True
            })
            
    except Exception as e:
        error_msg = f"Error in tts_queue: {str(e)}"
        print(error_msg)
        return jsonify({
            'error': error_msg,
            'success': False
        }), 500

@app.route('/text-to-speech/process-queue', methods=['POST'])
def process_tts_queue():
    """
    Process the next item in the TTS queue
    Client should call this when ready for the next audio file
    """
    try:
        session_id = session.get('session_id')
        if not session_id:
            return jsonify({'error': 'Invalid session'}), 400
            
        # Check if we have a queue
        if 'tts_queue' not in chat_sessions.get(session_id, {}):
            return jsonify({
                'message': 'No TTS queue exists',
                'success': False
            }), 404
            
        tts_queue = chat_sessions[session_id]['tts_queue']
        
        # If queue is empty, return empty response
        if not tts_queue:
            # Update UI state to reflect speaking status
            if 'ui_state' in chat_sessions[session_id]:
                chat_sessions[session_id]['ui_state']['is_assistant_speaking'] = False
                
            return jsonify({
                'message': 'TTS queue is empty',
                'queue_empty': True,
                'success': True
            })
            
        # Get the next request from the queue
        next_request = tts_queue.pop(0)
        
        # Update active TTS
        chat_sessions[session_id]['active_tts'] = next_request
        
        # Update UI state to reflect speaking status
        if 'ui_state' in chat_sessions[session_id]:
            chat_sessions[session_id]['ui_state']['is_assistant_speaking'] = True
        
        # Process the request by redirecting to the appropriate endpoint
        if next_request['is_streaming']:
            # For streaming, redirect to the streaming endpoint
            return redirect(url_for('stream_text_to_speech'), 
                           code=307,  # 307 preserves the POST method
                           Response=Response(
                               json.dumps({
                                   'text': next_request['text'], 
                                   'voice': next_request['voice_id'],
                                   'model': next_request['model_id'],
                                   'context_id': next_request['context_id']
                               }), 
                               mimetype='application/json')
                           )
        else:
            # For short text, use non-streaming endpoint
            return redirect(url_for('text_to_speech'), 
                           code=307,  # 307 preserves the POST method
                           Response=Response(
                               json.dumps({
                                   'text': next_request['text'], 
                                   'voice': next_request['voice_id'],
                                   'model': next_request['model_id']
                               }), 
                               mimetype='application/json')
                           )
            
    except Exception as e:
        error_msg = f"Error in process_tts_queue: {str(e)}"
        print(error_msg)
        return jsonify({
            'error': error_msg,
            'success': False
        }), 500

@app.route('/audio/websocket-token', methods=['GET'])
def get_websocket_token():
    """
    Generate a token for WebSocket authentication
    """
    try:
        session_id = session.get('session_id')
        if not session_id:
            return jsonify({'error': 'Invalid session'}), 400
            
        # Generate a token that expires in 15 minutes
        token = f"ws_token_{session_id}_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        expiry = time.time() + 900  # 15 minutes
        
        # Store the token in the session data
        if 'websocket_tokens' not in chat_sessions.get(session_id, {}):
            chat_sessions[session_id]['websocket_tokens'] = {}
        
        chat_sessions[session_id]['websocket_tokens'][token] = {
            'created_at': time.time(),
            'expires_at': expiry,
            'type': 'audio'
        }
        
        return jsonify({
            'token': token,
            'expires_at': expiry,
            'success': True
        })
        
    except Exception as e:
        error_msg = f"Error in get_websocket_token: {str(e)}"
        print(error_msg)
        return jsonify({
            'error': error_msg,
            'success': False
        }), 500

@app.route('/audio/speech-to-text/start', methods=['POST'])
def start_speech_recognition():
    """
    Start a new speech recognition session
    """
    try:
        session_id = session.get('session_id')
        if not session_id:
            return jsonify({'error': 'Invalid session'}), 400
            
        # Initialize audio processing state if not present
        if 'audio_state' not in chat_sessions.get(session_id, {}):
            chat_sessions[session_id]['audio_state'] = {
                'is_listening': False,
                'is_continuous': False,
                'recognition_mode': 'command',  # can be 'command', 'dictation', or 'conversation'
                'audio_chunks': [],
                'last_chunk_time': None,
                'session_start_time': None,
                'transcription_history': []
            }
        
        audio_state = chat_sessions[session_id]['audio_state']
        
        # Parse request parameters
        data = request.json or {}
        continuous = data.get('continuous', False)
        recognition_mode = data.get('mode', 'command')
        
        # Update audio state
        audio_state['is_listening'] = True
        audio_state['is_continuous'] = continuous
        audio_state['recognition_mode'] = recognition_mode
        audio_state['session_start_time'] = time.time()
        audio_state['audio_chunks'] = []
        
        # Update UI state to reflect listening status
        if 'ui_state' in chat_sessions[session_id]:
            chat_sessions[session_id]['ui_state']['is_microphone_active'] = True
            chat_sessions[session_id]['ui_state']['is_continuous_listening'] = continuous
        
        # Generate a unique session ID for this recognition session
        recognition_id = f"rec_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        audio_state['current_recognition_id'] = recognition_id
        
        return jsonify({
            'message': f"Started {'continuous' if continuous else 'single'} speech recognition in {recognition_mode} mode",
            'recognition_id': recognition_id,
            'success': True
        })
        
    except Exception as e:
        error_msg = f"Error in start_speech_recognition: {str(e)}"
        print(error_msg)
        return jsonify({
            'error': error_msg,
            'success': False
        }), 500

@app.route('/audio/speech-to-text/stop', methods=['POST'])
def stop_speech_recognition():
    """
    Stop the current speech recognition session
    """
    try:
        session_id = session.get('session_id')
        if not session_id:
            return jsonify({'error': 'Invalid session'}), 400
            
        # Check if audio state exists
        if 'audio_state' not in chat_sessions.get(session_id, {}):
            return jsonify({'error': 'No active speech recognition session'}), 400
            
        audio_state = chat_sessions[session_id]['audio_state']
        
        # Update state
        audio_state['is_listening'] = False
        audio_state['is_continuous'] = False
        
        # Update UI state to reflect listening status
        if 'ui_state' in chat_sessions[session_id]:
            chat_sessions[session_id]['ui_state']['is_microphone_active'] = False
            chat_sessions[session_id]['ui_state']['is_continuous_listening'] = False
        
        # Process any remaining audio chunks
        transcript = None
        if audio_state['audio_chunks']:
            try:
                # This would be implemented to process the audio chunks
                # For now, log that we would process them
                print(f"Would process {len(audio_state['audio_chunks'])} remaining audio chunks")
                # Reset chunks after processing
                audio_state['audio_chunks'] = []
            except Exception as e:
                print(f"Error processing remaining audio chunks: {str(e)}")
        
        return jsonify({
            'message': "Stopped speech recognition",
            'success': True
        })
        
    except Exception as e:
        error_msg = f"Error in stop_speech_recognition: {str(e)}"
        print(error_msg)
        return jsonify({
            'error': error_msg,
            'success': False
        }), 500

@app.route('/audio/speech-to-text/chunk', methods=['POST'])
def process_audio_chunk():
    """
    Process an audio chunk for transcription
    """
    try:
        session_id = session.get('session_id')
        if not session_id:
            return jsonify({'error': 'Invalid session'}), 400
            
        # Check if audio state exists and we're in listening mode
        if 'audio_state' not in chat_sessions.get(session_id, {}) or not chat_sessions[session_id]['audio_state']['is_listening']:
            return jsonify({'error': 'No active speech recognition session'}), 400
            
        audio_state = chat_sessions[session_id]['audio_state']
        
        # Check if a file was uploaded
        if 'audio_chunk' not in request.files:
            return jsonify({'error': 'No audio chunk provided'}), 400
            
        audio_chunk = request.files['audio_chunk']
        if audio_chunk.filename == '':
            return jsonify({'error': 'Empty filename'}), 400
        
        # Process the audio chunk
        recognition_mode = audio_state['recognition_mode']
        is_continuous = audio_state['is_continuous']
        
        # Update last chunk time
        audio_state['last_chunk_time'] = time.time()
        
        # Save the chunk to process
        with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as temp_audio:
            chunk_path = temp_audio.name
            audio_chunk.save(chunk_path)
            print(f"Saved uploaded audio chunk to temporary file: {chunk_path}")
            
            # If we're in command or conversation mode, we process each chunk immediately
            if recognition_mode in ['command', 'conversation'] and not is_continuous:
                try:
                    with open(chunk_path, 'rb') as audio_file:
                        # Call OpenAI's Whisper model for transcription
                        print("Calling OpenAI Whisper API...")
                        transcript = openai.audio.transcriptions.create(
                            model="whisper-1",
                            file=audio_file,
                            language="en"
                        )
                        
                        transcribed_text = transcript.text.strip()
                        print(f"Transcription successful: '{transcribed_text}'")
                        
                        # Add to transcription history
                        audio_state['transcription_history'].append({
                            'text': transcribed_text,
                            'timestamp': time.time(),
                            'mode': recognition_mode
                        })
                        
                        # Return the transcribed text
                        return jsonify({
                            'text': transcribed_text,
                            'is_final': True,
                            'success': True
                        })
                except Exception as e:
                    error_msg = f"Error during transcription: {str(e)}"
                    print(error_msg)
                    return jsonify({
                        'error': error_msg,
                        'success': False
                    }), 500
            else:
                # In continuous mode or dictation mode, we collect chunks and process them together
                audio_state['audio_chunks'].append(chunk_path)
                
                # If we have enough chunks or it's been a while since the last chunk, process them
                chunk_threshold = 5  # Process after collecting 5 chunks
                time_threshold = 2.0  # Or after 2 seconds since first chunk
                
                if len(audio_state['audio_chunks']) >= chunk_threshold:
                    # Process the collected chunks
                    try:
                        # This would combine and process the audio chunks
                        # For now, just acknowledge receipt
                        print(f"Collected {len(audio_state['audio_chunks'])} chunks, would process them")
                        
                        # Reset chunks after processing
                        audio_state['audio_chunks'] = []
                        
                        return jsonify({
                            'message': f"Processed {chunk_threshold} audio chunks",
                            'is_final': False,
                            'success': True
                        })
                    except Exception as e:
                        error_msg = f"Error processing audio chunks: {str(e)}"
                        print(error_msg)
                        return jsonify({
                            'error': error_msg,
                            'success': False
                        }), 500
                else:
                    # Just acknowledge receipt of chunk
                    return jsonify({
                        'message': f"Received audio chunk ({len(audio_state['audio_chunks'])}/{chunk_threshold})",
                        'is_final': False,
                        'success': True
                    })
        
    except Exception as e:
        error_msg = f"Error in process_audio_chunk: {str(e)}"
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
        socketio.run(app, debug=True, host='localhost', port=5001)
    else:
        print(f"SSL certificate files found. Running with HTTPS enabled.")
        socketio.run(app, debug=True, host='localhost', port=5001, ssl_context=(cert_file, key_file)) 