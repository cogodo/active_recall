import os
from cartesia import Cartesia

# Verify that API key is available
api_key = os.getenv('CARTESIA_API_KEY')
if not api_key:
    raise ValueError('CARTESIA_API_KEY environment variable must be set')

# Initialize client
client = Cartesia(api_key=api_key)

# Generate TTS audio
print('Generating TTS audio...')
audio_result = client.tts.bytes(
    model_id='sonic-2',
    transcript='Hello, world!',
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

# Collect audio data
print('Collecting audio chunks...')
audio_data = b''
for chunk in audio_result:
    audio_data += chunk

# Save to file
output_file = 'compatibility_test/test2_output.mp3'
print(f'Saving audio to {output_file}...')
with open(output_file, 'wb') as f:
    f.write(audio_data)

print(f'Audio saved successfully to {output_file}')