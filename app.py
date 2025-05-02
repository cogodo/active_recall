import os
from flask import Flask, request, render_template, jsonify
import PyPDF2
import openai
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Initialize OpenAI API
openai.api_key = os.getenv("OPENAI_API_KEY")

app = Flask(__name__)

# Configure upload folder
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    # Check if the post request has the file part
    if 'pdf_file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['pdf_file']
    
    # If user does not select file, browser also
    # submit an empty part without filename
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if file and file.filename.endswith('.pdf'):
        # Save file temporarily
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(filepath)
        
        try:
            # Extract text from PDF
            text_by_page = extract_text_from_pdf(filepath)
            
            # Concatenate text from all pages with page markers
            full_text = ""
            for i, page_text in enumerate(text_by_page):
                full_text += f"Page {i+1}:\n{page_text}\n\n"
            
            # Generate questions based on the text
            questions = generate_questions(full_text)
            
            # Optional: Delete the file after processing
            os.remove(filepath)
            
            return jsonify({
                'success': True,
                'text': text_by_page,
                'questions': questions,
                'pages': len(text_by_page)
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    else:
        return jsonify({'error': 'File must be a PDF'}), 400

def extract_text_from_pdf(pdf_path):
    """Extract text from each page of the PDF using PyPDF2."""
    text_by_page = []
    
    with open(pdf_path, 'rb') as file:
        reader = PyPDF2.PdfReader(file)
        
        for page_num in range(len(reader.pages)):
            page = reader.pages[page_num]
            text = page.extract_text()
            text_by_page.append(text)
    
    return text_by_page

def generate_questions(text):
    """Generate 10 active recall questions based on the provided text."""
    # Truncate text if it's too long (OpenAI has token limits)
    max_length = 12000  # Approximation for 3000 tokens
    if len(text) > max_length:
        text = text[:max_length] + "..."
    
    try:
        # Using the cheapest model (text-ada-001 is deprecated, using gpt-3.5-turbo)
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an education assistant that creates active recall questions based on text content."},
                {"role": "user", "content": f"Based on the following text, generate 10 active recall questions that test understanding of the key concepts. Format as a JSON array with just the questions. The text is:\n\n{text}"}
            ],
            temperature=0.7,
            max_tokens=600
        )
        
        # Extract questions from the response
        result = response.choices[0].message.content.strip()
        
        # Simple parsing for questions if not proper JSON
        if result.startswith("[") and result.endswith("]"):
            # Try to parse as JSON
            import json
            try:
                questions = json.loads(result)
                return questions
            except:
                pass
        
        # Fallback: look for numbered questions (1. Question)
        import re
        questions = re.findall(r'\d+[\.\)]\s*(.*?)(?=\d+[\.\)]|$)', result, re.DOTALL)
        if questions and len(questions) > 0:
            return [q.strip() for q in questions]
        
        # Second fallback: split by newlines and take non-empty lines
        questions = [line.strip() for line in result.split('\n') if line.strip()]
        if len(questions) >= 5:  # If we have at least 5 lines, assume they're questions
            return questions[:10]  # Limit to 10 questions
        
        # Last resort: just return the raw text split into chunks
        return [result]
        
    except Exception as e:
        print(f"Error generating questions: {str(e)}")
        return ["Error generating questions. Please check your OpenAI API key and try again."]

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001) 