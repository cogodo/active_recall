# Active Recall Study Assistant

A conversational web application that helps users practice active recall by generating topic-specific questions and providing feedback on answers.

## Features

- Chat-based interface for topic identification and question generation
- Intelligent analysis of user study goals
- Generation of high-quality active recall questions tailored to specific topics
- Feedback on user responses and hints when requested
- Ability to switch topics seamlessly within the conversation
- Session management to maintain conversation context

## What is Active Recall?

Active recall is a learning technique that involves actively stimulating memory during the learning process. It's one of the most effective study methods because it strengthens neural connections and improves long-term retention. This application helps users practice active recall by generating relevant questions about their chosen topics.

## Requirements

- Python 3.6+
- Flask
- OpenAI API key (GPT-4 access recommended)

## Installation

1. Clone this repository or download the files

2. Create a virtual environment (recommended):
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install the required packages:
   ```
   pip install -r requirements.txt
   ```

4. Set up your OpenAI API key:
   - Create a `.env` file in the project root 
   - Add your OpenAI API key:
     ```
     OPENAI_API_KEY=your_api_key_here
     ```

## Running the Application

1. Start the Flask server:
   ```
   python app.py
   ```

2. Open your web browser and navigate to:
   ```
   http://localhost:5001
   ```

3. Start chatting with the assistant by telling it what topic you want to review
4. Try to answer the generated questions to practice active recall
5. Ask for hints or feedback if needed
6. Change topics any time by asking to review something new

## How it Works

1. The user tells the assistant what topic they want to review
2. The application identifies the specific topic using GPT-4
3. It generates 10 active recall questions tailored to that topic
4. Questions are displayed in the sidebar for easy reference
5. The user can discuss the topic and attempt to answer questions
6. The assistant provides helpful feedback and encouragement
7. The user can change topics at any time to study something new

## Technology

- **Flask** for the web server and session management
- **OpenAI GPT-4** for intelligent conversation and question generation
- **JavaScript** for the dynamic chat interface
- **Flask Sessions** for maintaining conversation state
