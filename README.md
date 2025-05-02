# PDF Text Extractor

A simple Flask web application that allows users to upload PDF files and extract text from them.

## Features

- Upload PDF files through the web interface
- Extract text from PDF files (works on text-based PDFs, not scanned documents)
- View extracted text by page
- Simple and clean user interface

## Requirements

- Python 3.6+
- Flask
- PyPDF2

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

## Running the Application

1. Start the Flask server:
   ```
   python app.py
   ```

2. Open your web browser and navigate to:
   ```
   http://localhost:5001
   ```

3. Upload a PDF file and the extracted text will be displayed

## Notes

- The application has a 16MB file size limit for uploads (can be modified in app.py)
- This application works best with PDFs that contain actual text data, not scanned images
- For scanned documents, you would need to incorporate OCR (Optical Character Recognition) functionality

## Structure

- `app.py` - Main Flask application
- `templates/index.html` - HTML template for the web interface
- `uploads/` - Temporary storage for uploaded PDFs (created automatically)
- `requirements.txt` - Python dependencies
