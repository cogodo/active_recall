#!/usr/bin/env python3
"""
Cartesia Streaming TTS Test
--------------------------
Tests streaming TTS functionality with different configurations.
"""

import os
import asyncio
import time
import argparse
from datetime import datetime
from pathlib import Path
import logging
import json
from cartesia import Cartesia

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("streaming-test")

# Test configurations
LONG_TEXT = """
Once upon a time in a land far away, there lived a curious explorer named Alex. 
Alex had spent years studying ancient maps and legends of hidden treasures. 
One day, while researching in an old library, Alex discovered a mysterious journal.
The journal contained detailed accounts of a legendary city built entirely of crystal, said to be hidden deep within uncharted mountains.
Intrigued by this discovery, Alex decided to embark on an expedition to find this mythical place.
After months of preparation, gathering supplies, and assembling a small team of trusted companions, Alex was ready for the journey.
The expedition began on a crisp autumn morning, with the team setting off into the wilderness, following the cryptic directions from the journal.
Days turned into weeks as they traversed rugged terrain, dense forests, and swift rivers.
Along the way, they encountered various challenges: unpredictable weather, dangerous wildlife, and treacherous mountain passes.
Despite these obstacles, Alex remained determined, driven by an insatiable curiosity and the promise of discovery.
One evening, as the sun began to set, casting long shadows across the landscape, the team spotted an unusual formation in the distance.
As they approached, they were astonished to see magnificent crystal structures emerging from the mountainside, glistening in the fading light.
They had found it – the legendary Crystal City, hidden from the world for centuries.
The city was even more spectacular than described in the journal. Towering crystal spires reached toward the sky, while intricate crystal pathways wound through the city.
As they explored, they discovered that the entire city functioned as a massive sundial and calendar, with the crystal structures capturing and refracting sunlight in specific patterns throughout the year.
Alex realized that this wasn't just a city – it was an ancient observatory, built by a civilization far more advanced than previously believed.
The team spent weeks documenting their findings, taking careful notes, photographs, and samples.
They discovered ancient texts and artifacts that provided insights into the civilization that had built this remarkable place.
When they finally returned to civilization, their discovery revolutionized archaeological understanding and prompted a reassessment of ancient technological capabilities.
Alex's name became synonymous with one of the greatest archaeological discoveries of the century, but for Alex, the true reward was the journey itself – the thrill of curiosity, the joy of discovery, and the wonder of uncovering a piece of history long forgotten by the world.
"""

# Configuration lists
MODELS = [
    {"name": "Sonic 2", "id": "sonic-2"}
]

VOICES = [
    {"name": "Sophie", "config": {"mode": "id", "id": "bf0a246a-8642-498a-9950-80c35e9276b5"}},
    {"name": "Savannah", "config": {"mode": "id", "id": "78ab82d5-25be-4f7d-82b3-7ad64e5b85b2"}}
]

async def test_streaming(client, voice, model, output_dir):
    """Test streaming TTS functionality with WebSocket."""
    logger.info(f"Testing streaming TTS with voice {voice['name']}, model {model['name']}")
    
    # Create unique filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    voice_name = voice["name"].lower().replace(" ", "_")
    model_name = model["name"].lower().replace(" ", "_")
    filename = f"{voice_name}_{model_name}_streaming_{timestamp}.mp3"
    filepath = output_dir / filename
    
    file_handler = open(filepath, 'wb')
    total_chunks = 0
    total_bytes = 0
    start_time = time.time()
    
    logger.info(f"Starting stream to {filepath}")
    
    try:
        # Initialize websocket client
        ws_client = client.tts.websocket()
        
        # Generate a context ID for the session
        import uuid
        context_id = f"ctx_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        
        # Send initial request
        audio_chunks = ws_client.send({
            "contextId": context_id,
            "modelId": model["id"],
            "voice": voice["config"],
            "transcript": LONG_TEXT[:500],  # Start with first part of text
            "language": "en",
            "output_format": {"container": "mp3", "sample_rate": 44100}
        })
        
        # Process initial chunks
        for chunk in audio_chunks:
            if hasattr(chunk, 'chunk') and chunk.chunk:
                file_handler.write(chunk.chunk)
                total_chunks += 1
                total_bytes += len(chunk.chunk)
        
        # Continue with remaining text in chunks of ~500 chars
        text_chunks = [LONG_TEXT[i:i+500] for i in range(500, len(LONG_TEXT), 500)]
        
        # Use continue method for remaining chunks
        continue_method = getattr(ws_client, "continue")  # Use getattr to avoid continue keyword conflict
        
        for i, text_chunk in enumerate(text_chunks):
            logger.info(f"Sending continuation chunk {i+1}/{len(text_chunks)}")
            
            continuation_chunks = continue_method({
                "contextId": context_id,
                "transcript": text_chunk
            })
            
            for chunk in continuation_chunks:
                if hasattr(chunk, 'chunk') and chunk.chunk:
                    file_handler.write(chunk.chunk)
                    total_chunks += 1
                    total_bytes += len(chunk.chunk)
                    
                    # Log progress periodically
                    if total_chunks % 10 == 0:
                        elapsed = time.time() - start_time
                        logger.info(f"Received {total_chunks} chunks ({total_bytes/1024:.2f} KB) in {elapsed:.2f}s")
        
        # Calculate final stats
        duration = time.time() - start_time
        size_kb = total_bytes / 1024
        
        logger.info(f"Stream completed: {total_chunks} chunks, {size_kb:.2f} KB in {duration:.2f}s")
        
        result = {
            "voice": voice["name"],
            "model": model["name"],
            "file": str(filepath),
            "chunks": total_chunks,
            "size_bytes": total_bytes,
            "duration_sec": duration,
            "success": True
        }
        
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"Streaming error: {e}")
        
        result = {
            "voice": voice["name"],
            "model": model["name"],
            "file": str(filepath),
            "chunks": total_chunks,
            "size_bytes": total_bytes,
            "duration_sec": duration,
            "error": str(e),
            "success": False
        }
    
    finally:
        file_handler.close()
    
    return result

async def run_streaming_tests(args):
    """Run streaming TTS tests with specified parameters."""
    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create results directory
    results_dir = Path(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    
    # Create client
    api_key = os.getenv("CARTESIA_API_KEY")
    if not api_key:
        logger.error("CARTESIA_API_KEY environment variable must be set")
        return []
    
    logger.info("Initializing Cartesia client")
    client = Cartesia(api_key=api_key)
    
    # Select test parameters
    voices_to_test = VOICES
    if args.voice:
        voices_to_test = [v for v in VOICES if v["name"].lower() == args.voice.lower()]
        if not voices_to_test:
            logger.warning(f"Voice '{args.voice}' not found. Using all available voices.")
            voices_to_test = VOICES
    
    models_to_test = MODELS
    if args.model:
        models_to_test = [m for m in MODELS if m["name"].lower() == args.model.lower()]
        if not models_to_test:
            logger.warning(f"Model '{args.model}' not found. Using all available models.")
            models_to_test = MODELS
    
    # Run tests
    results = []
    total_tests = len(voices_to_test) * len(models_to_test)
    
    logger.info(f"Starting streaming tests for {total_tests} configurations")
    
    test_count = 0
    success_count = 0
    
    for voice in voices_to_test:
        for model in models_to_test:
            test_count += 1
            logger.info(f"Test {test_count}/{total_tests}: {voice['name']}, {model['name']}")
            
            result = await test_streaming(client, voice, model, output_dir)
            results.append(result)
            
            if result["success"]:
                success_count += 1
    
    # Write results to JSON file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = results_dir / f"streaming_test_results_{timestamp}.json"
    
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    # Log summary
    logger.info(f"\n=== Test Summary ===")
    logger.info(f"Total tests: {test_count}")
    logger.info(f"Successful: {success_count}")
    logger.info(f"Failed: {test_count - success_count}")
    logger.info(f"Success rate: {(success_count / test_count) * 100:.1f}%")
    
    if success_count > 0:
        # Calculate averages for successful tests
        avg_chunks = sum(r["chunks"] for r in results if r["success"]) / success_count
        avg_size = sum(r["size_bytes"] for r in results if r["success"]) / success_count / 1024
        avg_duration = sum(r["duration_sec"] for r in results if r["success"]) / success_count
        
        logger.info(f"Average chunks: {avg_chunks:.1f}")
        logger.info(f"Average file size: {avg_size:.2f} KB")
        logger.info(f"Average streaming time: {avg_duration:.2f} seconds")
    
    logger.info(f"Output files saved to: {output_dir.absolute()}")
    logger.info(f"Results saved to: {results_file}")
    
    return results

def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Test Cartesia streaming TTS")
    parser.add_argument("--voice", help="Specific voice to test")
    parser.add_argument("--model", help="Specific model to test")
    parser.add_argument("--output-dir", default="streaming_samples", help="Directory for output files")
    parser.add_argument("--results-dir", default="test_results", help="Directory for test results")
    
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    asyncio.run(run_streaming_tests(args)) 