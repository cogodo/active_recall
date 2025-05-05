import os
from cartesia import Cartesia

# Get API key
api_key = os.getenv('CARTESIA_API_KEY')
if not api_key:
    raise ValueError('CARTESIA_API_KEY environment variable must be set')

# Initialize client
client = Cartesia(api_key=api_key)

# Generate TTS audio with MP3 format
print('Generating MP3 with test2.py...')
audio_result = client.tts.bytes(
    model_id='sonic-2',
    transcript='This is a test of the MP3 output consistency.',
    voice={
        'mode': 'id',
        'id': 'bf0a246a-8642-498a-9950-80c35e9276b5',  # Sophie
    },
    language='en',
    output_format={
        'container': 'mp3',
        'sample_rate': 44100,
    }
)

# Collect and save audio
print('Collecting audio chunks...')
audio_data = b''
for chunk in audio_result:
    audio_data += chunk

print('Saving to consistency_test/test2_output.mp3...')
with open('consistency_test/test2_output.mp3', 'wb') as f:
    f.write(audio_data)

print('✓ MP3 saved successfully to consistency_test/test2_output.mp3')