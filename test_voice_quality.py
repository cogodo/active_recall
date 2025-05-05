#!/usr/bin/env python3
"""
Cartesia TTS Voice Quality Test
------------------------------
Tests voice quality across different configurations and saves samples.
"""

import os
import time
import uuid
import argparse
from pathlib import Path
from cartesia import Cartesia

# Test phrases designed to exercise various aspects of TTS
TEST_PHRASES = [
    "Hello world! This is a simple test of the text to speech system.",
    "Do you hear the people sing? Singing the song of angry men.",
    "The quick brown fox jumps over the lazy dog.",
    "She sells seashells by the seashore. Peter Piper picked a peck of pickled peppers.",
    "In 1492, Columbus sailed the ocean blue. On July 20, 1969, humans first landed on the moon.",
    "How much wood would a woodchuck chuck if a woodchuck could chuck wood?",
    "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore.",
    "Testing various punctuation: comma, period. Question mark? Exclamation point! Semi-colon; colon:"
]

# Test configurations
VOICES = [
    {"name": "Sophie", "config": {"mode": "id", "id": "bf0a246a-8642-498a-9950-80c35e9276b5"}},
    {"name": "Savannah", "config": {"mode": "id", "id": "78ab82d5-25be-4f7d-82b3-7ad64e5b85b2"}},
    {"name": "Brooke", "config": {"mode": "id", "id": "6f84f4b8-58a2-430c-8c79-688dad597532"}}
]

MODELS = [
    {"name": "Sonic 2", "id": "sonic-2"}
]

OUTPUT_FORMATS = [
    {"name": "MP3 Default", "config": {"container": "mp3", "sample_rate": 44100}},
    {"name": "WAV 44.1kHz", "config": {"container": "wav", "sample_rate": 44100, "encoding": "pcm_f32le"}}
]

def get_cartesia_client():
    """Create and return a Cartesia client."""
    api_key = os.getenv("CARTESIA_API_KEY")
    if not api_key:
        raise ValueError("CARTESIA_API_KEY environment variable must be set")
    
    return Cartesia(api_key=api_key)

def generate_sample(client, text, voice, model, output_format, output_dir):
    """Generate a TTS sample with the given parameters."""
    # Create a filename based on parameters
    voice_name = voice["name"].lower().replace(" ", "_")
    model_name = model["name"].lower().replace(" ", "_")
    format_name = output_format["name"].lower().replace(" ", "_")
    container = output_format["config"]["container"]
    
    # Truncate text for filename
    text_snippet = text[:20].replace(" ", "_").replace("?", "").replace("!", "").replace(".", "")
    
    # Create a unique filename
    filename = f"{voice_name}_{model_name}_{format_name}_{text_snippet}.{container}"
    filepath = output_dir / filename
    
    print(f"Generating: {filename}")
    start_time = time.time()
    
    try:
        # Generate audio
        audio_generator = client.tts.bytes(
            model_id=model["id"],
            transcript=text,
            voice=voice["config"],
            language="en",
            output_format=output_format["config"]
        )
        
        # Collect audio data
        audio_data = b""
        for chunk in audio_generator:
            audio_data += chunk
        
        # Save to file
        with open(filepath, 'wb') as f:
            f.write(audio_data)
        
        # Calculate performance metrics
        duration = time.time() - start_time
        size_kb = len(audio_data) / 1024
        
        print(f"  ✓ Generated in {duration:.2f}s, size: {size_kb:.2f}KB")
        
        return {
            "file": filepath,
            "size_bytes": len(audio_data),
            "duration_sec": duration,
            "success": True
        }
        
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return {
            "file": filepath,
            "error": str(e),
            "success": False
        }

def run_voice_quality_tests(args):
    """Run voice quality tests with specified parameters."""
    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create client
    client = get_cartesia_client()
    
    # Select test parameters
    voices_to_test = VOICES
    if args.voice:
        voices_to_test = [v for v in VOICES if v["name"].lower() == args.voice.lower()]
        if not voices_to_test:
            print(f"Warning: Voice '{args.voice}' not found. Using all available voices.")
            voices_to_test = VOICES
    
    models_to_test = MODELS
    if args.model:
        models_to_test = [m for m in MODELS if m["name"].lower() == args.model.lower()]
        if not models_to_test:
            print(f"Warning: Model '{args.model}' not found. Using all available models.")
            models_to_test = MODELS
    
    formats_to_test = OUTPUT_FORMATS
    if args.format:
        formats_to_test = [f for f in OUTPUT_FORMATS if f["name"].lower() == args.format.lower()]
        if not formats_to_test:
            print(f"Warning: Format '{args.format}' not found. Using all available formats.")
            formats_to_test = OUTPUT_FORMATS
    
    # Select phrases
    phrases_to_test = TEST_PHRASES
    if args.phrase_index is not None:
        if 0 <= args.phrase_index < len(TEST_PHRASES):
            phrases_to_test = [TEST_PHRASES[args.phrase_index]]
        else:
            print(f"Warning: Phrase index {args.phrase_index} out of range. Using all phrases.")

    if args.custom_phrase:
        phrases_to_test = [args.custom_phrase]
    
    # Run tests
    results = []
    total_tests = len(voices_to_test) * len(models_to_test) * len(formats_to_test) * len(phrases_to_test)
    
    print(f"\n=== Voice Quality Test ===")
    print(f"Running {total_tests} tests with:")
    print(f"  - {len(voices_to_test)} voice(s)")
    print(f"  - {len(models_to_test)} model(s)")
    print(f"  - {len(formats_to_test)} format(s)")
    print(f"  - {len(phrases_to_test)} phrase(s)")
    print(f"Output directory: {output_dir.absolute()}")
    print("\n")
    
    # Track statistics
    test_count = 0
    success_count = 0
    
    for voice in voices_to_test:
        for model in models_to_test:
            for output_format in formats_to_test:
                for text in phrases_to_test:
                    test_count += 1
                    print(f"Test {test_count}/{total_tests}: {voice['name']}, {model['name']}, {output_format['name']}")
                    result = generate_sample(
                        client, text, voice, model, output_format, output_dir
                    )
                    
                    results.append({
                        "voice": voice["name"],
                        "model": model["name"],
                        "format": output_format["name"],
                        "text": text[:50] + "..." if len(text) > 50 else text,
                        **result
                    })
                    
                    if result["success"]:
                        success_count += 1
    
    # Print summary
    print("\n=== Test Summary ===")
    print(f"Total tests: {test_count}")
    print(f"Successful: {success_count}")
    print(f"Failed: {test_count - success_count}")
    print(f"Success rate: {(success_count / test_count) * 100:.1f}%")
    
    if success_count > 0:
        # Calculate averages for successful tests
        avg_size = sum(r["size_bytes"] for r in results if r["success"]) / success_count / 1024
        avg_duration = sum(r["duration_sec"] for r in results if r["success"]) / success_count
        
        print(f"Average file size: {avg_size:.2f} KB")
        print(f"Average generation time: {avg_duration:.2f} seconds")
    
    print(f"\nOutput files saved to: {output_dir.absolute()}")
    
    return results

def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Test Cartesia TTS voice quality")
    parser.add_argument("--voice", help="Specific voice to test")
    parser.add_argument("--model", help="Specific model to test")
    parser.add_argument("--format", help="Specific output format to test")
    parser.add_argument("--phrase-index", type=int, help="Index of specific test phrase to use")
    parser.add_argument("--custom-phrase", help="Custom phrase to test")
    parser.add_argument("--output-dir", default="voice_samples", help="Directory for output files")
    
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    run_voice_quality_tests(args) 