import io
import os
import requests
from typing import List
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
# Replace with the actual endpoint from Mistral La Plateforme documentation
MISTRAL_OCR_ENDPOINT = os.getenv("MISTRAL_OCR_ENDPOINT", "https://platform.mistral.ai/api/v1/ocr") # Placeholder endpoint

def extract_text_from_pdf(pdf_stream: io.BytesIO) -> str:
    """Extracts text content from a PDF stream using Mistral OCR API."""
    if not MISTRAL_API_KEY:
        raise ValueError("MISTRAL_API_KEY environment variable not set.")
    if not MISTRAL_OCR_ENDPOINT:
        raise ValueError("MISTRAL_OCR_ENDPOINT environment variable not set or default incorrect.")

    headers = {
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
        # Add other necessary headers if required by Mistral API
        # "Content-Type": "application/pdf", # Often set automatically by requests
        # "Accept": "application/json",
    }

    files = {
        'file': ('input.pdf', pdf_stream, 'application/pdf')
    }

    try:
        response = requests.post(MISTRAL_OCR_ENDPOINT, headers=headers, files=files)
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)

        # --- Adjust based on Mistral's actual API response structure ---
        # Assuming the response JSON has a key like 'text' or 'extracted_text'
        response_data = response.json()
        extracted_text = response_data.get('text') # Example key
        if extracted_text is None:
             # Look for other potential keys based on documentation
             extracted_text = response_data.get('extracted_content', '')
        # --- End Adjustment Section ---

        return extracted_text

    except requests.exceptions.RequestException as e:
        print(f"Error calling Mistral OCR API: {e}")
        # Optionally, re-raise or return a specific error message
        raise ConnectionError(f"Failed to connect to Mistral OCR API: {e}")
    except Exception as e:
        print(f"An unexpected error occurred during OCR: {e}")
        raise

# Placeholder for future text processing logic
# def process_text_to_strings(text: str) -> List[str]:
#     """Processes extracted text and returns a list of strings (placeholder)."""
#     # Replace this with your actual logic to extract/generate strings
#     lines = text.split('\n')[:5] # Example: Take first 5 lines
#     return [f"Processed: {line}" for line in lines if line.strip()] + ["End of placeholder processing."]