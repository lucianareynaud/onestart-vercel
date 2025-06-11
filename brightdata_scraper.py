#!/usr/bin/env python3
"""
BrightData LinkedIn Profile Scraper - Clean implementation based on latest API docs.
"""
import os
import time
import json
import requests
from typing import Dict, Optional, Any
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
API_KEY = os.getenv("BRIGHTDATA_API_KEY")
DATASET_ID = os.getenv("BRIGHTDATA_DATASET_ID")

if not API_KEY or not DATASET_ID:
    raise RuntimeError("Missing BRIGHTDATA_API_KEY or BRIGHTDATA_DATASET_ID")

# API endpoints - updated based on documentation
BASE_URL = "https://api.brightdata.com"
TRIGGER_URL = f"{BASE_URL}/datasets/v3/trigger?dataset_id={DATASET_ID}&include_errors=true"
# Updated endpoints based on documentation
PROGRESS_URL = f"{BASE_URL}/datasets/v3/progress"  # + /{snapshot_id}
SNAPSHOT_URL = f"{BASE_URL}/datasets/v3/snapshot"  # + /{snapshot_id}/download - Note: singular "snapshot"

class BrightDataScraper:
    """BrightData API client for LinkedIn profile scraping."""
    
    def __init__(self):
        self.headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        }
    
    def scrape_profile(self, profile_url: str, max_wait_time: int = 60) -> Optional[Dict[str, Any]]:
        """
        Scrape a LinkedIn profile using BrightData API.
        
        Args:
            profile_url: The LinkedIn profile URL to scrape
            max_wait_time: Maximum time to wait for results in seconds
            
        Returns:
            Profile data as dictionary or None if scraping failed
        """
        print(f"Scraping LinkedIn profile: {profile_url}")
        
        # 1. Trigger the scraping job
        snapshot_id = self._trigger_job(profile_url)
        if not snapshot_id:
            return None
            
        # 2. Wait for completion
        if not self._wait_for_completion(snapshot_id, max_wait_time):
            return None
            
        # 3. Download results
        return self._download_results(snapshot_id)
    
    def _trigger_job(self, profile_url: str) -> Optional[str]:
        """Trigger a scraping job for the LinkedIn profile."""
        payload = [{"url": profile_url}]
        
        print(f"Triggering BrightData job with dataset ID: {DATASET_ID}")
        try:
            response = requests.post(TRIGGER_URL, headers=self.headers, json=payload, timeout=15)
            print(f"Trigger response status: {response.status_code}")
            
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
    
    def _wait_for_completion(self, snapshot_id: str, max_wait_time: int) -> bool:
        """Wait for job completion, polling the progress endpoint."""
        progress_url = f"{PROGRESS_URL}/{snapshot_id}"
        print(f"Checking progress at: {progress_url}")
        
        deadline = time.time() + max_wait_time
        while time.time() < deadline:
            try:
                response = requests.get(progress_url, headers=self.headers, timeout=10)
                
                # Print full response for debugging
                print(f"Progress check status: {response.status_code}")
                if response.status_code != 200:
                    print(f"Error response: {response.text}")
                    # On a 404, we try alternate endpoints
                    alt_progress_url = f"{BASE_URL}/datasets/v3/snapshots/{snapshot_id}/status"
                    print(f"Trying alternate progress URL: {alt_progress_url}")
                    alt_response = requests.get(alt_progress_url, headers=self.headers, timeout=10)
                    print(f"Alternate progress check status: {alt_response.status_code}")
                    print(f"Alternate response: {alt_response.text}")
                    
                    # If both fail, wait and try again
                    time.sleep(5)
                    continue
                
                data = response.json()
                status = data.get("status")
                
                print(f"Current status: {status}")
                if status == "done" or status == "ready":  # Check for both status values
                    return True
                elif status == "failed":
                    error_message = data.get("error_message", "Unknown error")
                    print(f"Scraping failed: {error_message}")
                    return False
                    
                # Wait before polling again
                time.sleep(5)
                
            except requests.exceptions.RequestException as e:
                print(f"Error checking progress: {str(e)}")
                time.sleep(5)
        
        print(f"Timed out after {max_wait_time} seconds")
        return False
    
    def _download_results(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        """Download and process scraping results."""
        # Try multiple endpoints
        download_urls = [
            f"{SNAPSHOT_URL}/{snapshot_id}",  # Direct snapshot URL
            f"{SNAPSHOT_URL}/{snapshot_id}/download",  # Documented endpoint
            f"{BASE_URL}/datasets/v3/snapshots/{snapshot_id}/download",  # Alternative endpoint
            f"{BASE_URL}/datasets/v3/trigger/download?snapshot_id={snapshot_id}"  # Query param endpoint
        ]
        
        print(f"Starting download process for snapshot ID: {snapshot_id}")
        
        for download_url in download_urls:
            print(f"Trying to download from: {download_url}")
            
            try:
                response = requests.get(download_url, headers=self.headers, timeout=30)
                print(f"Response status: {response.status_code}")
                
                if response.status_code == 200:
                    print("Got 200 response, attempting to parse data")
                    
                    # For debugging
                    preview = response.text[:100] + "..." if len(response.text) > 100 else response.text
                    print(f"Response preview: {preview}")
                    
                    # Try to parse as JSON
                    try:
                        if "}{" in response.text:
                            # Handle concatenated JSON objects
                            fixed_json = "[" + response.text.replace("}{", "},{") + "]"
                            data = json.loads(fixed_json)
                            print("Successfully parsed concatenated JSON objects")
                        else:
                            data = response.json()
                            print("Successfully parsed JSON response")
                        
                        if not data:
                            print("Warning: Empty data received")
                            continue
                        
                        # Save results to file for reference
                        with open("profile_results.json", "w") as f:
                            json.dump(data, f, indent=2)
                        print(f"Results saved to profile_results.json")
                        
                        # Return the first profile (we only requested one)
                        if isinstance(data, list) and len(data) > 0:
                            return data[0]
                        else:
                            return data
                            
                    except json.JSONDecodeError as e:
                        print(f"Error parsing JSON: {str(e)}")
                        
                        # Save raw response for inspection
                        with open(f"raw_response_{snapshot_id}.txt", "w") as f:
                            f.write(response.text)
                        print(f"Saved raw response to raw_response_{snapshot_id}.txt for inspection")
                else:
                    print(f"Download failed with status {response.status_code}: {response.text}")
                    
            except requests.exceptions.RequestException as e:
                print(f"Request error: {str(e)}")
        
        print("All download attempts failed")
        return None



if __name__ == "__main__":
    print("This is a development/testing utility only.")
    main()

def main(profile_url=None):
    """
    Testing function for the BrightData scraper.
    
    Args:
        profile_url: Optional LinkedIn profile URL to scrape
    """
    import sys
    
    print("WARNING: This is a test function for development only!")
    print("In production, this module should be imported by app.py\n")
    
    # Get URL from command line args or function parameter
    if not profile_url:
        if len(sys.argv) > 1:
            profile_url = sys.argv[1]
        else:
            print("Please provide a LinkedIn profile URL to scrape")
            print("Usage: python brightdata_scraper.py <linkedin_url>")
            return
    
    print(f"Testing scraper with URL: {profile_url}")
    scraper = BrightDataScraper()
    
    # Run the scraper
    profile_data = scraper.scrape_profile(profile_url, max_wait_time=90)
    
    # Print results summary
    if profile_data:
        print("\nProfile data fetched successfully:")
        print(f"Name: {profile_data.get('name', 'N/A')}")
        print(f"Headline: {profile_data.get('headline', 'N/A')}")
        print(f"Location: {profile_data.get('location', 'N/A')}")
        print(f"Current Company: {profile_data.get('company', 'N/A')}")
    else:
        print("\nFailed to fetch profile data")


if __name__ == "__main__":
    print("This is a development/testing utility only.")
    main() 