#!/usr/bin/env python3
"""
LinkedIn Profile Enricher with Supabase Integration

This script fetches LinkedIn profile data using BrightData API and stores it in Supabase.
"""

import os
import json
import time
import uuid
import asyncio
from datetime import datetime
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
import requests
from supabase import create_client, Client

# Import our LinkedIn enricher
from linkedin_enricher import trigger_brightdata_job, check_job_status, download_results, validate_linkedin_url

# Load environment variables
load_dotenv()

# Supabase configuration
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_KEY")

# BrightData API configuration
API_KEY = os.getenv("BRIGHTDATA_API_KEY")
DATASET_ID = os.getenv("BRIGHTDATA_DATASET_ID")

# Validate configuration
if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Missing Supabase configuration")
if not API_KEY or not DATASET_ID:
    raise RuntimeError("Missing BrightData configuration")

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

class LinkedInProfileEnricher:
    """BrightData LinkedIn Profile Enricher with Supabase integration."""
    
    def __init__(self):
        self.profile_cache = {}  # Cache to avoid duplicate API calls
    
    async def enrich_profile(self, linkedin_url: str, transcript_id: str) -> Dict[str, Any]:
        """
        Enrich a LinkedIn profile and store it in Supabase.
        
        Args:
            linkedin_url: The LinkedIn profile URL to enrich
            transcript_id: The transcript ID to associate with the enrichment
            
        Returns:
            A dictionary containing the enrichment operation result
        """
        if not validate_linkedin_url(linkedin_url):
            return self._create_error_result(linkedin_url, transcript_id, "Invalid LinkedIn URL format")
            
        # Check if we already have an entry for this URL + transcript in the database
        existing_entry = self._get_existing_enrichment(linkedin_url, transcript_id)
        if existing_entry and existing_entry.get("status") == "ok":
            print(f"Using existing enrichment for {linkedin_url}")
            return {
                "linkedin_url": linkedin_url,
                "transcript_id": transcript_id,
                "status": "ok",
                "profile_data": existing_entry.get("profile_data"),
                "enrichment_id": existing_entry.get("id"),
                "message": "Using existing enrichment"
            }
            
        # Create or update a pending enrichment
        enrichment_id = existing_entry.get("id") if existing_entry else str(uuid.uuid4())
        if not existing_entry:
            self._create_pending_enrichment(linkedin_url, transcript_id, enrichment_id)
        
        # Trigger BrightData job
        print(f"Triggering enrichment for {linkedin_url}")
        snapshot_id = trigger_brightdata_job([linkedin_url])
        if not snapshot_id:
            self._update_enrichment_status(enrichment_id, "error", "Failed to trigger BrightData job")
            return self._create_error_result(linkedin_url, transcript_id, "Failed to trigger BrightData job", enrichment_id)
        
        # Wait for job completion
        max_wait_time = 180  # seconds
        result = await self._wait_for_job_completion(snapshot_id, max_wait_time)
        if not result:
            self._update_enrichment_status(enrichment_id, "error", "Job failed or timed out")
            return self._create_error_result(linkedin_url, transcript_id, "Job failed or timed out", enrichment_id)
            
        # Download and process results
        profile_data = await self._process_results(snapshot_id, linkedin_url)
        if not profile_data:
            self._update_enrichment_status(enrichment_id, "error", "Failed to download or process results")
            return self._create_error_result(linkedin_url, transcript_id, "Failed to download or process results", enrichment_id)
            
        # Update Supabase with profile data
        self._update_enrichment_with_profile(enrichment_id, profile_data)
        
        return {
            "linkedin_url": linkedin_url,
            "transcript_id": transcript_id,
            "status": "ok",
            "profile_data": profile_data,
            "enrichment_id": enrichment_id,
            "message": "Successfully enriched profile"
        }
        
    async def enrich_profiles(self, urls_with_transcripts: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """
        Enrich multiple LinkedIn profiles and store them in Supabase.
        
        Args:
            urls_with_transcripts: List of dictionaries containing LinkedIn URLs and transcript IDs
            
        Returns:
            List of result dictionaries
        """
        results = []
        for item in urls_with_transcripts:
            linkedin_url = item.get("linkedin_url")
            transcript_id = item.get("transcript_id")
            
            if not linkedin_url or not transcript_id:
                results.append({
                    "status": "error",
                    "message": "Missing linkedin_url or transcript_id"
                })
                continue
                
            result = await self.enrich_profile(linkedin_url, transcript_id)
            results.append(result)
            
        return results
    
    async def _wait_for_job_completion(self, snapshot_id: str, max_wait_time: int) -> bool:
        """Wait for BrightData job completion."""
        deadline = time.time() + max_wait_time
        
        while time.time() < deadline:
            status = check_job_status(snapshot_id)
            
            if not status:
                print("Error checking job status, retrying...")
                await asyncio.sleep(5)
                continue
                
            print(f"Job status: {status}")
            
            if status == "ready":
                print("Job completed successfully!")
                return True
            elif status == "failed":
                print("Job failed!")
                return False
                
            # Wait before checking again
            await asyncio.sleep(5)
        
        print(f"Timed out after {max_wait_time} seconds")
        return False
    
    async def _process_results(self, snapshot_id: str, linkedin_url: str) -> Optional[Dict[str, Any]]:
        """Process BrightData results for a LinkedIn profile."""
        print(f"Processando resultados do snapshot_id: {snapshot_id} para URL: {linkedin_url}")
        results = download_results(snapshot_id)
        
        if not results:
            print("Nenhum resultado baixado do BrightData")
            return None
            
        print(f"Formato dos resultados: {type(results)}, Tamanho: {len(results) if isinstance(results, list) else 'N/A'}")
            
        # Find the profile data in the results
        # Look for objects with name, headline, etc. to identify actual profile data
        profile_candidates = []
        
        # Handle different data formats
        items_to_process = []
        if isinstance(results, list):
            items_to_process = results
        elif isinstance(results, dict):
            items_to_process = [results]
        else:
            print(f"Formato inesperado dos resultados: {type(results)}")
            return None
            
        print(f"Processando {len(items_to_process)} itens")
        
        for item in items_to_process:
            # Skip items that are clearly not profile data
            if not isinstance(item, dict):
                continue
                
            if "interaction" in item:
                print("Item parece ser uma interação, não um perfil")
                continue
                
            # Check if this is a profile object
            score = 0
            profile_fields = ["name", "headline", "summary", "location", "company", "position", "experience", "education"]
            found_fields = []
            
            for field in profile_fields:
                if field in item:
                    score += 1
                    found_fields.append(field)
            
            print(f"Item com pontuação {score}, campos encontrados: {found_fields}")
            
            # If it has multiple profile fields, it's likely a profile
            if score >= 2:
                profile_candidates.append((score, item))
        
        # Sort by score (highest first) and take the best match
        if profile_candidates:
            profile_candidates.sort(reverse=True, key=lambda x: x[0])
            best_candidate = profile_candidates[0]
            print(f"Melhor candidato encontrado com pontuação {best_candidate[0]}")
            profile_data = best_candidate[1]
            
            # Ensure we have a URL field
            if "linkedin_url" not in profile_data and "url" not in profile_data:
                print("Adicionando URL do LinkedIn aos dados do perfil")
                profile_data["linkedin_url"] = linkedin_url
                
            return profile_data
            
        # If no good candidates found, just return the first item
        if items_to_process:
            print("Nenhum bom candidato encontrado, usando o primeiro item")
            first_item = items_to_process[0]
            if isinstance(first_item, dict):
                # Add URL if missing
                if "linkedin_url" not in first_item and "url" not in first_item:
                    first_item["linkedin_url"] = linkedin_url
                return first_item
                
        print("Não foi possível encontrar dados de perfil válidos")
        return None
    
    def _get_existing_enrichment(self, linkedin_url: str, transcript_id: str) -> Optional[Dict[str, Any]]:
        """Get existing enrichment from Supabase."""
        try:
            response = supabase.table("linkedin_enrichments") \
                .select("*") \
                .eq("linkedin_url", linkedin_url) \
                .eq("transcript_id", transcript_id) \
                .execute()
                
            if response.data and len(response.data) > 0:
                return response.data[0]
        except Exception as e:
            print(f"Error querying Supabase: {str(e)}")
            
        return None
    
    def _create_pending_enrichment(self, linkedin_url: str, transcript_id: str, enrichment_id: str) -> None:
        """Create a pending enrichment in Supabase."""
        try:
            supabase.table("linkedin_enrichments").insert({
                "id": enrichment_id,
                "linkedin_url": linkedin_url,
                "transcript_id": transcript_id,
                "status": "pending",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }).execute()
        except Exception as e:
            print(f"Error creating enrichment: {str(e)}")
    
    def _update_enrichment_status(self, enrichment_id: str, status: str, message: str = None) -> None:
        """Update enrichment status in Supabase."""
        try:
            update_data = {
                "status": status,
                "updated_at": datetime.now().isoformat()
            }
            
            if message:
                if not update_data.get("profile_data"):
                    update_data["profile_data"] = {}
                update_data["profile_data"]["message"] = message
                
            supabase.table("linkedin_enrichments") \
                .update(update_data) \
                .eq("id", enrichment_id) \
                .execute()
        except Exception as e:
            print(f"Error updating enrichment status: {str(e)}")
    
    def _update_enrichment_with_profile(self, enrichment_id: str, profile_data: Dict[str, Any]) -> None:
        """Update enrichment with profile data in Supabase."""
        try:
            supabase.table("linkedin_enrichments") \
                .update({
                    "profile_data": profile_data,
                    "status": "ok",
                    "scraped_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat()
                }) \
                .eq("id", enrichment_id) \
                .execute()
        except Exception as e:
            print(f"Error updating enrichment with profile: {str(e)}")
    
    def _create_error_result(self, linkedin_url: str, transcript_id: str, 
                            message: str, enrichment_id: str = None) -> Dict[str, Any]:
        """Create an error result dictionary."""
        return {
            "linkedin_url": linkedin_url,
            "transcript_id": transcript_id,
            "status": "error",
            "message": message,
            "enrichment_id": enrichment_id,
            "profile_data": None
        }

async def main():
    """Main function for CLI usage."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Enrich LinkedIn profiles and store in Supabase")
    parser.add_argument("--url", help="LinkedIn profile URL to enrich")
    parser.add_argument("--transcript-id", help="Transcript ID to associate with the enrichment")
    parser.add_argument("--input", help="Path to a JSON file with URLs and transcript IDs")
    
    args = parser.parse_args()
    
    enricher = LinkedInProfileEnricher()
    
    if args.url and args.transcript_id:
        # Enrich a single profile
        result = await enricher.enrich_profile(args.url, args.transcript_id)
        print(json.dumps(result, indent=2))
    elif args.input:
        # Enrich multiple profiles from a file
        with open(args.input, "r") as f:
            urls_with_transcripts = json.load(f)
            
        results = await enricher.enrich_profiles(urls_with_transcripts)
        print(json.dumps(results, indent=2))
    else:
        parser.print_help()

if __name__ == "__main__":
    asyncio.run(main()) 