#!/usr/bin/env python3
"""
FastAPI server for LinkedIn profile enrichment using BrightData.
"""
import os
import asyncio
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, HttpUrl, UUID4
from dotenv import load_dotenv

# Import our LinkedIn enricher
from brightdata_supabase_integration import LinkedInProfileEnricher

# Load environment variables
load_dotenv()

# Create FastAPI app
app = FastAPI(
    title="LinkedIn Profile Enrichment API",
    description="API for enriching LinkedIn profiles using BrightData and storing in Supabase",
    version="1.0.0"
)

# Initialize the enricher
enricher = LinkedInProfileEnricher()

class LinkedInEnrichmentRequest(BaseModel):
    """Model for LinkedIn enrichment request."""
    linkedin_url: HttpUrl
    transcript_id: UUID4

class LinkedInBatchEnrichmentRequest(BaseModel):
    """Model for batch LinkedIn enrichment request."""
    profiles: List[LinkedInEnrichmentRequest]

class EnrichmentResponse(BaseModel):
    """Model for enrichment response."""
    linkedin_url: str
    transcript_id: str
    status: str
    message: Optional[str] = None
    enrichment_id: Optional[str] = None

@app.get("/")
async def read_root():
    """Root endpoint returning API info."""
    return {
        "name": "LinkedIn Profile Enrichment API",
        "version": "1.0.0",
        "description": "Enrich LinkedIn profiles with BrightData and store in Supabase",
        "endpoints": [
            {
                "path": "/enrich",
                "method": "POST",
                "description": "Enrich a single LinkedIn profile"
            },
            {
                "path": "/enrich-batch",
                "method": "POST",
                "description": "Enrich multiple LinkedIn profiles"
            }
        ]
    }

@app.post("/enrich", response_model=EnrichmentResponse)
async def enrich_profile(request: LinkedInEnrichmentRequest):
    """
    Enrich a LinkedIn profile and store in Supabase.
    
    This endpoint takes a LinkedIn profile URL and transcript ID,
    enriches the profile data using BrightData, and stores it in Supabase.
    """
    try:
        linkedin_url = str(request.linkedin_url)
        transcript_id = str(request.transcript_id)
        
        result = await enricher.enrich_profile(linkedin_url, transcript_id)
        
        return EnrichmentResponse(
            linkedin_url=linkedin_url,
            transcript_id=transcript_id,
            status=result.get("status", "error"),
            message=result.get("message"),
            enrichment_id=result.get("enrichment_id")
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error enriching profile: {str(e)}")

@app.post("/enrich-batch", response_model=List[EnrichmentResponse])
async def enrich_profiles(request: LinkedInBatchEnrichmentRequest, background_tasks: BackgroundTasks):
    """
    Enrich multiple LinkedIn profiles in batch mode.
    
    This endpoint takes a list of LinkedIn profile URLs and transcript IDs,
    and processes them asynchronously. For large batches, the processing
    is done in the background, and the response is returned immediately.
    """
    try:
        # Convert request to the format expected by the enricher
        urls_with_transcripts = [
            {
                "linkedin_url": str(item.linkedin_url),
                "transcript_id": str(item.transcript_id)
            }
            for item in request.profiles
        ]
        
        # For small batches (<=5), process synchronously
        if len(urls_with_transcripts) <= 5:
            results = await enricher.enrich_profiles(urls_with_transcripts)
            
            return [
                EnrichmentResponse(
                    linkedin_url=result.get("linkedin_url", ""),
                    transcript_id=result.get("transcript_id", ""),
                    status=result.get("status", "error"),
                    message=result.get("message"),
                    enrichment_id=result.get("enrichment_id")
                )
                for result in results
            ]
        
        # For larger batches, process in the background
        background_tasks.add_task(enricher.enrich_profiles, urls_with_transcripts)
        
        # Return immediate response that processing has started
        return [
            EnrichmentResponse(
                linkedin_url=item.get("linkedin_url", ""),
                transcript_id=item.get("transcript_id", ""),
                status="pending",
                message="Enrichment started in background"
            )
            for item in urls_with_transcripts
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error enriching profiles: {str(e)}")

if __name__ == "__main__":
    print("This module should be imported by app.py, not run directly.") 