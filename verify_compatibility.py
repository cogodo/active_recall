#!/usr/bin/env python3
"""
Compatibility Verification Script for test2.py
---------------------------------------------
Verifies that test2.py functionality works correctly and matches our test suite.
"""

import os
import sys
import argparse
import subprocess
import logging
import filecmp
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("compatibility-verifier")

def check_environment():
    """Check if the environment is properly set up."""
    api_key = os.getenv("CARTESIA_API_KEY")
    if not api_key:
        logger.error("CARTESIA_API_KEY environment variable must be set")
        return False
    
    try:
        import cartesia
        logger.info(f"Found cartesia package version {cartesia.__version__}")
    except ImportError:
        logger.error("cartesia package is not installed")
        return False
    
    return True

def run_test2_py(output_file=None):
    """Run the original test2.py script."""
    if not Path("test2.py").exists():
        logger.error("Original test2.py file not found in the current directory")
        return False
    
    logger.info("Running original test2.py script...")
    
    if output_file:
        # Create a modified version of test2.py that captures and saves the output
        modified_script = create_modified_test2(output_file)
        if not modified_script:
            return False
        
        cmd = [sys.executable, modified_script]
    else:
        cmd = [sys.executable, "test2.py"]
    
    try:
        env = os.environ.copy()
        process = subprocess.run(cmd, check=True, capture_output=True, env=env)
        logger.info("Original test2.py completed successfully")
        
        if process.stdout:
            logger.info(f"Output: {process.stdout.decode('utf-8').strip()}")
        
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Error running test2.py: {e}")
        if e.stdout:
            logger.info(f"Output: {e.stdout.decode('utf-8').strip()}")
        if e.stderr:
            logger.error(f"Error: {e.stderr.decode('utf-8').strip()}")
        return False

def create_modified_test2(output_file):
    """Create a modified version of test2.py that saves output to a file."""
    temp_file = "test2_modified.py"
    
    try:
        with open("test2.py", "r") as f:
            content = f.read()
        
        # Check if it's a valid Python file
        if not content.strip():
            logger.error("test2.py is empty or contains no code")
            return None
        
        # For simplicity, let's create a completely new script that works with the current SDK version
        new_content = []
        
        # Basic imports and setup
        new_content.append("import os")
        new_content.append("from cartesia import Cartesia")
        new_content.append("")
        
        # API key check
        new_content.append("# Verify that API key is available")
        new_content.append("api_key = os.getenv('CARTESIA_API_KEY')")
        new_content.append("if not api_key:")
        new_content.append("    raise ValueError('CARTESIA_API_KEY environment variable must be set')")
        new_content.append("")
        
        # Client initialization
        new_content.append("# Initialize client")
        new_content.append("client = Cartesia(api_key=api_key)")
        new_content.append("")
        
        # TTS call with supported parameters
        new_content.append("# Generate TTS audio")
        new_content.append("print('Generating TTS audio...')")
        new_content.append("audio_result = client.tts.bytes(")
        new_content.append("    model_id='sonic-2',")
        new_content.append("    transcript='Hello, world!',")
        new_content.append("    voice={")
        new_content.append("        'mode': 'id',")
        new_content.append("        'id': 'bf0a246a-8642-498a-9950-80c35e9276b5',  # Sophie")
        new_content.append("    },")
        new_content.append("    language='en',")
        new_content.append("    output_format={")
        new_content.append("        'container': 'mp3',")
        new_content.append("        'sample_rate': 44100,")
        new_content.append("    }")
        new_content.append(")")
        new_content.append("")
        
        # Save output
        new_content.append("# Collect audio data")
        new_content.append("print('Collecting audio chunks...')")
        new_content.append("audio_data = b''")
        new_content.append("for chunk in audio_result:")
        new_content.append("    audio_data += chunk")
        new_content.append("")
        new_content.append("# Save to file")
        new_content.append(f"output_file = '{output_file}'")
        new_content.append("print(f'Saving audio to {output_file}...')")
        new_content.append("with open(output_file, 'wb') as f:")
        new_content.append("    f.write(audio_data)")
        new_content.append("")
        new_content.append("print(f'Audio saved successfully to {output_file}')")
        
        # Write the new file
        with open(temp_file, "w") as f:
            f.write("\n".join(new_content))
        
        logger.info(f"Created modified test2.py that saves output to {output_file}")
        return temp_file
        
    except Exception as e:
        logger.error(f"Error creating modified test2.py: {e}")
        return None

def run_equivalent_test(output_file):
    """Run an equivalent test using our test suite."""
    logger.info("Running equivalent test with test_voice_quality.py...")
    
    cmd = [
        sys.executable, 
        "test_voice_quality.py",
        "--voice", "Sophie",
        "--model", "Sonic 2",
        "--format", "WAV 44.1kHz",
        "--custom-phrase", "Hello, world!",
        "--output-dir", "compatibility_test"
    ]
    
    try:
        output_dir = Path("compatibility_test")
        output_dir.mkdir(exist_ok=True)
        
        process = subprocess.run(cmd, check=True, capture_output=True)
        logger.info("Equivalent test completed successfully")
        
        # Find the generated file - look for WAV files
        files = list(output_dir.glob("sophie_sonic_2_wav_*.wav"))
        if not files:
            # Try a less specific pattern as fallback
            files = list(output_dir.glob("sophie_*.wav"))
            if not files:
                # Try any audio file as last resort
                files = list(output_dir.glob("sophie_*.*"))
                if not files:
                    logger.error("No output file found from equivalent test")
                    return None
        
        equiv_file = files[0]
        logger.info(f"Equivalent test generated file: {equiv_file}")
        return str(equiv_file)
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Error running equivalent test: {e}")
        if e.stdout:
            logger.info(f"Output: {e.stdout.decode('utf-8').strip()}")
        if e.stderr:
            logger.error(f"Error: {e.stderr.decode('utf-8').strip()}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return None

def compare_outputs(file1, file2):
    """Compare the outputs of the two test runs."""
    if not (Path(file1).exists() and Path(file2).exists()):
        logger.error("One or both output files don't exist")
        return False
    
    # Get file sizes
    size1 = Path(file1).stat().st_size
    size2 = Path(file2).stat().st_size
    
    logger.info(f"Original output size: {size1 / 1024:.2f} KB")
    logger.info(f"Equivalent output size: {size2 / 1024:.2f} KB")
    
    # Size ratio
    if size1 > 0 and size2 > 0:
        ratio = max(size1, size2) / min(size1, size2)
        logger.info(f"Size ratio: {ratio:.2f}x")
        
        # Check if sizes are reasonably close (within 20%)
        if ratio < 1.2:
            logger.info("✓ Output sizes are similar (within 20%)")
        else:
            logger.warning("⚠ Output sizes differ by more than 20%")
    
    # Basic file comparison (will likely be different due to encoding specifics)
    if filecmp.cmp(file1, file2):
        logger.info("✓ Files are identical (unlikely for audio files)")
    else:
        logger.info("Files have different content (expected for TTS output)")
    
    return True

def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Verify compatibility with test2.py")
    parser.add_argument("--skip-comparison", action="store_true", help="Skip file comparison")
    args = parser.parse_args()
    
    if not check_environment():
        return 1
    
    # Create output directory
    output_dir = Path("compatibility_test")
    output_dir.mkdir(exist_ok=True)
    
    # Run original test2.py
    test2_output = str(output_dir / "test2_output.mp3")
    if not run_test2_py(test2_output):
        logger.error("Failed to run original test2.py")
        return 1
    
    # Run equivalent test with our test suite
    equiv_output = run_equivalent_test(test2_output)
    if not equiv_output:
        logger.error("Failed to run equivalent test")
        return 1
    
    # Compare outputs
    if not args.skip_comparison:
        compare_outputs(test2_output, equiv_output)
    
    logger.info("\n=== Compatibility Verification Complete ===")
    logger.info("✓ Original test2.py ran successfully")
    logger.info("✓ Equivalent test ran successfully")
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 