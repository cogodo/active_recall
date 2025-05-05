# Cartesia TTS Testing Framework

This directory contains a comprehensive testing framework for the Cartesia Text-to-Speech (TTS) system. The framework includes tools for compatibility verification, voice quality testing, and MP3 output consistency testing.

## Test Scripts

### 1. Compatibility Verification (`verify_compatibility.py`)

This script verifies that the core TTS functionality works correctly and matches our test suite. It:

- Runs the original test2.py script with enhanced output capture
- Runs an equivalent test using our comprehensive test_voice_quality.py
- Compares the outputs to ensure compatibility

Usage:
```bash
python verify_compatibility.py [--skip-comparison]
```

### 2. Voice Quality Testing (`test_voice_quality.py`)

This script tests voice quality across different configurations:
- Multiple voice options
- Different output formats (MP3, WAV, MP4)
- Various test phrases

Usage:
```bash
python test_voice_quality.py [--voice NAME] [--model NAME] [--format NAME] [--custom-phrase TEXT] [--output-dir DIR]
```

### 3. MP3 Consistency Test (`test_mp3_consistency.py`)

This script specifically tests the consistency of MP3 output between the original implementation and our test suite:
- Creates MP3 files using both implementations
- Compares file sizes and content
- Provides detailed statistics

Usage:
```bash
python test_mp3_consistency.py
```

### 4. Streaming TTS Testing (`test_streaming_tts.py`)

Tests the WebSocket-based streaming TTS functionality to ensure real-time audio delivery works correctly.

Usage:
```bash
python test_streaming_tts.py
```

## Configuration

The test suite is configured to use the following voices:
- Sophie (ID: bf0a246a-8642-498a-9950-80c35e9276b5)
- Savannah (ID: 78ab82d5-25be-4f7d-82b3-7ad64e5b85b2)
- Brooke (ID: 6f84f4b8-58a2-430c-8c79-688dad597532)

And the following models:
- Sonic 2

## Output Formats

The test suite tests multiple output formats:
- MP3 (with 44.1kHz sample rate)
- WAV (with 44.1kHz sample rate)

Note: MP4 format is not supported by the current Cartesia API.

## Environment Requirements

To run the tests, you need:
1. Python 3.8+
2. The Cartesia SDK installed (`pip install cartesia>=2.0.2`)
3. The CARTESIA_API_KEY environment variable set with a valid API key

## WebSocket API Notes

The WebSocket API uses the following methods:
- `client.tts.websocket()` to initialize a WebSocket client
- `ws_client.send({...})` to send the initial request
- `ws_client.continue({...})` to continue an existing session

Note: The continue method is accessed using getattr to avoid conflict with the Python keyword.

## Output Directories

Test outputs are saved to:
- `compatibility_test/`: For compatibility verification outputs
- `voice_samples/`: For voice quality test samples (default)
- `consistency_test/`: For MP3 consistency test outputs

## Running All Tests

To run all tests in sequence:

```bash
# Set API key
export CARTESIA_API_KEY="your-api-key"

# Run compatibility verification
python verify_compatibility.py

# Run MP3 consistency test
python test_mp3_consistency.py

# Run voice quality test with all voices and formats
python test_voice_quality.py
``` 