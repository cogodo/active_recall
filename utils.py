import io
import os
import requests
from typing import List
from dotenv import load_dotenv
import re
import time
import json
from mistralai.client import MistralClient

# Load environment variables from .env file
load_dotenv()

def extract_text_from_pdf(pdf_stream: io.BytesIO) -> str:
    """Extract text from a PDF using Mistral OCR API."""
    api_key = os.getenv("MISTRAL_API_KEY")
    
    if not api_key:
        raise ValueError("MISTRAL_API_KEY environment variable is not set")
    
    try:
        client = MistralClient(api_key=api_key)
        
        # Make sure the stream is at the beginning
        pdf_stream.seek(0)
        
        # Convert BytesIO to bytes for the API
        pdf_bytes = pdf_stream.read()
        
        # Call Mistral OCR API (placeholder - implement according to Mistral's API docs)
        # This is a simplified example - you'll need to update based on actual Mistral OCR API
        # For now, returning placeholder text for testing purposes
        
        # Commenting out the actual API call until it's properly documented
        # response = client.ocr(data=pdf_bytes, model="mistral-ocr-latest")
        # extracted_text = response.get("text", "")
        
        # Placeholder implementation for testing
        extracted_text = "This is placeholder text extracted from the PDF for testing the LangGraph pipeline. " + \
                        "In a real implementation, this would be the actual text extracted via Mistral's OCR API. " + \
                        "The system would analyze the document contents and generate relevant active recall questions based on key concepts."
        
        if not extracted_text:
            print("Warning: OCR returned empty text")
            return ""
            
        return extracted_text
        
    except Exception as e:
        print(f"Error in OCR processing: {e}")
        raise e

