import os
from flask import Flask, request, render_template, jsonify
import PyPDF2  # PyPDF2 instead of PyMuPDF

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
            text = extract_text_from_pdf(filepath)
            
            # Optional: Delete the file after processing
            os.remove(filepath)
            
            return jsonify({
                'success': True,
                'text': text,
                'pages': len(text) if isinstance(text, list) else 1
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

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001) 