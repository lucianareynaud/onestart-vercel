#!/usr/bin/env python3
"""
LinkedIn Profile Enricher using BrightData API

This script takes LinkedIn profile URLs as input and enriches them with
data from the BrightData API. It can process multiple profiles in a single request.

Usage:
  python linkedin_enricher.py --urls <linkedin-profile-url> [<linkedin-profile-url>...]
  python linkedin_enricher.py --input urls.txt
  python linkedin_enricher.py --interactive
"""

import os
import sys
import time
import json
import argparse
import requests
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
API_KEY = os.getenv("BRIGHTDATA_API_KEY")
DATASET_ID = os.getenv("BRIGHTDATA_DATASET_ID")

if not API_KEY or not DATASET_ID:
    raise RuntimeError("Missing BRIGHTDATA_API_KEY or BRIGHTDATA_DATASET_ID")

# API endpoints
BASE_URL = "https://api.brightdata.com"
TRIGGER_URL = f"{BASE_URL}/datasets/v3/trigger?dataset_id={DATASET_ID}&include_errors=true"
PROGRESS_URL = f"{BASE_URL}/datasets/v3/progress"  # + /{snapshot_id}

# Headers for API requests
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

def validate_linkedin_url(url: str) -> bool:
    """Check if a URL is a valid LinkedIn profile URL."""
    return "linkedin.com/in/" in url

def trigger_brightdata_job(profile_urls: List[str]) -> Optional[str]:
    """
    Trigger a BrightData job for multiple LinkedIn profiles.
    
    Args:
        profile_urls: List of LinkedIn profile URLs to scrape
        
    Returns:
        Snapshot ID if successful, None otherwise
    """
    # Validate URLs
    valid_urls = [url for url in profile_urls if validate_linkedin_url(url)]
    if not valid_urls:
        print("Error: No valid LinkedIn profile URLs provided")
        return None
        
    # Create payload
    payload = [{"url": url} for url in valid_urls]
    
    print(f"Triggering BrightData job with {len(valid_urls)} LinkedIn profiles...")
    print(f"Using dataset ID: {DATASET_ID}")
    
    try:
        response = requests.post(TRIGGER_URL, headers=HEADERS, json=payload, timeout=15)
        
        if response.status_code != 200:
            print(f"Error: API returned status code {response.status_code}")
            print(f"Response: {response.text}")
            return None
            
        data = response.json()
        snapshot_id = data.get("snapshot_id")
        
        if not snapshot_id:
            print("Error: No snapshot_id in response")
            return None
            
        print(f"Job triggered successfully. Snapshot ID: {snapshot_id}")
        return snapshot_id
        
    except requests.exceptions.RequestException as e:
        print(f"Error triggering job: {str(e)}")
        return None

def check_job_status(snapshot_id: str) -> Optional[str]:
    """
    Check the status of a BrightData job.
    
    Args:
        snapshot_id: The ID of the snapshot to check
        
    Returns:
        Status string if successful, None otherwise
    """
    progress_url = f"{PROGRESS_URL}/{snapshot_id}"
    
    try:
        response = requests.get(progress_url, headers=HEADERS, timeout=10)
        
        if response.status_code != 200:
            print(f"Error checking status: {response.status_code}")
            print(f"Response: {response.text}")
            return None
            
        data = response.json()
        status = data.get("status")
        
        if not status:
            print("Error: No status in response")
            return None
            
        return status
        
    except requests.exceptions.RequestException as e:
        print(f"Error checking status: {str(e)}")
        return None

def download_results(snapshot_id: str) -> Optional[List[Dict[str, Any]]]:
    """
    Download results from a BrightData job.
    
    Args:
        snapshot_id: The ID of the snapshot to download
        
    Returns:
        List of profile data dictionaries if successful, None otherwise
    """
    # Try multiple different endpoint formats based on BrightData documentation
    endpoints = [
        # Versão testada com curl
        f"{BASE_URL}/datasets/v3/snapshot/{snapshot_id}",
        # Outras variantes para fallback
        f"{BASE_URL}/datasets/v3/snapshot/{snapshot_id}/download",
        f"{BASE_URL}/datasets/v3/snapshots/{snapshot_id}/download",
        # Endpoints adicionais para tentar
        f"{BASE_URL}/datasets/v3/trigger/download?snapshot_id={snapshot_id}",
        f"{BASE_URL}/datasets/v3/snapshots/{snapshot_id}",
        f"{BASE_URL}/datasets/v3/download/{snapshot_id}"
    ]
    
    # Adiciona log para debugging
    print(f"Tentando baixar resultados para snapshot_id: {snapshot_id}")
    print(f"Headers usados: {HEADERS}")
    
    for download_url in endpoints:
        print(f"Trying to download from: {download_url}")
        
        try:
            response = requests.get(download_url, headers=HEADERS, timeout=30)
            
            if response.status_code == 200:
                raw_text = response.text
                
                # Special handling for the endpoint that works but returns malformed JSON
                if download_url.endswith(f"/{snapshot_id}") and not download_url.endswith("/download"):
                    try:
                        # The response looks like a JSON object but with multiple objects concatenated
                        # Let's try to fix it by wrapping in array brackets and adding commas
                        fixed_json = "[" + raw_text.replace("}{", "},{") + "]"
                        data = json.loads(fixed_json)
                        print(f"Successfully downloaded and fixed data from: {download_url}")
                        return data
                    except json.JSONDecodeError as e:
                        print(f"Error fixing JSON: {str(e)}")
                        
                        # Save the raw response for manual inspection
                        output_file = f"raw_response_{int(time.time())}.txt"
                        with open(output_file, "w") as f:
                            f.write(raw_text)
                        print(f"Saved raw response to {output_file} for manual inspection")
                        
                        # As a fallback, try to manually parse the response
                        # This is a hack, but it might work for the specific format we're seeing
                        try:
                            # Create an array to hold our parsed profiles
                            profiles = []
                            
                            # Try to find complete JSON objects in the response
                            # Look for pattern {"id":...}{"id":...} and split into separate objects
                            import re
                            pattern = r'(\{[^{]*?"id":[^{]*?\})'
                            matches = re.findall(pattern, raw_text)
                            
                            if matches:
                                for match in matches:
                                    try:
                                        profile = json.loads(match)
                                        profiles.append(profile)
                                    except:
                                        pass
                                
                                if profiles:
                                    print(f"Manually parsed {len(profiles)} profiles from malformed response")
                                    return profiles
                        except Exception as parse_err:
                            print(f"Failed to manually parse: {str(parse_err)}")
                else:
                    # Regular JSON parsing for other endpoints
                    try:
                        data = json.loads(raw_text)
                        print(f"Successfully downloaded data from: {download_url}")
                        return data
                    except json.JSONDecodeError:
                        print(f"Error: Response is not valid JSON: {raw_text[:200]}...")
            else:
                print(f"Download failed with status {response.status_code}")
                if response.status_code != 404:  # Only show detailed error for non-404s
                    print(f"Response: {response.text}")
                
        except requests.exceptions.RequestException as e:
            print(f"Error downloading results: {str(e)}")
    
    print("All download attempts failed")
    return None

def process_profiles(profile_urls: List[str], max_wait_time: int = 180, output_dir: str = "outputs") -> bool:
    """
    Process LinkedIn profiles through BrightData and save results.
    
    Args:
        profile_urls: List of LinkedIn profile URLs to process
        max_wait_time: Maximum time to wait for results in seconds
        output_dir: Directory to save output files
        
    Returns:
        True if successful, False otherwise
    """
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Trigger the job
    snapshot_id = trigger_brightdata_job(profile_urls)
    if not snapshot_id:
        return False
    
    # Wait for job completion
    print(f"Waiting for job completion (up to {max_wait_time} seconds)...")
    deadline = time.time() + max_wait_time
    
    while time.time() < deadline:
        status = check_job_status(snapshot_id)
        
        if not status:
            print("Error checking job status, retrying...")
            time.sleep(5)
            continue
            
        print(f"Current status: {status}")
        
        if status == "ready":
            print("Job completed successfully!")
            return True
        elif status == "done":
            print("Job completed successfully (status: done)!")
            return True
        elif status == "failed":
            print("Job failed!")
            return False
            
        # Wait before checking again
        time.sleep(5)
    else:
        print(f"Timed out after {max_wait_time} seconds")
        return False
    
    # Download results
    print("Downloading results...")
    results = download_results(snapshot_id)
    
    if not results:
        print("Failed to download results")
        return False
        
    # Save results to file
    timestamp = int(time.time())
    output_file = os.path.join(output_dir, f"linkedin_profiles_{timestamp}.json")
    
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
        
    print(f"Results saved to {output_file}")
    
    # Print summary
    print("\nSummary:")
    print(f"Processed {len(profile_urls)} LinkedIn profiles")
    print(f"Retrieved {len(results)} profiles from BrightData")
    
    return True

def read_urls_from_file(file_path: str) -> List[str]:
    """Read LinkedIn profile URLs from a file."""
    with open(file_path, "r") as f:
        return [line.strip() for line in f if line.strip()]

def interactive_mode() -> List[str]:
    """Get LinkedIn profile URLs interactively from user."""
    print("Enter LinkedIn profile URLs (one per line, empty line to finish):")
    urls = []
    
    while True:
        line = input("> ").strip()
        if not line:
            break
        urls.append(line)
        
    return urls

def main() -> None:
    """Main function to parse arguments and process profiles."""
    parser = argparse.ArgumentParser(description="Enrich LinkedIn profiles using BrightData API")
    
    # Define mutually exclusive input methods
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--urls", nargs="+", help="List of LinkedIn profile URLs to process")
    group.add_argument("--input", help="Path to a file containing LinkedIn profile URLs (one per line)")
    group.add_argument("--interactive", action="store_true", help="Enter URLs interactively")
    
    # Additional options
    parser.add_argument("--wait-time", type=int, default=180, help="Maximum time to wait for results in seconds")
    parser.add_argument("--output-dir", default="outputs", help="Directory to save output files")
    
    args = parser.parse_args()
    
    # Get profile URLs based on input method
    if args.urls:
        profile_urls = args.urls
    elif args.input:
        profile_urls = read_urls_from_file(args.input)
    elif args.interactive:
        profile_urls = interactive_mode()
    
    if not profile_urls:
        print("Error: No LinkedIn profile URLs provided")
        sys.exit(1)
        
    # Process profiles
    success = process_profiles(profile_urls, args.wait_time, args.output_dir)
    
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    main() 