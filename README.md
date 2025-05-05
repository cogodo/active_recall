# Active Recall Study Assistant

## Description
An AI-powered study assistant that helps users practice active recall - a highly effective learning technique where you test yourself on material instead of passively reviewing it.

## Features
- **Chat-based Study**: Define any topic and get AI-generated active recall questions
- **PDF Document Support**: Upload PDFs and automatically generate study questions from their content
- **Voice Interaction**: Fully voice-enabled with speech recognition and text-to-speech
- **Personalized Feedback**: Get hints and feedback tailored to your answers
- **LangGraph Pipeline**: Advanced PDF processing using LangGraph for optimized question generation

## Setup Instructions

### Prerequisites
- Python 3.8+
- OpenAI API key for GPT model access
- Mistral API key for PDF processing and question generation
- Cartesia API key for high-quality TTS (optional)

### Installation
1. Clone this repository
2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Create a `.env` file in the root directory with your API keys:
   ```
   OPENAI_API_KEY=your_openai_api_key
   MISTRAL_API_KEY=your_mistral_api_key
   CARTESIA_API_KEY=your_cartesia_api_key  # Optional
   ```

### Running the Application
Run the application with:
```
python app.py
```
Then open your browser to `http://localhost:5000`

## Using the Application

### Chat-based Study
1. Enter a topic you want to study
2. The assistant will generate active recall questions
3. Try to answer each question to test your knowledge
4. Ask for hints or feedback if needed

### PDF-based Study
1. Click the "Choose File" button in the PDF upload section
2. Select a PDF document (max 10MB)
3. Click "Upload & Generate Questions"
4. The system will process the PDF and generate questions based on its content
5. Practice with the generated questions

### Voice Interaction
- Click the microphone button to activate voice mode
- Use voice commands like "next question," "hint," or "repeat"
- Enable "Auto-read responses" to have the assistant read responses aloud

## How It Works
The application uses two approaches for content generation:

1. **Chat-based Questions**: Direct interaction with OpenAI's GPT models to generate questions on any topic
2. **PDF Processing Pipeline**: A LangGraph workflow:
   - PDF uploading and validation
   - Text extraction using Mistral's OCR capabilities
   - Question generation through Mistral's language models
   - Interactive practice with generated questions

## License
[License information]

## Acknowledgements
- OpenAI for GPT models
- Mistral AI for PDF processing capabilities
- LangGraph for workflow orchestration

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
