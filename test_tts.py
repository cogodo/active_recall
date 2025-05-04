"""
Test script for Cartesia TTS API
Usage: python test_tts.py "Text to convert to speech"
"""

import os
import sys
import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get Cartesia API key
CARTESIA_API_KEY = os.getenv("CARTESIA_API_KEY", "")

def test_cartesia_tts(text, output_file="test_speech.mp3"):
    """Test Cartesia TTS API directly"""
    if not CARTESIA_API_KEY:
        print("ERROR: Cartesia API key not found. Set it in the .env file.")
        return False
        
    print(f"Using Cartesia API key: {CARTESIA_API_KEY[:5]}...")
    print(f"Converting text: '{text}'")
    
    # Call Cartesia API
    url = "https://api.cartesia.ai/v1/tts"
    headers = {
        "Authorization": f"Bearer {CARTESIA_API_KEY}",
        "Content-Type": "application/json",
        "Cartesia-Version": "2025-04-16"
    }
    payload = {
        "modelId": "sonic-2",
        "transcript": text,
        "voiceId": "nova",
        "language": "en",
        "outputFormat": {
            "container": "mp3",
            "sampleRate": 24000,
            "bitRate": 128000
        }
    }
    
    try:
        print(f"Sending request to {url}...")
        print(f"With headers: {headers}")
        print(f"And payload: {payload}")
        
        response = requests.post(url, json=payload, headers=headers)
        
        print(f"Response status: {response.status_code}")
        print(f"Response headers: {dict(response.headers)}")
        
        if response.status_code != 200:
            print(f"ERROR: API returned {response.status_code}")
            print(f"Response body: {response.text}")
            return False
            
        # Save the audio to a file
        with open(output_file, 'wb') as f:
            f.write(response.content)
            
        print(f"Audio saved to {output_file} ({len(response.content)} bytes)")
        return True
        
    except Exception as e:
        print(f"ERROR: {str(e)}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_tts.py \"Text to convert to speech\"")
        sys.exit(1)
        
    text = sys.argv[1]
    success = test_cartesia_tts(text)
    
    if success:
        print("Test completed successfully!")
    else:
        print("Test failed.")
        sys.exit(1) 