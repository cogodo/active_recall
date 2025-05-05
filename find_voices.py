#!/usr/bin/env python3
"""
Find available Cartesia voices
"""
import os
from cartesia import Cartesia

def main():
    # Check API key
    api_key = os.getenv("CARTESIA_API_KEY")
    if not api_key:
        print("CARTESIA_API_KEY environment variable not set")
        return
    
    # Initialize client
    client = Cartesia(api_key=api_key)
    
    # List voices
    print("Listing available voices...")
    try:
        voices = list(client.voices.list())
        print(f"Found {len(voices)} voices:")
        
        # Print voice details
        for i, voice in enumerate(voices[:20]):  # Print first 20 only
            print(f"{i+1}. ID: {voice.id} - Name: {voice.name}")
            
        # Look for specific voices
        print("\nLooking for specific voices:")
        found_nova = False
        found_shimmer = False
        
        for voice in voices:
            name_lower = voice.name.lower()
            if 'nova' in name_lower:
                print(f"Found Nova: {voice.id} - {voice.name}")
                found_nova = True
            if 'shimmer' in name_lower:
                print(f"Found Shimmer: {voice.id} - {voice.name}")
                found_shimmer = True
        
        if not found_nova:
            print("Nova voice not found")
        if not found_shimmer:
            print("Shimmer voice not found")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main() 