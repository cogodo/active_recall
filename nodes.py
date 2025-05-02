from typing import Dict, Any, List
import io
import os

from mistralai.client import MistralClient

from utils import extract_text_from_pdf

# Define the state for the graph
class GraphState(Dict[str, Any]):
    pdf_stream: io.BytesIO = None
    extracted_text: str = None
    generated_questions: List[str] = None
    error: str = None

def parse_pdf_node(state: GraphState) -> GraphState:
    """Node to parse the PDF content from the stream via Mistral OCR API."""
    print("--- Executing Node: parse_pdf_node ---")
    pdf_stream = state.get("pdf_stream")
    if not pdf_stream:
        return {**state, "error": "PDF stream not found in state"}

    try:
        # Ensure the stream is at the beginning if it was read before
        pdf_stream.seek(0)
        extracted_text = extract_text_from_pdf(pdf_stream)
        print(f"Extracted text length: {len(extracted_text)}")
        # Make sure text extraction didn't yield an empty result implicitly
        if not extracted_text or extracted_text.isspace():
             return {**state, "error": "OCR processing returned empty text."}
        return {**state, "extracted_text": extracted_text}
    except Exception as e:
        print(f"Error during PDF processing (API call): {e}")
        error_message = f"Failed to process PDF via external service: {type(e).__name__}"
        return {**state, "error": error_message}

def generate_questions_node(state: GraphState) -> GraphState:
    """Node to generate active recall questions from the extracted text using Mistral."""
    print("--- Executing Node: generate_questions_node ---")
    extracted_text = state.get("extracted_text")
    api_key = os.getenv("MISTRAL_API_KEY")
    model = "mistral-small-latest"

    if state.get("error"):
        print("Skipping question generation due to upstream error.")
        return state

    if not extracted_text:
        return {**state, "error": "Extracted text not found in state for question generation"}

    if not api_key:
        return {**state, "error": "MISTRAL_API_KEY environment variable not set."}

    try:
        client = MistralClient(api_key=api_key)

        # Limit text length to avoid excessive token usage/costs
        # Consider more sophisticated chunking/summarization for very long docs
        max_chars = 4000
        text_for_prompt = extracted_text[:max_chars]
        if len(extracted_text) > max_chars:
            print(f"Warning: Truncating text for prompt to {max_chars} characters.")

        prompt = f"""
Analyze the following text extracted from a document. Based *only* on this text, generate a concise list of 3-5 important questions that would help someone actively recall the key information presented. Frame the questions clearly and directly related to the text content. Ensure the questions cover different aspects or key points of the provided text.

Text:
---
{text_for_prompt}
---

Output *only* the questions, each on a new line. Do not include numbering, bullet points, introductory phrases, or concluding remarks. Just the questions themselves.
"""

        messages = [{"role": "user", "content": prompt}]

        print(f"Calling Mistral model ({model}) for question generation...")
        chat_response = client.chat(
            model=model,
            messages=messages,
            temperature=0.3 # Lower temperature for more focused output
        )

        if not chat_response.choices:
             return {**state, "error": "Mistral API returned no choices for question generation."}

        raw_questions = chat_response.choices[0].message.content
        # Parse the response into a list of strings, removing empty lines
        generated_questions = [q.strip() for q in raw_questions.split('\n') if q.strip()]

        if not generated_questions:
            print("Warning: Mistral response parsed into an empty list of questions.")
            # You might want to return an error or a default message here
            return {**state, "error": "Failed to parse valid questions from the model response."}

        print(f"Generated {len(generated_questions)} questions.")
        # Clear any previous error if this step succeeded
        return {**state, "generated_questions": generated_questions, "error": None}

    except Exception as e:
        print(f"Error generating questions with Mistral: {e}")
        # Specific error handling for API vs other issues could be added here
        return {**state, "error": f"Failed during question generation: {type(e).__name__}"} 