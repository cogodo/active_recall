import os
import cartesia
import traceback
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get Cartesia API key
CARTESIA_API_KEY = os.getenv("CARTESIA_API_KEY", "")

def test_cartesia_client():
    """Test Cartesia client directly"""
    if not CARTESIA_API_KEY:
        print("ERROR: Cartesia API key not found. Set it in the .env file.")
        return False
        
    print(f"Using Cartesia API key: {CARTESIA_API_KEY[:5]}...")
    
    client = cartesia.Cartesia(api_key=CARTESIA_API_KEY)
    
    try:
        # Try with onyx voice which might be more widely supported
        voice = {"mode": "id", "id": "onyx"}  
        output_format = {"container": "mp3", "sample_rate": 24000, "bit_rate": 64000}
        
        print("Requesting TTS with:")
        print(f"  Voice: {voice}")
        print(f"  Model: sonic-2")
        print(f"  Output format: {output_format}")
        
        audio_generator = client.tts.bytes(
            transcript="Hello, this is a test",
            model_id="sonic-2",
            voice=voice,
            language="en",
            output_format=output_format
        )
        
        # Collect all audio chunks
        audio_bytes = b"".join(list(audio_generator))
        
        # Save the audio
        with open("test_direct.mp3", "wb") as f:
            f.write(audio_bytes)
            
        print(f"Audio saved to test_direct.mp3 ({len(audio_bytes)} bytes)")
        return True
        
    except Exception as e:
        print(f"ERROR: {str(e)}")
        print("Full error:")
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_cartesia_client()
    
    if success:
        print("Test completed successfully!")
    else:
        print("Test failed.") 