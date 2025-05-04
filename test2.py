from cartesia import Cartesia
from cartesia.tts import OutputFormat_Raw, TtsRequestIdSpecifier
import os

client = Cartesia(
    api_key=os.getenv("CARTESIA_API_KEY"),
)
client.tts.bytes(
    model_id="sonic-2",
    transcript="Hello, world!",
    voice={
        "mode": "id",
        "id": "694f9389-aac1-45b6-b726-9d9369183238",
    },
    language="en",
    output_format={
        "container": "mp4",
        "sample_rate": 44100,
        "encoding": "pcm_f32le",
    },
)