# Apply eventlet monkey patching at the very beginning
import eventlet
eventlet.monkey_patch()

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
import io
from werkzeug.utils import secure_filename

# Import LangGraph components
from graph import app as langgraph_app
from nodes import GraphState

"""
Configuration Instructions:
--------------------------
1. Create or modify a .env file in the root directory with the following variables:
   OPENAI_API_KEY="your_openai_api_key"
   CARTESIA_API_KEY="your_cartesia_api_key"
   MISTRAL_API_KEY="your_mistral_api_key"

2. If the .env file already exists, add the CARTESIA_API_KEY and MISTRAL_API_KEY variables.

3. Cartesia API is used for high-quality text-to-speech (TTS) capabilities.
   This functionality requires a valid Cartesia API key.
   
4. Mistral API is used for PDF processing and question generation.
   The app requires this API key for the LangGraph pipeline functionality.

5. Restart the application after updating the .env file.
"""

# Load environment variables from .env file
load_dotenv()

# Initialize OpenAI API
openai.api_key = os.getenv("OPENAI_API_KEY")
# Initialize Cartesia API key
CARTESIA_API_KEY = os.getenv("CARTESIA_API_KEY", "")
# Initialize Mistral API key
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")

# Check and log API availability
if not CARTESIA_API_KEY:
    print("WARNING: Cartesia API key not found. Text-to-speech will not work.")
else:
    print("Cartesia API key loaded successfully.")

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(24).hex())

# Configure secure cookies for HTTPS
app.config['SESSION_COOKIE_SECURE'] = True  # Only send cookies over HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True  # Prevent JavaScript access to cookies
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # SameSite protection

# Store chat sessions (in-memory for simplicity - would use a database in production)
chat_sessions = {}

# Initialize SocketIO with Flask app
socketio = SocketIO(app, 
                   cors_allowed_origins="*", 
                   async_mode='eventlet',
                   logger=True,
                   engineio_logger=True)

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

# Define allowed file extensions and max file size
ALLOWED_EXTENSIONS = {'pdf'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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

@app.route('/upload-pdf', methods=['POST'])
def upload_pdf():
    """Handle PDF upload and process it through the LangGraph pipeline"""
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
        
    session_id = session.get('session_id')
    
    # Check if file is in request
    if 'pdf_file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
        
    file = request.files['pdf_file']
    
    # Check if file was selected
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
        
    # Check file type
    if not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file type. Only PDF files are allowed.'}), 400
    
    # Check file size
    if request.content_length > MAX_FILE_SIZE:
        return jsonify({'error': f'File size exceeds limit of {MAX_FILE_SIZE/1024/1024}MB'}), 400
    
    try:
        # Get the file content as BytesIO
        pdf_stream = io.BytesIO(file.read())
        
        # Initialize session if needed
        if session_id not in chat_sessions:
            chat_sessions[session_id] = {
                'messages': [],
                'current_topic': None,
                'generated_questions': []
            }
            
        # Update UI state to show processing
        chat_sessions[session_id]['ui_state'] = {
            'is_processing_pdf': True,
            'pdf_filename': secure_filename(file.filename)
        }
        
        # Use LangGraph to process the PDF
        input_state = GraphState(pdf_stream=pdf_stream)
        result = langgraph_app.invoke(input_state)
        
        # Check for errors in the result
        if result.get('error'):
            chat_sessions[session_id]['ui_state'] = {
                'is_processing_pdf': False,
                'pdf_error': result['error']
            }
            return jsonify({'error': result['error']}), 500
            
        # Extract generated questions from result
        generated_questions = result.get('generated_questions', [])
        if not generated_questions:
            chat_sessions[session_id]['ui_state'] = {
                'is_processing_pdf': False,
                'pdf_error': 'No questions could be generated from this PDF'
            }
            return jsonify({'error': 'No questions could be generated'}), 500
        
        # Set topic from filename
        filename_without_ext = os.path.splitext(secure_filename(file.filename))[0]
        topic = f"PDF: {filename_without_ext}"
        
        # Update session with questions and topic
        chat_sessions[session_id]['current_topic'] = topic
        chat_sessions[session_id]['generated_questions'] = generated_questions
        chat_sessions[session_id]['question_state'] = {
            'current_index': 0,
            'total': len(generated_questions),
            'source': 'pdf'
        }
        
        # Update UI state to show completion
        chat_sessions[session_id]['ui_state'] = {
            'is_processing_pdf': False,
            'pdf_processed': True,
            'pdf_filename': secure_filename(file.filename)
        }
        
        # Emit socket event if socket is connected
        if session_id in socket_sessions:
            socketio.emit('ui_state_update', chat_sessions[session_id]['ui_state'], room=session_id)
            socketio.emit('question_state_update', {
                'question_state': chat_sessions[session_id]['question_state'],
                'current_question': generated_questions[0],
                'total_questions': len(generated_questions)
            }, room=session_id)
        
        # Add system message to chat
        bot_message = {
            'role': 'assistant',
            'content': f"I've analyzed your PDF and generated {len(generated_questions)} questions for active recall practice. Let's begin with the first question."
        }
        chat_sessions[session_id]['messages'].append(bot_message)
        
        return jsonify({
            'success': True,
            'message': f"Successfully processed PDF and generated {len(generated_questions)} questions",
            'questions': generated_questions,
            'topic': topic
        })
        
    except Exception as e:
        print(f"Error processing PDF: {str(e)}")
        # Update UI state to show error
        if session_id in chat_sessions:
            chat_sessions[session_id]['ui_state'] = {
                'is_processing_pdf': False,
                'pdf_error': f"Error processing PDF: {str(e)}"
            }
            # Emit socket event if socket is connected
            if session_id in socket_sessions:
                socketio.emit('ui_state_update', chat_sessions[session_id]['ui_state'], room=session_id)
                
        return jsonify({'error': f"Error processing PDF: {str(e)}"}), 500

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
            return jsonify({
                'error': 'Cartesia API key not configured',
                'success': False
            }), 503
            
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
            return jsonify({
                'error': 'Cartesia API key not configured',
                'success': False
            }), 503
            
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
            return jsonify({
                'error': 'Cartesia API key not configured',
                'success': False
            }), 503
            
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
            return jsonify({
                'error': 'Cartesia API key not configured',
                'success': False
            }), 503
            
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
                'auto_read': False,
                'server_tts': True,  # Always use server TTS
                'force_browser_tts': False  # Never force browser TTS
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
            if 'server_tts' in data:
                preferences['server_tts'] = bool(data['server_tts'])
            if 'force_browser_tts' in data:
                preferences['force_browser_tts'] = bool(data['force_browser_tts'])
                
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
        
        # Check if Cartesia API is configured
        if not CARTESIA_API_KEY:
            print("Warning: Cartesia API key not set, returning error")
            # Return an error without the text
            return jsonify({
                'error': 'Cartesia API key not configured',
                'success': False
            }), 503
        
        # Instead of using redirect, directly call the appropriate function
        if next_request['is_streaming']:
            # For streaming, call the stream function directly
            text = next_request['text']
            voice_id = next_request['voice_id']
            model_id = next_request['model_id']
            
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
                    context_id = next_request.get('context_id', f"ctx_{int(time.time())}_{uuid.uuid4().hex[:8]}")
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
            
        else:
            # For short text, directly call the text_to_speech function
            text = next_request['text']
            voice_id = next_request['voice_id']
            model_id = next_request['model_id']
            
            print(f"Converting to speech: '{text[:50]}...' (truncated)")
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
                        "Content-Disposition": "attachment; filename=speech.mp3",
                        'Access-Control-Allow-Origin': '*'
                    }
                )
                
                return flask_response
                
            except Exception as e:
                error_msg = f"Cartesia SDK error: {str(e)}"
                print(error_msg)
                return jsonify({
                    'error': error_msg,
                    'success': False
                }), 500
            
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
    Handle initial message to identify the topic for review.
    Returns a tuple of (response_message, response_text)
    """
    # Extract topic and difficulty from message
    topic_info = analyze_review_topic(user_message)
    topic = topic_info['topic']
    difficulty = topic_info.get('difficulty', 'mixed')  # Default to mixed if not specified
    
    if not topic:
        # If topic wasn't clearly identified, ask for clarification
        response_text = "I'd be happy to help you study! Please specify what topic you'd like to review. For example, 'I want to review photosynthesis' or 'Help me study Spanish verb conjugation'."
        return {"role": "assistant", "content": response_text}, response_text
    
    # Generate questions based on the identified topic and difficulty
    questions = generate_active_recall_questions(topic, difficulty)
    
    if not questions:
        # Handle case where question generation failed
        response_text = f"I apologize, but I couldn't generate questions about {topic}. Could you please try a different topic or phrase it differently?"
        return {"role": "assistant", "content": response_text}, response_text
    
    # Store the topic and generated questions
    session_data['current_topic'] = topic
    session_data['topic_difficulty'] = difficulty
    session_data['generated_questions'] = questions
    session_data['question_state'] = {
        'current_index': 0,
        'total': len(questions),
        'difficulty': difficulty,
        'correct_count': 0,
        'incorrect_count': 0
    }
    
    # Format response with difficulty information
    difficulty_display = difficulty.capitalize() if difficulty != 'mixed' else 'Mixed (Basic to Advanced)'
    response_text = f"Great! I'll help you review {topic} at {difficulty_display} difficulty level. I've prepared {len(questions)} active recall questions to test your knowledge. Let's start:\n\n{questions[0]}"
    
    return {"role": "assistant", "content": response_text}, response_text

def handle_ongoing_conversation(user_message, session_data):
    """
    Handle conversation after the topic has been established.
    Returns a tuple of (response_message, response_text)
    """
    # Check if the user wants to change topics or difficulty
    if is_new_topic_request(user_message):
        # Extract new topic info
        topic_info = extract_new_topic(user_message)
        
        if topic_info['topic']:
            # Generate new questions for the new topic
            questions = generate_active_recall_questions(topic_info['topic'], topic_info['difficulty'])
            
            if questions:
                # Update session with new topic and questions
                session_data['current_topic'] = topic_info['topic']
                session_data['topic_difficulty'] = topic_info['difficulty']
                session_data['generated_questions'] = questions
                session_data['question_state'] = {
                    'current_index': 0,
                    'total': len(questions),
                    'difficulty': topic_info['difficulty'],
                    'correct_count': 0,
                    'incorrect_count': 0
                }
                
                # Format response with difficulty information
                difficulty_display = topic_info['difficulty'].capitalize() 
                if topic_info['difficulty'] == 'mixed':
                    difficulty_display = 'Mixed (Basic to Advanced)'
                    
                response_text = f"I've switched to helping you review {topic_info['topic']} at {difficulty_display} difficulty level. I've prepared {len(questions)} new questions. Let's start:\n\n{questions[0]}"
                return {"role": "assistant", "content": response_text}, response_text
            else:
                response_text = f"I couldn't generate questions about {topic_info['topic']}. Could you try a different topic?"
                return {"role": "assistant", "content": response_text}, response_text
    
    # Check if user is asking for the next question
    if is_next_question_request(user_message):
        return handle_next_question(session_data)
    
    # Check if user wants to change difficulty without changing topic
    if is_difficulty_change_request(user_message):
        new_difficulty = extract_difficulty(user_message)
        if new_difficulty:
            current_topic = session_data['current_topic']
            # Generate new questions with new difficulty
            questions = generate_active_recall_questions(current_topic, new_difficulty)
            
            if questions:
                # Update session
                session_data['topic_difficulty'] = new_difficulty
                session_data['generated_questions'] = questions
                session_data['question_state'] = {
                    'current_index': 0,
                    'total': len(questions),
                    'difficulty': new_difficulty,
                    'correct_count': 0,
                    'incorrect_count': 0
                }
                
                difficulty_display = new_difficulty.capitalize()
                if new_difficulty == 'mixed':
                    difficulty_display = 'Mixed (Basic to Advanced)'
                    
                response_text = f"I've updated the difficulty to {difficulty_display} for topic {current_topic}. Here's your first question:\n\n{questions[0]}"
                return {"role": "assistant", "content": response_text}, response_text
    
    # Default: Provide feedback on the user's answer
    return generate_feedback_or_hint(user_message, session_data)

def is_next_question_request(message):
    """Check if user is asking for the next question."""
    patterns = [
        r"(?i)(?:next|another|different) question",
        r"(?i)next",
        r"(?i)give me (?:another|the next)",
        r"(?i)move(?: on)?(?: to next)?",
        r"(?i)let's continue"
    ]
    
    for pattern in patterns:
        if re.search(pattern, message):
            return True
    return False

def handle_next_question(session_data):
    """Handle a request for the next question."""
    questions = session_data.get('generated_questions', [])
    
    if not questions:
        response_text = "I don't have any questions prepared. Let's establish a topic first."
        return {"role": "assistant", "content": response_text}, response_text
    
    # Get current question state
    question_state = session_data.get('question_state', {'current_index': 0})
    current_index = question_state.get('current_index', 0)
    
    # Move to next question
    next_index = current_index + 1
    
    # Check if we've reached the end of questions
    if next_index >= len(questions):
        # We've completed all questions
        correct = question_state.get('correct_count', 0)
        total = len(questions)
        accuracy = (correct / total) * 100 if total > 0 else 0
        
        response_text = f"You've completed all {total} questions on {session_data['current_topic']}! "
        response_text += f"You correctly answered approximately {correct} questions ({accuracy:.1f}% accuracy). "
        
        if accuracy < 70:
            response_text += "Would you like to try again with the same questions, or would you prefer a different topic or difficulty level?"
        else:
            response_text += "Great job! Would you like to try a different topic or difficulty level?"
            
        # Reset index to 0 for potential reuse
        question_state['current_index'] = 0
    else:
        # Update index and get next question
        question_state['current_index'] = next_index
        next_question = questions[next_index]
        response_text = f"Question {next_index + 1} of {len(questions)}:\n\n{next_question}"
    
    # Update session data
    session_data['question_state'] = question_state
    
    return {"role": "assistant", "content": response_text}, response_text

def is_difficulty_change_request(message):
    """Check if user is asking to change the difficulty level."""
    patterns = [
        r"(?i)(?:change|switch|adjust) (?:the )?difficulty",
        r"(?i)make (?:it|the questions) (?:easier|harder|more difficult|simpler)",
        r"(?i)(?:easier|harder|more advanced|more basic) questions",
        r"(?i)(?:basic|beginner|intermediate|advanced|mixed) (?:difficulty|level|mode)"
    ]
    
    for pattern in patterns:
        if re.search(pattern, message):
            return True
    return False

def extract_difficulty(message):
    """Extract the requested difficulty level from the message."""
    if re.search(r"(?i)(?:basic|beginner|elementary|simple|easy)", message):
        return 'basic'
    elif re.search(r"(?i)(?:intermediate|moderate|medium)", message):
        return 'intermediate'
    elif re.search(r"(?i)(?:advanced|difficult|complex|hard|challenging)", message):
        return 'advanced'
    elif re.search(r"(?i)(?:mixed|varied|all levels|different levels)", message):
        return 'mixed'
    else:
        return None

def analyze_review_topic(user_input):
    """
    Analyze the user's message to extract the review topic and difficulty level.
    Returns a dict with topic and difficulty.
    """
    # Look for explicit topic indicators
    topic_indicators = [
        r"(?i)(?:help me|I want to|I'd like to|can you help me|I need to|let's|let me) (?:review|study|learn|practice|go over|understand) ([\w\s\-']+)",
        r"(?i)(?:review|study|learn about|practice|quiz me on|test me on) ([\w\s\-']+)",
        r"(?i)I'm (?:studying|learning|reviewing) ([\w\s\-']+)",
        r"(?i)(?:questions|quiz|test) (?:about|on|regarding|for|related to) ([\w\s\-']+)"
    ]
    
    # Look for difficulty indicators
    difficulty_patterns = {
        'basic': r"(?i)(?:basic|beginner|elementary|simple|easy|introductory|fundamental)",
        'intermediate': r"(?i)(?:intermediate|moderate|medium|middle-level)",
        'advanced': r"(?i)(?:advanced|difficult|complex|hard|expert|challenging|in-depth)",
        'mixed': r"(?i)(?:mixed|varied|all levels|different levels|range of)"
    }
    
    # Extract topic
    topic = None
    for pattern in topic_indicators:
        match = re.search(pattern, user_input)
        if match:
            topic = match.group(1).strip().rstrip(".,?!").strip()
            break
    
    # If no structured pattern matched, just use the whole input as topic
    if not topic:
        # Remove common phrases that aren't part of the topic
        cleaned_input = re.sub(r"(?i)(?:please |can you |I want to |help me |quiz me |test me )", "", user_input)
        topic = cleaned_input.strip().rstrip(".,?!").strip()
    
    # Extract difficulty
    difficulty = 'mixed'  # default
    for level, pattern in difficulty_patterns.items():
        if re.search(pattern, user_input):
            difficulty = level
            break
    
    result = {
        'topic': topic,
        'difficulty': difficulty
    }
    
    print(f"Analyzed topic: '{topic}', Difficulty: {difficulty}")
    return result

def generate_active_recall_questions(topic, difficulty='mixed'):
    """Generate active recall questions for a given topic with specified difficulty level."""
    try:
        # Create a prompt based on the topic and difficulty
        prompt = create_topic_based_prompt(topic, difficulty)
        
        # Call OpenAI API
        response = openai.ChatCompletion.create(
            model="gpt-4",  # Use GPT-4 for better question quality
            messages=[
                {"role": "system", "content": "You are an expert educator specializing in creating effective active recall questions."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1500
        )
        
        # Extract and format the questions
        raw_questions = response.choices[0].message.content.strip()
        questions = parse_and_validate_questions(raw_questions)
        
        if not questions:
            print(f"Warning: Failed to parse questions for topic '{topic}'")
            return []
            
        print(f"Generated {len(questions)} questions for topic '{topic}' at {difficulty} difficulty")
        return questions
        
    except Exception as e:
        print(f"Error generating questions: {str(e)}")
        return []

def create_topic_based_prompt(topic, difficulty='mixed'):
    """Create a specialized prompt based on topic and difficulty level."""
    
    # Base prompt structure
    base_prompt = f"""
Generate 5-8 active recall questions about "{topic}".
    """
    
    # Add difficulty-specific instructions
    difficulty_instructions = {
        'basic': """
Focus on foundational concepts and definitions.
These questions should help beginners establish a basic understanding of the topic.
Use straightforward language and clear, unambiguous questions.
""",
        'intermediate': """
Target intermediate understanding with questions that explore relationships between concepts.
Include questions that require application of knowledge, not just recall.
Incorporate some technical terminology appropriate for someone with some background.
""",
        'advanced': """
Create challenging questions that require deep understanding and critical thinking.
Include questions on complex applications, edge cases, and advanced theories.
Use precise technical terminology and expect sophisticated understanding.
""",
        'mixed': """
Provide a balanced mix of basic, intermediate, and advanced questions.
Label each question with its difficulty level (Basic, Intermediate, Advanced).
Progress from simpler to more complex concepts to build understanding.
"""
    }
    
    # Add subject-specific instructions based on topic analysis
    subject_type = analyze_topic_type(topic)
    subject_instructions = {
        'math': """
Include some questions requiring step-by-step problem-solving.
Focus on conceptual understanding alongside procedural knowledge.
For formulas, ask about their applications and meanings, not just memorization.
""",
        'science': """
Include questions about experiments, evidence, and scientific models.
Ask about cause-effect relationships and applications of scientific principles.
Balance theoretical questions with practical applications.
""",
        'history': """
Include questions about chronology, cause-effect relationships, and historical significance.
Ask about different perspectives and interpretations of historical events.
Balance factual recall with questions about historical processes and themes.
""",
        'language': """
Include questions about grammar rules, vocabulary application, and language constructs.
Ask about practical usage and exceptions to rules.
Include contextual examples to test understanding.
""",
        'arts': """
Include questions about techniques, historical context, and interpretative aspects.
Balance factual knowledge with questions about aesthetic principles.
Ask about influential works and their significance.
""",
        'technology': """
Include questions about principles, implementations, and practical applications.
Ask about evolution of technologies and their impact.
Balance theoretical understanding with practical usage scenarios.
""",
        'general': """
Cover key concepts, applications, and relationships within the topic.
Include questions that test both recall and understanding.
Balance breadth and depth of the topic.
"""
    }
    
    # Format instructions based on difficulty and topic
    difficulty_instruction = difficulty_instructions.get(difficulty, difficulty_instructions['mixed'])
    subject_instruction = subject_instructions.get(subject_type, subject_instructions['general'])
    
    # Combine all instructions into the final prompt
    final_prompt = f"""{base_prompt}

Difficulty level: {difficulty.capitalize()}
{difficulty_instruction}

Topic-specific guidance:
{subject_instruction}

Format guidelines:
1. Each question should be self-contained and clear.
2. Avoid overly complex or compound questions.
3. Ensure questions are directly related to the topic.
4. Format each question on its own line without numbering or prefixes.
5. If using "mixed" difficulty, label each question with its level: [Basic], [Intermediate], or [Advanced].

Examples of well-formed questions:
- What is the primary function of mitochondria in a cell?
- How does Newton's Third Law apply to rocket propulsion?
- What factors contributed to the fall of the Roman Empire?

Return ONLY the questions themselves, one per line, without explanations or additional text.
"""
    
    return final_prompt

def analyze_topic_type(topic):
    """Analyze the topic to determine what subject category it falls into."""
    
    # Convert to lowercase for easier matching
    topic_lower = topic.lower()
    
    # Keywords for different subject areas
    subject_keywords = {
        'math': ['math', 'algebra', 'calculus', 'geometry', 'statistics', 'probability', 'equation', 'function', 'theorem', 'number'],
        'science': ['science', 'biology', 'chemistry', 'physics', 'astronomy', 'geology', 'molecule', 'cell', 'atom', 'energy', 'force'],
        'history': ['history', 'war', 'civilization', 'empire', 'revolution', 'century', 'ancient', 'medieval', 'modern', 'president', 'king'],
        'language': ['language', 'grammar', 'syntax', 'vocabulary', 'literature', 'writing', 'reading', 'speaking', 'english', 'spanish'],
        'arts': ['art', 'music', 'painting', 'sculpture', 'dance', 'theater', 'film', 'design', 'photography', 'architecture'],
        'technology': ['technology', 'computer', 'software', 'hardware', 'programming', 'code', 'algorithm', 'data', 'internet', 'digital']
    }
    
    # Check for keyword matches
    for subject, keywords in subject_keywords.items():
        for keyword in keywords:
            if keyword in topic_lower:
                return subject
    
    # Default to general if no specific matches
    return 'general'

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
    """Extract a new topic request from the user message."""
    topic_info = analyze_review_topic(message)
    return topic_info

def generate_feedback_or_hint(user_message, session_data):
    """
    Generate feedback or hint based on the user's response to a question.
    """
    # Get current question
    questions = session_data.get('generated_questions', [])
    question_state = session_data.get('question_state', {'current_index': 0})
    current_index = question_state.get('current_index', 0)
    
    if not questions or current_index >= len(questions):
        response_text = "I'm not sure what question you're answering. Let's start with a topic first."
        return {"role": "assistant", "content": response_text}, response_text
    
    current_question = questions[current_index]
    current_topic = session_data.get('current_topic', 'the topic')
    current_difficulty = session_data.get('topic_difficulty', 'mixed')
    
    # Check if this is a hint request
    is_hint_request = "hint" in user_message.lower() or "help" in user_message.lower()
    
    try:
        if is_hint_request:
            # Generate a hint based on the question
            prompt = f"""
The student is asking for a hint on this question: "{current_question}"
The topic is "{current_topic}" and the difficulty level is "{current_difficulty}".

Provide a helpful hint that guides them toward the answer without giving it away completely.
For basic questions, the hint can be more direct.
For intermediate questions, provide some guidance but let them make connections.
For advanced questions, give minimal hints that prompt critical thinking.

Write a brief, helpful hint:
"""
            
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a helpful educational assistant providing hints."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=150
            )
            
            hint_text = response.choices[0].message.content.strip()
            return {"role": "assistant", "content": hint_text}, hint_text
            
        else:
            # Generate feedback on the user's answer
            prompt = f"""
Question: "{current_question}"
Student's answer: "{user_message}"
Topic: "{current_topic}"
Difficulty: "{current_difficulty}"

Evaluate the answer and provide constructive feedback:
1. Is the answer correct, partially correct, or incorrect?
2. What aspects of the answer are good or need improvement?
3. What key concepts should be emphasized?

For basic questions, focus on accuracy of fundamental facts.
For intermediate questions, assess application of concepts.
For advanced questions, evaluate depth of understanding and critical thinking.

Provide a brief, helpful feedback response:
"""
            
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a helpful educational assistant evaluating answers."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=250
            )
            
            feedback_text = response.choices[0].message.content.strip()
            
            # Determine if the answer was correct for tracking
            answer_quality = "incorrect"
            if "correct" in feedback_text.lower() and not "incorrect" in feedback_text.lower():
                answer_quality = "correct"
                question_state['correct_count'] = question_state.get('correct_count', 0) + 1
            elif "partially correct" in feedback_text.lower():
                answer_quality = "partially correct"
                # Count partial answers as 0.5 correct
                question_state['correct_count'] = question_state.get('correct_count', 0) + 0.5
            else:
                question_state['incorrect_count'] = question_state.get('incorrect_count', 0) + 1
                
            # Update session data
            session_data['question_state'] = question_state
            
            # Add next question prompt if appropriate
            if answer_quality == "correct":
                feedback_text += "\n\nReady for the next question? Just say 'next'."
                
            return {"role": "assistant", "content": feedback_text}, feedback_text
            
    except Exception as e:
        print(f"Error generating feedback: {str(e)}")
        response_text = "I apologize, but I'm having trouble evaluating your answer. Let's try again or move to the next question."
        return {"role": "assistant", "content": response_text}, response_text

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

@app.route('/test-tts-page')
def test_tts_page():
    """
    Serve the TTS test page
    """
    return render_template('tts_test.html')

if __name__ == '__main__':
    # Check if OpenAI API key is set
    if not openai.api_key:
        print("ERROR: OpenAI API key is not set. Please add it to your .env file.")
    else:
        print(f"OpenAI API key loaded successfully (first 5 chars): {openai.api_key[:5]}...")
        
    # Check if Cartesia API key is set
    if not CARTESIA_API_KEY:
        print("WARNING: Cartesia API key is not set. Text-to-speech will not work.")
    else:
        print(f"Cartesia API key loaded successfully (first 5 chars): {CARTESIA_API_KEY[:5]}...")
    
    # Check if SSL certificate files exist
    cert_file = 'localhost+1.pem'
    key_file = 'localhost+1-key.pem'
    ssl_files_exist = os.path.exists(cert_file) and os.path.exists(key_file)
    
    # Run with or without SSL
    try:
        if ssl_files_exist:
            print(f"SSL certificate files found. Running with HTTPS enabled.")
            print(f"Using cert: {cert_file}, key: {key_file}")
            # Use Flask-SocketIO's built-in SSL support
            socketio.run(app, 
                       debug=True, 
                       host='127.0.0.1', 
                       port=5001,
                       keyfile=key_file,
                       certfile=cert_file,
                       allow_unsafe_werkzeug=True)
        else:
            print(f"WARNING: SSL certificate files not found ({cert_file} and/or {key_file}).")
            print("Running without SSL. This may cause issues with microphone access.")
            socketio.run(app, debug=True, host='127.0.0.1', port=5001, 
                      allow_unsafe_werkzeug=True)
    except Exception as e:
        print(f"Error starting server: {e}")
        print("Falling back to basic Flask server without SocketIO")
        app.run(debug=True, host='127.0.0.1', port=5001)