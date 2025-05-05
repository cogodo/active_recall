#!/usr/bin/env python3
"""
Cartesia TTS Test Runner
-----------------------
Runs all Cartesia TTS tests and generates a comprehensive report.
"""

import os
import sys
import argparse
import subprocess
import datetime
import json
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("tts-test-runner")

def check_environment():
    """Check if the environment is properly set up for testing."""
    # Check for API key
    api_key = os.getenv("CARTESIA_API_KEY")
    if not api_key:
        logger.error("CARTESIA_API_KEY environment variable must be set")
        return False

    # Check for required packages
    try:
        import cartesia
        logger.info(f"Found cartesia package version {cartesia.__version__}")
    except ImportError:
        logger.error("cartesia package is not installed. Please install it with 'pip install cartesia'")
        return False

    return True

def run_voice_quality_tests(args):
    """Run voice quality tests."""
    logger.info("Running voice quality tests...")
    
    cmd = [
        sys.executable, 
        "test_voice_quality.py",
        "--output-dir", str(args.output_dir / "voice_samples")
    ]
    
    if args.voice:
        cmd.extend(["--voice", args.voice])
    
    if args.model:
        cmd.extend(["--model", args.model])
        
    if args.phrase_index is not None:
        cmd.extend(["--phrase-index", str(args.phrase_index)])
        
    if args.custom_phrase:
        cmd.extend(["--custom-phrase", args.custom_phrase])
    
    try:
        process = subprocess.run(cmd, check=True, capture_output=not args.verbose)
        if process.returncode == 0:
            logger.info("Voice quality tests completed successfully")
            return True
        else:
            logger.error(f"Voice quality tests failed with code {process.returncode}")
            return False
    except subprocess.CalledProcessError as e:
        logger.error(f"Voice quality tests failed: {e}")
        if e.stderr:
            logger.error(f"Error output: {e.stderr.decode('utf-8')}")
        return False
    except FileNotFoundError:
        logger.error("test_voice_quality.py not found")
        return False

def run_streaming_tests(args):
    """Run streaming TTS tests."""
    logger.info("Running streaming TTS tests...")
    
    cmd = [
        sys.executable, 
        "test_streaming_tts.py",
        "--output-dir", str(args.output_dir / "streaming_samples"),
        "--results-dir", str(args.output_dir / "test_results")
    ]
    
    if args.voice:
        cmd.extend(["--voice", args.voice])
    
    if args.model:
        cmd.extend(["--model", args.model])
    
    try:
        process = subprocess.run(cmd, check=True, capture_output=not args.verbose)
        if process.returncode == 0:
            logger.info("Streaming TTS tests completed successfully")
            return True
        else:
            logger.error(f"Streaming TTS tests failed with code {process.returncode}")
            return False
    except subprocess.CalledProcessError as e:
        logger.error(f"Streaming TTS tests failed: {e}")
        if e.stderr:
            logger.error(f"Error output: {e.stderr.decode('utf-8')}")
        return False
    except FileNotFoundError:
        logger.error("test_streaming_tts.py not found")
        return False

def generate_report(args):
    """Generate a consolidated test report."""
    logger.info("Generating test report...")
    
    report_file = args.output_dir / "test_results" / f"consolidated_report_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    
    # Find all JSON result files
    results_dir = args.output_dir / "test_results"
    json_files = list(results_dir.glob("*.json"))
    
    if not json_files:
        logger.warning("No test result files found for report generation")
        return False
    
    # Load and consolidate results
    all_results = []
    for file in json_files:
        try:
            with open(file, 'r') as f:
                results = json.load(f)
                if isinstance(results, list):
                    all_results.extend(results)
                else:
                    all_results.append(results)
        except Exception as e:
            logger.error(f"Error processing {file}: {e}")
    
    if not all_results:
        logger.warning("No valid test results found")
        return False
    
    # Generate HTML report
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Cartesia TTS Test Report</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            h1, h2 {{ color: #333; }}
            table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
            th, td {{ padding: 8px; text-align: left; border: 1px solid #ddd; }}
            th {{ background-color: #f2f2f2; }}
            tr:nth-child(even) {{ background-color: #f9f9f9; }}
            .success {{ background-color: #dff0d8; }}
            .failure {{ background-color: #f2dede; }}
            .summary {{ display: flex; justify-content: space-between; margin-bottom: 20px; }}
            .summary-box {{ background-color: #f8f9fa; border: 1px solid #ddd; padding: 15px; border-radius: 5px; width: 30%; }}
        </style>
    </head>
    <body>
        <h1>Cartesia TTS Test Report</h1>
        <p>Generated on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        
        <div class="summary">
            <div class="summary-box">
                <h3>Test Summary</h3>
                <p>Total Tests: {len(all_results)}</p>
                <p>Successful: {sum(1 for r in all_results if r.get('success', False))}</p>
                <p>Failed: {sum(1 for r in all_results if not r.get('success', False))}</p>
                <p>Success Rate: {(sum(1 for r in all_results if r.get('success', False)) / len(all_results) * 100):.1f}%</p>
            </div>
            
            <div class="summary-box">
                <h3>Voice Distribution</h3>
                {generate_voice_summary_html(all_results)}
            </div>
            
            <div class="summary-box">
                <h3>Model Distribution</h3>
                {generate_model_summary_html(all_results)}
            </div>
        </div>
        
        <h2>Test Results</h2>
        <table>
            <tr>
                <th>Test Type</th>
                <th>Voice</th>
                <th>Model</th>
                <th>Status</th>
                <th>Duration (s)</th>
                <th>Size (KB)</th>
                <th>Details</th>
            </tr>
            {generate_results_table_html(all_results)}
        </table>
        
        <h2>Sample Files</h2>
        <table>
            <tr>
                <th>Voice</th>
                <th>Model</th>
                <th>File Path</th>
                <th>Size (KB)</th>
            </tr>
            {generate_files_table_html(all_results)}
        </table>
    </body>
    </html>
    """
    
    with open(report_file, 'w') as f:
        f.write(html_content)
    
    logger.info(f"Test report generated: {report_file}")
    return True

def generate_voice_summary_html(results):
    """Generate HTML for voice summary."""
    voice_counts = {}
    for result in results:
        voice = result.get('voice', 'Unknown')
        voice_counts[voice] = voice_counts.get(voice, 0) + 1
    
    html = "<ul>"
    for voice, count in voice_counts.items():
        html += f"<li>{voice}: {count}</li>"
    html += "</ul>"
    
    return html

def generate_model_summary_html(results):
    """Generate HTML for model summary."""
    model_counts = {}
    for result in results:
        model = result.get('model', 'Unknown')
        model_counts[model] = model_counts.get(model, 0) + 1
    
    html = "<ul>"
    for model, count in model_counts.items():
        html += f"<li>{model}: {count}</li>"
    html += "</ul>"
    
    return html

def generate_results_table_html(results):
    """Generate HTML for results table."""
    html = ""
    for i, result in enumerate(results):
        success = result.get('success', False)
        row_class = "success" if success else "failure"
        
        # Determine test type
        test_type = "Streaming" if "chunks" in result else "Voice Quality"
        
        # Get details
        details = result.get('error', '') if not success else ''
        if "chunks" in result and success:
            details = f"{result.get('chunks', 0)} chunks"
        
        html += f"""
        <tr class="{row_class}">
            <td>{test_type}</td>
            <td>{result.get('voice', 'Unknown')}</td>
            <td>{result.get('model', 'Unknown')}</td>
            <td>{'Success' if success else 'Failure'}</td>
            <td>{result.get('duration_sec', 0):.2f}</td>
            <td>{result.get('size_bytes', 0) / 1024:.2f}</td>
            <td>{details}</td>
        </tr>
        """
    
    return html

def generate_files_table_html(results):
    """Generate HTML for files table."""
    html = ""
    for result in results:
        if 'file' in result:
            html += f"""
            <tr>
                <td>{result.get('voice', 'Unknown')}</td>
                <td>{result.get('model', 'Unknown')}</td>
                <td>{result.get('file', '')}</td>
                <td>{result.get('size_bytes', 0) / 1024:.2f}</td>
            </tr>
            """
    
    return html

def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Run Cartesia TTS tests")
    
    # Test selection options
    parser.add_argument("--voice-quality", action="store_true", help="Run voice quality tests")
    parser.add_argument("--streaming", action="store_true", help="Run streaming TTS tests")
    parser.add_argument("--all", action="store_true", help="Run all tests (default)")
    
    # Configuration options
    parser.add_argument("--voice", help="Specific voice to test")
    parser.add_argument("--model", help="Specific model to test")
    parser.add_argument("--phrase-index", type=int, help="Index of specific test phrase to use")
    parser.add_argument("--custom-phrase", help="Custom phrase to test")
    
    # Output options
    parser.add_argument("--output-dir", default="tts_test_output", help="Directory for test output")
    parser.add_argument("--verbose", action="store_true", help="Show verbose output")
    
    return parser.parse_args()

def main():
    """Main function to run tests."""
    args = parse_args()
    
    # Convert output_dir to Path
    args.output_dir = Path(args.output_dir)
    
    # Create output directories
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "voice_samples").mkdir(exist_ok=True)
    (args.output_dir / "streaming_samples").mkdir(exist_ok=True)
    (args.output_dir / "test_results").mkdir(exist_ok=True)
    
    # Check if environment is set up properly
    if not check_environment():
        logger.error("Environment check failed. Please set up the environment properly.")
        return 1
    
    # Determine which tests to run
    run_all = args.all or (not args.voice_quality and not args.streaming)
    
    # Run selected tests
    success = True
    
    if args.voice_quality or run_all:
        voice_quality_success = run_voice_quality_tests(args)
        success = success and voice_quality_success
    
    if args.streaming or run_all:
        streaming_success = run_streaming_tests(args)
        success = success and streaming_success
    
    # Generate report
    generate_report(args)
    
    logger.info("All tests completed.")
    if success:
        logger.info("All requested tests passed successfully.")
        return 0
    else:
        logger.warning("Some tests failed. See the logs for details.")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 