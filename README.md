# PDF Text Extractor with Active Recall

A web application that extracts text from PDF files and uses OpenAI to generate active recall questions based on the content.

## Features

- Upload PDF files through the web interface
- Extract text from PDF files (works on text-based PDFs, not scanned documents)
- Generate 10 active recall questions automatically using OpenAI
- View extracted text and questions side by side
- Simple and modern user interface

## Requirements

- Python 3.6+
- Flask
- PyPDF2
- OpenAI API key

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
   - Sign up for an OpenAI API key at https://platform.openai.com/
   - Copy the file `.env.example` to `.env` 
   - Add your OpenAI API key to the `.env` file:
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

3. Upload a PDF file and wait for the extraction and question generation to complete
4. Review the extracted text and the generated active recall questions

## How it Works

1. PDF files are uploaded to the server
2. PyPDF2 extracts text from each page of the PDF
3. The extracted text is sent to OpenAI's GPT-3.5-Turbo model (the most cost-effective option)
4. The AI generates 10 active recall questions based on the content
5. Both the text and questions are displayed to the user

## Cost Considerations

- OpenAI's GPT-3.5-Turbo is used as it's the most cost-effective model with good results
- The application limits the amount of text sent to OpenAI to control costs
- Each query typically costs less than $0.01 USD

## Structure

- `app.py` - Main Flask application with PDF extraction and OpenAI integration
- `templates/index.html` - HTML template for the web interface
- `uploads/` - Temporary storage for uploaded PDFs (created automatically)
- `requirements.txt` - Python dependencies
- `.env` - Environment variables file (you need to create this from .env.example)

## Notes

- The application has a 16MB file size limit for uploads (can be modified in app.py)
- This application works best with PDFs that contain actual text data, not scanned images
- For scanned documents, you would need to incorporate OCR (Optical Character Recognition)
- The text sent to OpenAI is limited to approximately 3000 tokens to control costs
