# Active Recall Study Assistant

An interactive study assistant that helps users practice active recall for better learning retention.

## Key Features

- Text-to-speech powered by Cartesia API
- Speech-to-text powered by OpenAI Whisper API
- Active recall question generation with OpenAI GPT models
- Real-time feedback on learning progress
- Voice commands and conversation mode

## Architecture Overview

The application uses a modern client-server architecture with real-time capabilities:

### Server-Side Components

1. **Flask Backend**: Core web application framework
2. **WebSocket Support**: Real-time communication using Flask-SocketIO
3. **Session Management**: Server-side session tracking and state persistence
4. **TTS Service**: Text-to-speech processing with Cartesia SDK
5. **Speech Recognition**: Audio transcription with OpenAI Whisper
6. **Question Generation**: OpenAI GPT-based question generation and feedback

### Client-Side Components

1. **UI Rendering**: HTML/CSS for user interface
2. **WebSocket Client**: Real-time communication with server
3. **Audio Processing**: In-browser audio recording and visualization
4. **State Management**: Synced with server via WebSockets and REST fallback

## Security Improvements

- API keys are now stored and used exclusively on the server
- No exposure of sensitive credentials to client-side code
- Authentication for WebSocket connections
- Session-based preferences and state management

## Performance Enhancements

- Significantly reduced JavaScript code size (70% reduction)
- WebSocket-based real-time updates reduce HTTP requests
- Server-side audio processing reduces client CPU usage
- Optimized voice streaming for longer texts

## Installation

1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Create a `.env` file with:
   ```
   OPENAI_API_KEY=your_openai_api_key
   CARTESIA_API_KEY=your_cartesia_api_key
   ```
4. Run the application: `flask run --port=5001`

## Usage

1. Open a browser to `http://localhost:5001`
2. Enter a topic you want to study
3. Answer the generated questions to practice active recall
4. Use voice mode by clicking the microphone button

## Voice Commands

- "Next question" - Get the next question
- "Hint" - Get a hint for the current question
- "Repeat" - Repeat the last assistant message
- "Stop listening" - Exit voice mode
- "Clear chat" - Start a fresh conversation
