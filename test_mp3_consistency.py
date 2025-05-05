#!/usr/bin/env python3
"""
MP3 Output Consistency Test
--------------------------
Tests MP3 output consistency between test2.py and test_voice_quality.py.
"""

import os
import sys
import subprocess
import logging
import filecmp
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("mp3-consistency")

def ensure_directory(dir_path):
    """Ensure the directory exists."""
    Path(dir_path).mkdir(exist_ok=True)
    return Path(dir_path)

def run_test2_modified():
    """Run the modified test2.py script to generate MP3 output."""
    output_dir = ensure_directory("consistency_test")
    output_file = output_dir / "test2_output.mp3"
    
    # Create the modified test2.py
    script_path = create_mp3_test2_script(output_file)
    if not script_path:
        return None
    
    # Run the script
    logger.info(f"Running modified test2.py to generate {output_file}...")
    
    try:
        cmd = [sys.executable, script_path]
        process = subprocess.run(cmd, check=True, capture_output=True)
        logger.info("✓ test2.py MP3 generation successful")
        
        if process.stdout:
            logger.info(f"Output: {process.stdout.decode('utf-8').strip()}")
        
        return output_file
    except subprocess.CalledProcessError as e:
        logger.error(f"Error running test2.py: {e}")
        if e.stdout:
            logger.info(f"Output: {e.stdout.decode('utf-8').strip()}")
        if e.stderr:
            logger.error(f"Error: {e.stderr.decode('utf-8').strip()}")
        return None

def create_mp3_test2_script(output_file):
    """Create the test2 script for MP3 output."""
    script_path = "test2_mp3_test.py"
    
    try:
        # Create a script that works with the current SDK version
        script_content = [
            "import os",
            "from cartesia import Cartesia",
            "",
            "# Get API key",
            "api_key = os.getenv('CARTESIA_API_KEY')",
            "if not api_key:",
            "    raise ValueError('CARTESIA_API_KEY environment variable must be set')",
            "",
            "# Initialize client",
            "client = Cartesia(api_key=api_key)",
            "",
            "# Generate TTS audio with MP3 format",
            "print('Generating MP3 with test2.py...')",
            "audio_result = client.tts.bytes(",
            "    model_id='sonic-2',",
            "    transcript='This is a test of the MP3 output consistency.',",
            "    voice={",
            "        'mode': 'id',",
            "        'id': 'bf0a246a-8642-498a-9950-80c35e9276b5',  # Sophie",
            "    },",
            "    language='en',",
            "    output_format={",
            "        'container': 'mp3',",
            "        'sample_rate': 44100,",
            "    }",
            ")",
            "",
            "# Collect and save audio",
            "print('Collecting audio chunks...')",
            "audio_data = b''",
            "for chunk in audio_result:",
            "    audio_data += chunk",
            "",
            f"print('Saving to {output_file}...')",
            f"with open('{output_file}', 'wb') as f:",
            "    f.write(audio_data)",
            "",
            f"print('✓ MP3 saved successfully to {output_file}')"
        ]
        
        with open(script_path, "w") as f:
            f.write("\n".join(script_content))
        
        logger.info(f"Created test2 MP3 script: {script_path}")
        return script_path
    
    except Exception as e:
        logger.error(f"Error creating test2 MP3 script: {e}")
        return None

def run_voice_quality_mp3():
    """Run test_voice_quality.py with MP3 format."""
    output_dir = ensure_directory("consistency_test")
    
    logger.info("Running test_voice_quality.py with MP3 format...")
    
    cmd = [
        sys.executable, 
        "test_voice_quality.py",
        "--voice", "Sophie",
        "--model", "Sonic 2",
        "--format", "MP3 Default",
        "--custom-phrase", "This is a test of the MP3 output consistency.",
        "--output-dir", str(output_dir)
    ]
    
    try:
        process = subprocess.run(cmd, check=True, capture_output=True)
        logger.info("✓ test_voice_quality.py MP3 generation successful")
        
        # Find MP3 file that's not test2_output.mp3
        mp3_files = []
        for file in output_dir.glob("*.mp3"):
            if file.name != "test2_output.mp3":
                mp3_files.append(file)
                
        if not mp3_files:
            mp3_files = list(output_dir.glob("sophie_sonic_2_mp3_*.mp3"))
            
        if not mp3_files:
            logger.error("No MP3 file found from test_voice_quality.py")
            return None
        
        voice_quality_file = mp3_files[0]
        logger.info(f"Found MP3 file: {voice_quality_file}")
        return voice_quality_file
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Error running test_voice_quality.py: {e}")
        if e.stdout:
            logger.info(f"Output: {e.stdout.decode('utf-8').strip()}")
        if e.stderr:
            logger.error(f"Error: {e.stderr.decode('utf-8').strip()}")
        return None

def compare_mp3_files(file1, file2):
    """Compare the two MP3 files."""
    if not file1 or not file2:
        logger.error("Cannot compare files: one or both files missing")
        return False
    
    if not (Path(file1).exists() and Path(file2).exists()):
        logger.error("One or both MP3 files don't exist")
        return False
    
    # Get file sizes
    size1 = Path(file1).stat().st_size
    size2 = Path(file2).stat().st_size
    
    logger.info(f"test2.py output size: {size1 / 1024:.2f} KB")
    logger.info(f"test_voice_quality.py output size: {size2 / 1024:.2f} KB")
    
    # Size ratio
    if size1 > 0 and size2 > 0:
        ratio = max(size1, size2) / min(size1, size2)
        logger.info(f"Size ratio: {ratio:.2f}x")
        
        # Check if sizes are reasonably close (within 20%)
        if ratio < 1.2:
            logger.info("✓ Output sizes are similar (within 20%)")
        else:
            logger.warning("⚠ Output sizes differ by more than 20%")
    
    # Basic file comparison
    if filecmp.cmp(file1, file2):
        logger.info("✓ Files are identical (rare for audio files)")
    else:
        logger.info("Files have different content (expected for TTS output)")
    
    return True

def main():
    """Main function to run the MP3 consistency test."""
    logger.info("=== MP3 Output Consistency Test ===")
    
    # Run test2.py with MP3 output
    test2_output = run_test2_modified()
    if not test2_output:
        logger.error("Failed to generate MP3 with test2.py")
        return 1
    
    # Run test_voice_quality.py with MP3 output
    voice_quality_output = run_voice_quality_mp3()
    if not voice_quality_output:
        logger.error("Failed to generate MP3 with test_voice_quality.py")
        return 1
    
    # Compare the outputs
    compare_mp3_files(test2_output, voice_quality_output)
    
    logger.info("\n=== MP3 Consistency Test Complete ===")
    return 0

if __name__ == "__main__":
    sys.exit(main()) 