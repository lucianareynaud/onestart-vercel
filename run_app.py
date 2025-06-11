#!/usr/bin/env python3
import os
import sys
import uvicorn
from dotenv import load_dotenv

def main():
    """
    Run the application with correct port messaging.
    This wrapper ensures the correct external port is displayed in logs.
    """
    # Load environment variables from .env file
    load_dotenv(verbose=True)
    
    # Verify critical environment variables
    brightdata_key = os.environ.get("BRIGHTDATA_API_KEY")
    brightdata_dataset = os.environ.get("BRIGHTDATA_DATASET_ID")
    openai_key = os.environ.get("OPENAI_API_KEY")
    
    print("\nEnvironment variables check:")
    print(f"BRIGHTDATA_API_KEY: {'SET' if brightdata_key else 'NOT SET'}")
    print(f"BRIGHTDATA_DATASET_ID: {'SET' if brightdata_dataset else 'NOT SET'}")
    print(f"OPENAI_API_KEY: {'SET' if openai_key else 'NOT SET'}")
    
    # Internal port (inside container)
    internal_port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    
    # External port (mapped in docker-compose)
    external_port = 9000 if internal_port == 8000 else internal_port
    
    print("\n" + "=" * 50)
    print(f"🚀 Whisper Transcription App is starting!")
    print(f"📊 Access the app at: http://localhost:{external_port}")
    print("=" * 50 + "\n")
    
    # Run the application
    uvicorn.run("app:app", host=host, port=internal_port, log_level="info")

if __name__ == "__main__":
    main() 