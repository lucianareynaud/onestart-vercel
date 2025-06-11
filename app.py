import os
import uuid
import traceback
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime
import json
import time
import requests
from dotenv import load_dotenv

from fastapi import FastAPI, UploadFile, File, Request, HTTPException, Form, Depends
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from config import UPLOAD_DIR, SUPPORTED_FORMATS, OPENAI_API_KEY
from transcription import transcription_service
from db import supabase
from analysis_svc.pipeline import run_analysis_pipeline
from analysis_svc.utils.client_analyzer import analyze_client, extract_decision_criteria, identify_value_drivers
from analysis_svc.config.report_settings import get_client_specific_settings, get_funnel_stage_settings

# Import LinkedIn scraper functionality
from run_linkedin_scraper import save_stakeholders_json, run_scraper, get_profiles
# Import company website scraper
from run_website_scraper import run_website_scraper

# Import LinkedIn scraper functionality
from brightdata_scraper import BrightDataScraper
from brightdata_supabase_integration import LinkedInProfileEnricher
# Import company website scraper
from run_website_scraper import run_website_scraper

# Initialize app
app = FastAPI(title="Whisper Transcription")

# Create upload directory
UPLOAD_DIR.mkdir(exist_ok=True)

# Check app mode - ALWAYS use production mode
demo_mode = False  # Force production mode for all operations
logger.info("App running in production mode with OpenAI API")

# Log Supabase status
logger.info("=== Supabase Status ===")
logger.info(f"Demo mode: {supabase.is_demo_mode}")
logger.info(f"Anon client: {'Available' if supabase.client else 'Unavailable'}")
logger.info(f"Admin client: {'Available' if supabase.admin_client else 'Unavailable'}")
logger.info(f"Storage bucket: {os.getenv('SUPABASE_STORAGE_BUCKET', 'transcripts')}")
logger.info("=====================")

# Ensure output directories exist
os.makedirs("output", exist_ok=True)
os.makedirs("input", exist_ok=True)

# Set up static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Models
class TranscriptionResponse(BaseModel):
    transcript_id: str
    filename: str
    transcript: str
    duration_seconds: int
    language: str
    file_url: Optional[str] = None

class ErrorResponse(BaseModel):
    detail: str

class TranscriptListItem(BaseModel):
    id: str
    transcript: str
    storage_path: str
    duration_seconds: int
    language: str
    created_at: str
    
class SalesAnalysisResponse(BaseModel):
    transcript_id: str
    sales_data: Dict[str, Any]
    call_analysis: Dict[str, Any]

# LinkedIn Models
class StakeholderData(BaseModel):
    Company: str
    Stakeholders: List[str]
    BANT_Analysis: Optional[Dict[str, str]] = None
    Personalization_Context: Optional[str] = None
    Research_Topics: Optional[List[str]] = None
    Pain_Points: Optional[List[str]] = None
    Opportunities: Optional[List[str]] = None

class LinkedInScraperResponse(BaseModel):
    status: str
    job_id: str
    message: str

class LinkedInProfileResponse(BaseModel):
    profiles: List[Dict[str, Any]]
    count: int

# New models for data enrichment
class EnrichmentRequest(BaseModel):
    transcript_id: str
    company_website: Optional[str] = None
    linkedin_profiles: List[str] = []

class EnrichmentResponse(BaseModel):
    transcript_id: str
    report: str
    scraping_status: Dict[str, bool]

class UpdateAnalysisRequest(BaseModel):
    sales_data: Dict[str, Any]
    call_analysis: Dict[str, Any]

# Add new model for website enrichment database entries
class WebsiteEnrichment(BaseModel):
    id: Optional[str] = None
    transcript_id: str
    website_url: str
    scraped_at: Optional[str] = None
    parsed_data: Optional[Dict[str, Any]] = None
    status: str = "pending"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

# Add new model for LinkedIn enrichment database entries
class LinkedInEnrichment(BaseModel):
    id: Optional[str] = None
    transcript_id: str
    linkedin_url: str
    scraped_at: Optional[str] = None
    profile_data: Optional[Dict[str, Any]] = None
    status: str = "pending"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

# Routes
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Render the home page"""
    return templates.TemplateResponse(
        "index.html", 
        {"request": request}
    )

@app.post("/transcribe/", response_model=TranscriptionResponse)
async def transcribe(file: UploadFile = File(...)):
    """Transcribe an audio/video file and store the transcript in Supabase (without uploading the file)"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")
    
    # Check format
    if not transcription_service.validate_file(file.filename):
        supported_formats = ", ".join([".mp3", ".wav", ".m4a", ".mp4", ".mov", ".ogg"]) 
        raise HTTPException(
            status_code=400, 
            detail=f"Unsupported format. Supported formats include: {supported_formats}, and more."
        )
    
    # Generate a unique filename for local storage
    file_id = str(uuid.uuid4())
    file_ext = os.path.splitext(file.filename)[1].lower()
    temp_file_path = UPLOAD_DIR / f"{file_id}{file_ext}"
    
    try:
        # Save uploaded file locally first
        with open(temp_file_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        logger.info(f"File '{file.filename}' saved locally as '{temp_file_path}' ({os.path.getsize(temp_file_path)} bytes)")
        
        # Process the file (now only stores transcript, not the file)
        result = transcription_service.process_and_store(
            file_path=str(temp_file_path),
            original_filename=file.filename,
            language="pt"
        )
        
        # Verify the result contains required fields
        if not result or not isinstance(result, dict):
            raise ValueError(f"Invalid result from transcription service: {result}")
        
        for required_field in ["transcript_id", "transcript"]:
            if required_field not in result or not result[required_field]:
                raise ValueError(f"Missing required field in result: {required_field}")
        
        # Log results            
        if "transcript_id" in result:
            logger.info(f"✅ Transcript saved with ID: {result['transcript_id']}")
            
        # Delete the temporary file as we no longer need it
        try:
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
                logger.info(f"✅ Deleted temporary file after transcription: {temp_file_path}")
        except Exception as cleanup_error:
            logger.warning(f"Error deleting temporary file: {str(cleanup_error)}")
        
        # Remove upload_success field from response since we don't upload
        if "upload_success" in result:
            del result["upload_success"]
        
        # Also remove file_url as it's just a local reference
        if "file_url" in result:
            del result["file_url"]
            
        return result
    
    except Exception as e:
        # Clean up on error
        try:
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
                logger.info(f"Deleted temporary file after error: {temp_file_path}")
        except Exception as cleanup_error:
            logger.warning(f"Cleanup error: {str(cleanup_error)}")
        
        error_message = str(e)
        logger.error(f"Error during transcription: {error_message}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=error_message)

@app.post("/upload-transcript/", response_model=TranscriptionResponse)
async def upload_transcript(file: UploadFile = File(...)):
    """
    Upload a transcript text file directly, bypassing audio/video processing.
    The contents of the text file will be stored as a transcript.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")
    
    # Check if it's a text file
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in ['.txt', '.text']:
        raise HTTPException(
            status_code=400, 
            detail="Only .txt files are supported for direct transcript uploads."
        )
    
    try:
        # Read the transcript content
        content = await file.read()
        transcript_text = content.decode('utf-8')
        
        if not transcript_text or len(transcript_text.strip()) < 10:
            raise HTTPException(
                status_code=400,
                detail="The transcript file appears to be empty or too short."
            )
        
        # Generate a unique ID for the transcript
        transcript_id = str(uuid.uuid4())
        
        # Virtual storage path (not actually stored)
        storage_path = f"transcripts/{transcript_id}_{file.filename}"
        
        # Store the transcript in Supabase using the store_transcript method
        transcript_record = supabase.store_transcript(
            transcript_id=transcript_id,  # Pass the generated ID
            transcript_text=transcript_text,
            storage_path=storage_path,
            duration_seconds=0,  # No audio/video duration for text uploads
            language='pt'  # Default to Portuguese
        )
        
        if not transcript_record:
            raise HTTPException(
                status_code=500,
                detail="Failed to store transcript in database."
            )
        
        logger.info(f"✅ Direct transcript saved with ID: {transcript_record['id']}")
        
        # Return the response
        return {
            'transcript_id': transcript_record['id'],
            'filename': file.filename,
            'transcript': transcript_text,
            'duration_seconds': 0,
            'language': 'pt'
        }
        
    except HTTPException:
        raise
    
    except Exception as e:
        error_message = str(e)
        logger.error(f"Error during transcript upload: {error_message}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=error_message)

@app.get("/transcripts/")
async def list_transcripts(request: Request):
    """Get all stored transcripts and render them in a clean HTML template"""
    try:
        transcripts = supabase.get_all_transcripts()
        
        # Return HTML template when requested from browser
        if request.headers.get("accept", "").find("text/html") >= 0:
            return templates.TemplateResponse(
                "transcripts_list.html", 
                {"request": request, "transcripts": transcripts}
            )
        
        # Otherwise return JSON for API requests
        return transcripts
    except Exception as e:
        logger.error(f"Error listing transcripts: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/transcripts/{transcript_id}", response_model=dict)
async def get_transcript_api(transcript_id: str):
    """Get details of a specific transcript via API"""
    try:
        transcript = supabase.get_transcript(transcript_id)
        if not transcript:
            raise HTTPException(status_code=404, detail="Transcript not found")
        return transcript
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting transcript: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/transcript/{transcript_id}", response_class=HTMLResponse)
async def view_transcript(request: Request, transcript_id: str):
    """View a specific transcript in the web interface"""
    try:
        transcript = supabase.get_transcript(transcript_id)
        if not transcript:
            raise HTTPException(status_code=404, detail="Transcript not found")
        
        return templates.TemplateResponse(
            "transcript.html", 
            {"request": request, "transcript": transcript}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error viewing transcript: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/transcripts/{transcript_id}/analyze", response_model=SalesAnalysisResponse)
async def analyze_transcript(transcript_id: str):
    """
    Analyze a transcript for sales intelligence using LLM
    
    Args:
        transcript_id: ID of the transcript to analyze
        
    Returns:
        JSON with structured sales intelligence data
    """
    try:
        # Check if transcript exists
        transcript = supabase.get_transcript(transcript_id)
        if not transcript:
            raise HTTPException(status_code=404, detail="Transcript not found")
        
        # Validate transcript content
        transcript_text = transcript.get('transcript', '')
        if not transcript_text or len(transcript_text.strip()) < 10:
            raise HTTPException(status_code=400, detail="Transcript is too short or empty")
            
        logger.info(f"Starting analysis for transcript {transcript_id} with {len(transcript_text)} characters")
            
        # Run the analysis pipeline
        try:
            result = await run_analysis_pipeline(transcript_id)
            
            logger.info(f"Analysis pipeline result for {transcript_id}: {list(result.keys())}")
            logger.info(f"Call analysis present: {'call_analysis' in result}")
            if 'call_analysis' in result:
                logger.info(f"Call analysis keys: {list(result['call_analysis'].keys())}")
                
            # Ensure we return proper data structure even if some parts failed
            if 'sales_data' not in result:
                result['sales_data'] = {}
            if 'call_analysis' not in result:
                result['call_analysis'] = {}
                
            return result
        except Exception as pipeline_error:
            logger.error(f"Error in analysis pipeline: {str(pipeline_error)}")
            traceback.print_exc()
            # Return a more specific error message
            raise HTTPException(status_code=500, 
                detail=f"Analysis pipeline error: {str(pipeline_error)}")
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error analyzing transcript: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Analysis error: {str(e)}")

@app.post("/linkedin/scrape/", response_model=LinkedInScraperResponse)
async def scrape_linkedin(data: StakeholderData):
    """
    Trigger LinkedIn scraping for the provided stakeholders.
    
    This endpoint uses BrightData API to scrape LinkedIn profiles for
    the stakeholders and company provided.
    """
    try:
        # Generate a unique job ID
        job_id = str(uuid.uuid4())
        
        # Initialize scraper
        scraper = BrightDataScraper()
        enricher = LinkedInProfileEnricher()
        
        # Prepare stakeholder data for processing and storage
        stakeholder_data = {
            "Company": data.Company,
            "Stakeholders": data.Stakeholders,
            "BANT_Analysis": data.BANT_Analysis or {},
            "Personalization_Context": data.Personalization_Context or "",
            "Research_Topics": data.Research_Topics or [],
            "Pain_Points": data.Pain_Points or [],
            "Opportunities": data.Opportunities or []
        }
        
        # Store the request data in Supabase instead of saving to a file
        try:
            client_to_use = supabase.admin_client if supabase.admin_client else supabase.client
            if client_to_use:
                client_to_use.table('external_cache').insert({
                    "url": f"linkedin_request_{job_id}",
                    "body": stakeholder_data,
                    "fetched_at": supabase.get_current_timestamp()
                }).execute()
                logger.info(f"Stored LinkedIn request data in Supabase for job: {job_id}")
        except Exception as e:
            logger.warning(f"Could not store LinkedIn request data in Supabase: {e}")
        
        status = "success"
        message = f"Scraping job started with ID: {job_id}"
        
        # For each stakeholder, attempt to find and scrape LinkedIn profile
        profiles = []
        company = data.Company
        
        for stakeholder in data.Stakeholders:
            # Create a placeholder entry noting that profile search is needed
            fallback_profile = {
                "name": stakeholder,
                "headline": "LinkedIn profile needs to be selected in UI",
                "company": company,
                "profile_url": "",
                "location": "Unknown",
                "about": "The user should select a LinkedIn profile URL through the UI.",
                "stakeholder_id": stakeholder
            }
            
            try:
                # The scraping should only be triggered once the user has selected
                # a valid LinkedIn profile URL from the UI
                profile_data = None
                
                if profile_data:
                    # Add reference to original stakeholder
                    profile_data["stakeholder_id"] = stakeholder
                    profiles.append(profile_data)
                else:
                    # Use fallback profile
                    profiles.append(fallback_profile)
                    
            except Exception as e:
                logger.error(f"Error scraping profile for {stakeholder}: {str(e)}")
                profiles.append(fallback_profile)
        
        # Store profiles in Supabase instead of saving to a local file
        try:
            client_to_use = supabase.admin_client if supabase.admin_client else supabase.client
            if client_to_use:
                client_to_use.table('external_cache').insert({
                    "url": f"linkedin_profiles_{job_id}",
                    "body": profiles,
                    "fetched_at": supabase.get_current_timestamp()
                }).execute()
                logger.info(f"Stored {len(profiles)} profiles in Supabase for job: {job_id}")
        except Exception as e:
            logger.warning(f"Could not store LinkedIn profiles in Supabase: {e}")
        
        return {
            "status": status,
            "job_id": job_id,
            "message": f"{message}. Processed {len(profiles)} stakeholders."
        }
    
    except Exception as e:
        logger.error(f"Error triggering LinkedIn scraper: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/linkedin/profiles/{job_id}", response_model=LinkedInProfileResponse)
async def get_linkedin_profiles(job_id: str):
    """
    Get LinkedIn profiles for a specific job ID.
    
    This endpoint returns the profiles found by the scraper for the given job ID.
    """
    try:
        # Check if the job exists in Supabase
        client_to_use = supabase.admin_client if supabase.admin_client else supabase.client
        if not client_to_use:
            raise HTTPException(
                status_code=500,
                detail="No database connection available"
            )
            
        # Query the external_cache table for the profiles
        result = client_to_use.table('external_cache').select('body').eq('url', f"linkedin_profiles_{job_id}").execute()
        
        if not result.data or len(result.data) == 0:
            raise HTTPException(
                status_code=404, 
                detail=f"No profiles found for job ID: {job_id}"
            )
            
        # Get the profiles from the result
        profiles = result.data[0].get('body', [])
        
        return {
            "profiles": profiles,
            "count": len(profiles)
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting LinkedIn profiles: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/transcripts/{transcript_id}/update-analysis", response_model=Dict[str, Any])
async def update_analysis(transcript_id: str, request: UpdateAnalysisRequest):
    """
    Update the analysis results for a transcript.
    
    Args:
        transcript_id: ID of the transcript to update
        request: Updated sales data
        
    Returns:
        Updated analysis data
    """
    try:
        # Check if transcript exists
        transcript = supabase.get_transcript(transcript_id)
        if not transcript:
            raise HTTPException(status_code=404, detail="Transcript not found")
            
        # Update the analysis in the database
        # Store analysis results in a new "analyses" table if it exists
        # Otherwise just return the updated data
        try:
            # Try to update in the analyses table first (if it exists)
            analysis_data = {
                "transcript_id": transcript_id,
                "updated_at": supabase.get_current_timestamp()
            }
            
            # Add the data that was sent in the request
            if hasattr(request, 'sales_data') and request.sales_data:
                analysis_data["sales_data"] = request.sales_data
                
            if hasattr(request, 'call_analysis') and request.call_analysis:
                analysis_data["call_analysis"] = request.call_analysis
            
            # Check if there's an existing analysis to update
            existing = None
            try:
                # Try to query the analyses table
                client_to_use = supabase.admin_client if supabase.admin_client else supabase.client
                result = client_to_use.table('analyses').select('*').eq('transcript_id', transcript_id).execute()
                if result.data and len(result.data) > 0:
                    existing = result.data[0]
            except Exception as e:
                logger.warning(f"Error checking for existing analysis: {str(e)}")
            
            if existing:
                # Update existing analysis
                update_data = {"updated_at": supabase.get_current_timestamp()}
                
                if hasattr(request, 'sales_data') and request.sales_data:
                    update_data["sales_data"] = request.sales_data
                    
                if hasattr(request, 'call_analysis') and request.call_analysis:
                    update_data["call_analysis"] = request.call_analysis
                    
                client_to_use.table('analyses').update(update_data).eq('id', existing['id']).execute()
                logger.info(f"Updated existing analysis for transcript {transcript_id}")
            else:
                # Create new analysis
                client_to_use.table('analyses').insert(analysis_data).execute()
                logger.info(f"Created new analysis for transcript {transcript_id}")
        except Exception as db_error:
            # Log the error but don't fail - we'll just return the data without storing it
            logger.warning(f"Could not save analysis to database: {str(db_error)}")
        
        logger.info(f"Updated analysis for transcript {transcript_id}")
        
        response = {"transcript_id": transcript_id}
        
        if hasattr(request, 'sales_data') and request.sales_data:
            response["sales_data"] = request.sales_data
            
        if hasattr(request, 'call_analysis') and request.call_analysis:
            response["call_analysis"] = request.call_analysis
            
        return response
    except Exception as e:
        logger.error(f"Error updating analysis: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/enrich-data/", response_model=EnrichmentResponse)
async def enrich_data(data: EnrichmentRequest):
    """
    Enrich the analysis with additional data from LinkedIn profiles and company website.
    
    This endpoint takes LinkedIn profile URLs and a company website URL, processes them
    using BrightData API and Scrapy, and passes the enriched data to an LLM to generate
    a sales intelligence report.
    
    Args:
        data: EnrichmentRequest containing transcript_id, company_website, and linkedin_profiles
        
    Returns:
        EnrichmentResponse with the generated sales intelligence report
    """
    try:
        # Check if transcript exists
        transcript_id = data.transcript_id
        transcript = supabase.get_transcript(transcript_id)
        if not transcript:
            raise HTTPException(status_code=404, detail="Transcript not found")
        
        # First run the analysis pipeline to ensure we have analysis data
        await run_analysis_pipeline(transcript_id)
        
        # Status tracking
        scraping_status = {
            "website": False,
            "linkedin": False
        }
        
        # Process company website if provided
        company_data = {}
        if data.company_website:
            # Store the data in Supabase for tracking
            website_id = await store_website_task(transcript_id, data.company_website)
            
            # Run the Scrapy scraper for the company website
            try:
                logger.info(f"Scraping website: {data.company_website}")
                # This would typically call a Scrapy process or API
                # For now, we'll use a simplified version
                company_data = await scrape_website(data.company_website)
                
                # Update the status in the database if successful
                if company_data:
                    await update_website_status(website_id, "completed", company_data)
                    scraping_status["website"] = True
                else:
                    await update_website_status(website_id, "failed")
            except Exception as scrape_error:
                logger.error(f"Error scraping website: {str(scrape_error)}")
                await update_website_status(website_id, "failed")
        
        # Process LinkedIn profiles if provided
        linkedin_profiles = []
        if data.linkedin_profiles:
            # Import the BrightData LinkedIn enricher
            from brightdata_supabase_integration import LinkedInProfileEnricher
            
            # Initialize the enricher
            enricher = LinkedInProfileEnricher()
            
            # Create a list of LinkedIn URLs with transcript IDs
            linkedin_urls_with_transcripts = [
                {"linkedin_url": url, "transcript_id": transcript_id}
                for url in data.linkedin_profiles
            ]
            
            # Process all LinkedIn profiles in a single batch
            logger.info(f"Enriching {len(data.linkedin_profiles)} LinkedIn profiles with BrightData")
            enrichment_results = await enricher.enrich_profiles(linkedin_urls_with_transcripts)
            
            # Process the results
            for result in enrichment_results:
                if result.get("status") == "ok" and result.get("profile_data"):
                    linkedin_profiles.append(result.get("profile_data"))
                    scraping_status["linkedin"] = True
                    logger.info(f"Successfully enriched LinkedIn profile: {result.get('linkedin_url')}")
                else:
                    error_msg = result.get("message", "Unknown error")
                    logger.warning(f"Failed to enrich LinkedIn profile: {result.get('linkedin_url')}. Error: {error_msg}")
        
        # Generate the report using the enriched data
        report_html = await generate_sales_intelligence_report(
            transcript_id, 
            linkedin_profiles, 
            company_data
        )
        
        return {
            "transcript_id": transcript_id,
            "report": report_html,
            "scraping_status": scraping_status
        }
    except Exception as e:
        logger.error(f"Error in enrichment process: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/linkedin/enrich/", response_model=List[Dict[str, Any]])
async def enrich_linkedin_profiles(request: Request):
    """
    Enrich LinkedIn profiles using the BrightData API.
    
    This endpoint takes a list of LinkedIn profile URLs and transcript IDs,
    and enriches them with data from the BrightData API.
    
    The request body should be a JSON array of objects with:
    - linkedin_url: The LinkedIn profile URL to enrich
    - transcript_id: The transcript ID to associate with the enrichment
    
    Returns:
        List of enrichment results
    """
    try:
        # Parse request body
        data = await request.json()
        
        # Validate input
        if not isinstance(data, list):
            raise HTTPException(status_code=400, detail="Request body must be an array")
            
        for item in data:
            if not isinstance(item, dict):
                raise HTTPException(status_code=400, detail="Each item must be an object")
            if "linkedin_url" not in item:
                raise HTTPException(status_code=400, detail="Each item must have a linkedin_url field")
            if "transcript_id" not in item:
                raise HTTPException(status_code=400, detail="Each item must have a transcript_id field")
        
        # Import the BrightData LinkedIn enricher
        from brightdata_supabase_integration import LinkedInProfileEnricher
        
        # Initialize the enricher
        enricher = LinkedInProfileEnricher()
        
        # Process all LinkedIn profiles in a single batch
        logger.info(f"Enriching {len(data)} LinkedIn profiles with BrightData")
        results = await enricher.enrich_profiles(data)
        
        return results
        
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        logger.error(f"Error enriching LinkedIn profiles: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/analyze-text", response_model=SalesAnalysisResponse)
async def analyze_pasted_text(request: Request):
    """
    Analyze directly pasted text without requiring it to be uploaded as a transcript first.
    This is useful for quick analysis of copy-pasted content.
    
    Args:
        request: The request containing the text to analyze
        
    Returns:
        JSON with structured sales intelligence data
    """
    try:
        # Parse the request body to get the text
        body = await request.json()
        text = body.get("text", "")
        
        if not text or len(text.strip()) < 10:
            raise HTTPException(status_code=400, detail="Text is too short or empty. Please provide more content to analyze.")
            
        logger.info(f"Analyzing directly pasted text with {len(text)} characters")
        
        # Create a temporary transcript for this analysis
        transcript_id = str(uuid.uuid4())
        
        # Store the transcript in Supabase
        transcript_record = supabase.store_transcript(
            transcript_id=transcript_id,
            transcript_text=text,
            storage_path=f"temp_transcripts/{transcript_id}.txt",
            duration_seconds=0,
            language="pt"  # Default to Portuguese
        )
        
        if not transcript_record:
            raise HTTPException(status_code=500, detail="Failed to store temporary transcript")
            
        # Run the analysis pipeline on the temporary transcript
        try:
            result = await run_analysis_pipeline(transcript_id)
            
            # Ensure we return proper data structure even if some parts failed
            if 'sales_data' not in result:
                result['sales_data'] = {}
            if 'call_analysis' not in result:
                result['call_analysis'] = {}
                
            return result
        except Exception as pipeline_error:
            logger.error(f"Error in direct text analysis pipeline: {str(pipeline_error)}")
            traceback.print_exc()
            raise HTTPException(status_code=500, 
                detail=f"Analysis pipeline error: {str(pipeline_error)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error analyzing pasted text: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Analysis error: {str(e)}")

async def generate_sales_intelligence_report(
    transcript_id: str, 
    linkedin_profiles: List[Dict[str, Any]], 
    company_data: Dict[str, Any]
) -> str:
    """
    Generate a sales intelligence report based on transcript analysis and enriched data.
    
    Args:
        transcript_id: ID of the transcript
        linkedin_profiles: LinkedIn profiles data
        company_data: Company website data
        
    Returns:
        HTML formatted sales intelligence report
    """
    try:
        # Get transcript data
        transcript = supabase.get_transcript(transcript_id)
        if not transcript:
            return "<p>Transcrição não encontrada</p>"
        
        # Get the transcript text
        transcript_text = transcript.get("transcript", "")
        
        # Get sales analysis data - FIRST run analysis pipeline to ensure data exists
        try:
            # Remover await pois a função pode não ser assíncrona neste contexto
            analysis_result = run_analysis_pipeline(transcript_id)
            sales_data = analysis_result.get("sales_data", {}) if analysis_result else {}
        except Exception as e:
            logger.warning(f"Error running analysis pipeline: {e}")
            # Tentar obter o resultado diretamente da base
            sales_data = {}
        
        # Also check for updated analysis data in the database
        try:
            # Try to query the analyses table for possible updated data
            client_to_use = supabase.admin_client if supabase.admin_client else supabase.client
            result = client_to_use.table('analyses').select('*').eq('transcript_id', transcript_id).execute()
            if result.data and len(result.data) > 0 and result.data[0].get('sales_data'):
                # Use the updated analysis data instead
                sales_data = result.data[0]['sales_data']
                logger.info(f"Using updated analysis data from database for transcript {transcript_id}")
        except Exception as e:
            logger.warning(f"Could not check for updated analysis: {str(e)}")
        
        # Check if we have OPENAI_API_KEY for calling the LLM
        if not OPENAI_API_KEY or OPENAI_API_KEY == "demo_mode":
            # If in demo mode, return a basic report using the template-based approach
            logger.warning("No OpenAI API key available for comprehensive report generation, using template")
            return generate_template_based_report(sales_data, linkedin_profiles, company_data)
            
        # Read the report generation prompt
        prompt_path = Path(__file__).parent / "analysis_svc" / "prompts" / "sales_report_pt.txt"
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                report_prompt = f.read()
        except Exception as e:
            logger.error(f"Could not read report prompt: {e}")
            report_prompt = "Gere um relatório de inteligência de vendas baseado nos dados fornecidos."
        
        # Enrich the data structure for better LLM context
        enriched_context = prepare_enriched_context(sales_data, linkedin_profiles, company_data, transcript_text)
        
        # Call the LLM with the enriched context
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        
        try:
            logger.info("Calling OpenAI to generate comprehensive sales report")
            
            response = client.chat.completions.create(
                model="gpt-4o",  # Using the most capable model
                messages=[
                    {"role": "system", "content": report_prompt},
                    {"role": "user", "content": enriched_context}
                ],
                temperature=0.2,  # Lower temperature for more focused and precise results
                max_tokens=4000  # Allow a substantial response
            )
            
            # Extract the HTML report
            report_html = response.choices[0].message.content
            
            # Remove markdown code block markers if present
            report_html = report_html.replace("```html", "").replace("```", "").strip()
            
            # Add styling from the old template to ensure consistent look
            report_html += """
            <style>
                .sales-intelligence-report {
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
                    color: #333;
                    line-height: 1.6;
                    max-width: 1200px;
                    margin: 0 auto;
                    padding: 20px;
                }
                
                .report-section {
                    margin-bottom: 2rem;
                    padding-bottom: 1.5rem;
                    border-bottom: 1px solid #eee;
                    background-color: #fff;
                    border-radius: 8px;
                    box-shadow: 0 1px 3px rgba(0,0,0,0.05);
                    padding: 20px;
                }
                
                .report-section h3 {
                    color: #7158e2;
                    margin-bottom: 1rem;
                    padding-bottom: 0.5rem;
                    border-bottom: 2px solid #7158e2;
                    font-size: 1.5rem;
                }
                
                .spin-item, .bant-item {
                    margin-bottom: 1.25rem;
                    background-color: #f9f9f9;
                    padding: 15px;
                    border-radius: 6px;
                }
                
                .spin-item h4, .bant-item h4 {
                    color: #555;
                    margin-bottom: 0.5rem;
                    font-weight: 600;
                }
                
                .two-columns {
                    display: flex;
                    gap: 2rem;
                }
                
                @media (max-width: 768px) {
                    .two-columns {
                        flex-direction: column;
                    }
                }
                
                .column {
                    flex: 1;
                    background-color: #f9f9f9;
                    padding: 15px;
                    border-radius: 6px;
                }
                
                .stakeholders-map {
                    background: #f5f7ff;
                    padding: 1.5rem;
                    border-radius: 0.5rem;
                }
                
                ul, ol {
                    padding-left: 1.5rem;
                    margin-bottom: 1rem;
                }
                
                li {
                    margin-bottom: 0.75rem;
                }
                
                .executive-summary {
                    background-color: #f0f8ff;
                    padding: 1.5rem;
                    border-radius: 0.5rem;
                    border-left: 4px solid #7158e2;
                    font-size: 1.1rem;
                }
                
                .stakeholders-table, .objections-table, .timeline-table {
                    width: 100%;
                    border-collapse: collapse;
                    margin: 1rem 0;
                    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
                    border-radius: 8px;
                    overflow: hidden;
                }
                
                .stakeholders-table th, .objections-table th, .timeline-table th {
                    background-color: #7158e2;
                    color: white;
                    text-align: left;
                    padding: 12px 15px;
                    font-weight: 600;
                }
                
                .stakeholders-table td, .objections-table td, .timeline-table td {
                    padding: 12px 15px;
                    border-bottom: 1px solid #eee;
                }
                
                .stakeholders-table tr:nth-child(even), .objections-table tr:nth-child(even), .timeline-table tr:nth-child(even) {
                    background-color: #f8f8f8;
                }
                
                .stakeholders-table tr:hover, .objections-table tr:hover, .timeline-table tr:hover {
                    background-color: #f0f0f0;
                    transition: background-color 0.3s ease;
                }
                
                .phase {
                    margin-bottom: 1.75rem;
                    background-color: #f9f9f9;
                    padding: 15px;
                    border-radius: 6px;
                }
                
                .phase h4 {
                    color: #7158e2;
                    margin-bottom: 0.75rem;
                    font-weight: 600;
                }
                
                .value-metrics, .differentiators {
                    margin-top: 1.5rem;
                    background-color: #f5f7ff;
                    padding: 15px;
                    border-radius: 6px;
                }
                
                .value-metrics h4, .differentiators h4 {
                    color: #7158e2;
                    margin-bottom: 0.75rem;
                    font-weight: 600;
                }
                
                /* Estilos adicionais para elementos de destaque */
                .highlight-box {
                    background-color: #fff8e1;
                    border-left: 4px solid #ffc107;
                    padding: 15px;
                    margin: 15px 0;
                    border-radius: 0 6px 6px 0;
                }
                
                .action-item {
                    background-color: #e8f5e9;
                    border-left: 4px solid #4caf50;
                    padding: 10px 15px;
                    margin: 8px 0;
                    border-radius: 0 6px 6px 0;
                }
                
                /* Efeitos de impressão */
                @media print {
                    .sales-intelligence-report {
                        max-width: 100%;
                        padding: 0;
                    }
                    
                    .report-section {
                        box-shadow: none;
                        border: 1px solid #ddd;
                        break-inside: avoid;
                    }
                    
                    .stakeholders-table, .objections-table, .timeline-table {
                        box-shadow: none;
                        border: 1px solid #ddd;
                    }
                    
                    .executive-summary {
                        background-color: #f9f9f9 !important;
                        color: #000 !important;
                    }
                }
                
                /* Botão de impressão */
                .print-button {
                    position: sticky;
                    top: 20px;
                    right: 20px;
                    float: right;
                    background-color: #7158e2;
                    color: white;
                    border: none;
                    padding: 10px 15px;
                    border-radius: 4px;
                    cursor: pointer;
                    font-weight: 600;
                    transition: background-color 0.3s ease;
                    z-index: 100;
                }
                
                .print-button:hover {
                    background-color: #5e48b5;
                }
                
                /* Script para impressão */
                .sales-intelligence-report::before {
                    content: '';
                    display: block;
                    clear: both;
                }
            </style>
            <script>
                document.addEventListener('DOMContentLoaded', function() {
                    // Adicionar botão de impressão
                    const reportDiv = document.querySelector('.sales-intelligence-report');
                    if (reportDiv) {
                        const printButton = document.createElement('button');
                        printButton.className = 'print-button';
                        printButton.textContent = 'Imprimir Relatório';
                        printButton.onclick = function() {
                            window.print();
                        };
                        reportDiv.prepend(printButton);
                    }
                });
            </script>
            """
            
            return report_html
            
        except Exception as llm_error:
            logger.error(f"Error calling OpenAI for report generation: {llm_error}")
            # Fallback to template-based report
            return generate_template_based_report(sales_data, linkedin_profiles, company_data)
        
    except Exception as e:
        logger.error(f"Error generating sales intelligence report: {str(e)}")
        traceback.print_exc()
        return f"<p>Erro ao gerar relatório: {str(e)}</p>"

def prepare_enriched_context(
    sales_data: Dict[str, Any],
    linkedin_profiles: List[Dict[str, Any]],
    company_data: Dict[str, Any],
    transcript_text: str
) -> str:
    """
    Prepares a rich, structured context for the LLM with all available data properly organized.
    
    Args:
        sales_data: The sales analysis data
        linkedin_profiles: LinkedIn profiles data
        company_data: Company website data
        transcript_text: The transcript text
        
    Returns:
        A rich, structured context string for the LLM
    """
    try:
        # Analisar características do cliente para personalização
        client_analysis = analyze_client(transcript_text, sales_data, company_data)
        industry_type = client_analysis.get("industry", "general")
        funnel_stage = client_analysis.get("funnel_stage", "consideration")
        
        # Obter configurações específicas baseadas no tipo de cliente e fase do funil
        industry_settings = get_client_specific_settings(industry_type)
        funnel_settings = get_funnel_stage_settings(funnel_stage)
        
        # Extrair critérios de decisão e impulsionadores de valor
        decision_criteria = extract_decision_criteria(transcript_text, sales_data)
        value_drivers = identify_value_drivers(sales_data, industry_type)
        
        # Adicionar informações de análise de cliente ao contexto
        client_context = f"""
        ## ANÁLISE ESTRATÉGICA DO CLIENTE
        
        **Tipo de indústria detectado:** {industry_type}
        **Fase do funil de vendas:** {funnel_stage}
        **Foco recomendado:** {funnel_settings.get('focus', 'diferenciação competitiva')}
        **Tipo de conteúdo recomendado:** {funnel_settings.get('content_type', 'comparativo e detalhado')}
        **Call-to-action recomendado:** {funnel_settings.get('call_to_action', 'análise detalhada de necessidades')}
        
        **Áreas de foco para esta indústria:**
        {', '.join(industry_settings.get('focus_areas', ['inovação', 'eficiência', 'redução de custos']))}
        
        **Terminologia relevante para esta indústria:**
        {', '.join(industry_settings.get('terminology', ['ROI', 'eficiência', 'otimização']))}
        
        **Critérios de decisão identificados:**
        """
        if decision_criteria:
            for criterion in decision_criteria[:5]:  # Limitar a 5 critérios para não sobrecarregar
                client_context += f"- {criterion}\n"
        else:
            client_context += "- Nenhum critério específico identificado\n"
        
        client_context += """
        **Impulsionadores de valor por categoria:**
        """
        
        for category, drivers in value_drivers.items():
            if drivers:
                client_context += f"\n*{category.title()}:*\n"
                for driver in drivers:
                    client_context += f"- {driver}\n"
    except Exception as e:
        # Em caso de erro na análise do cliente, apenas log e continua sem essa parte
        logger.error(f"Error in client analysis: {e}")
        client_context = ""
    
    # Start with a brief version of the transcript
    short_transcript = transcript_text[:1500] + "..." if len(transcript_text) > 1500 else transcript_text
    
    # Build structured sections for the context
    context_sections = []
    
    # Add company overview section
    company_name = sales_data.get('empresa', company_data.get('name', 'Empresa'))
    context_sections.append(f"""
    ## VISÃO GERAL DA EMPRESA
    
    **Nome:** {company_name}
    **Descrição:** {company_data.get('about', sales_data.get('contexto_personalizacao', 'Não disponível'))}
    """)
    
    # Add client analysis if available
    if client_context:
        context_sections.append(client_context)
    
    # Add stakeholders section with enriched LinkedIn data
    stakeholders_section = """
    ## STAKEHOLDERS-CHAVE
    
    """
    if linkedin_profiles:
        for i, profile in enumerate(linkedin_profiles):
            profile_name = profile.get('name', f"Stakeholder {i+1}")
            profile_title = profile.get('headline', 'Cargo não disponível')
            profile_company = profile.get('company', company_name)
            profile_experience = profile.get('experience', [])
            profile_education = profile.get('education', [])
            
            stakeholders_section += f"""
            ### {profile_name}
            **Cargo Atual:** {profile_title}
            **Empresa:** {profile_company}
            **URL do Perfil:** {profile.get('profile_url', 'N/A')}
            
            **Experiência Profissional Relevante:**
            """
            
            if profile_experience:
                for exp in profile_experience[:3]:  # Include top 3 experiences
                    exp_role = exp.get('title', 'Cargo não especificado')
                    exp_company = exp.get('company', 'Empresa não especificada')
                    exp_duration = exp.get('duration', 'Duração não especificada')
                    stakeholders_section += f"- {exp_role} em {exp_company} ({exp_duration})\n"
            else:
                stakeholders_section += "- Informações de experiência não disponíveis\n"
                
            stakeholders_section += """
            **Educação Relevante:**
            """
            
            if profile_education:
                for edu in profile_education[:2]:  # Include top 2 education entries
                    edu_school = edu.get('school', 'Instituição não especificada')
                    edu_degree = edu.get('degree', 'Grau não especificado')
                    stakeholders_section += f"- {edu_degree} em {edu_school}\n"
            else:
                stakeholders_section += "- Informações de educação não disponíveis\n"
                
            # Adicionar interesses e atividades recentes quando disponíveis
            if profile.get('interests'):
                stakeholders_section += "\n**Interesses:**\n"
                for interest in profile.get('interests', [])[:5]:
                    stakeholders_section += f"- {interest}\n"
                    
            if profile.get('activities'):
                stakeholders_section += "\n**Atividades Recentes:**\n"
                for activity in profile.get('activities', [])[:3]:
                    stakeholders_section += f"- {activity}\n"
    else:
        stakeholders_list = sales_data.get('stakeholders', [])
        if stakeholders_list:
            for stakeholder in stakeholders_list:
                stakeholders_section += f"- {stakeholder} (Detalhes do LinkedIn não disponíveis)\n"
        else:
            stakeholders_section += "- Nenhum stakeholder identificado\n"
    
    context_sections.append(stakeholders_section)
    
    # Add SPIN analysis section
    spin_data = sales_data.get('spin', {})
    context_sections.append(f"""
    ## ANÁLISE SPIN
    
    **Situação:** {spin_data.get('situacao', 'Não identificada')}
    
    **Problema:** {spin_data.get('problema', 'Não identificado')}
    
    **Implicação:** {spin_data.get('implicacao', 'Não identificada')}
    
    **Necessidade:** {spin_data.get('necessidade', 'Não identificada')}
    """)
    
    # Add BANT analysis section
    bant_data = sales_data.get('bant', {})
    context_sections.append(f"""
    ## ANÁLISE BANT
    
    **Budget (Orçamento):** {bant_data.get('budget', 'Não identificado')}
    
    **Authority (Autoridade):** {bant_data.get('authority', 'Não identificada')}
    
    **Need (Necessidade):** {bant_data.get('need', 'Não identificada')}
    
    **Timeline (Cronograma):** {bant_data.get('timeline', 'Não identificado')}
    """)
    
    # Add pain points and opportunities section
    pains = sales_data.get('dores', [])
    opportunities = sales_data.get('oportunidades', [])
    
    pains_section = "## DORES E OPORTUNIDADES\n\n**Dores Identificadas:**\n"
    if pains:
        for pain in pains:
            pains_section += f"- {pain}\n"
    else:
        pains_section += "- Nenhuma dor específica identificada\n"
    
    pains_section += "\n**Oportunidades:**\n"
    if opportunities:
        for opp in opportunities:
            pains_section += f"- {opp}\n"
    else:
        pains_section += "- Nenhuma oportunidade específica identificada\n"
    
    context_sections.append(pains_section)
    
    # Add company website data section
    if company_data and not company_data.get("error"):
        website_section = """
        ## DADOS DO SITE DA EMPRESA
        """
        
        # Add services/products if available
        services = company_data.get('services', [])
        if services:
            website_section += "\n**Serviços/Produtos:**\n"
            for service in services:
                service_name = service.get('name', '')
                service_desc = service.get('description', '')
                website_section += f"- {service_name}"
                if service_desc:
                    website_section += f": {service_desc}\n"
                else:
                    website_section += "\n"
        
        # Add team information if available
        team = company_data.get('team', [])
        if team:
            website_section += "\n**Equipe:**\n"
            for member in team:
                member_name = member.get('name', '')
                member_position = member.get('position', '')
                website_section += f"- {member_name}"
                if member_position:
                    website_section += f" - {member_position}\n"
                else:
                    website_section += "\n"
        
        # Add technologies if available
        technologies = company_data.get('technologies', [])
        if technologies:
            website_section += "\n**Tecnologias Mencionadas:**\n"
            for tech in technologies:
                website_section += f"- {tech}\n"
                
        context_sections.append(website_section)
    
    # Add mentions of other companies/platforms
    marcas = sales_data.get('marcas', [])
    if marcas:
        marcas_section = """
        ## EMPRESAS/PLATAFORMAS MENCIONADAS
        """
        for marca in marcas:
            marcas_section += f"- {marca}\n"
        context_sections.append(marcas_section)
    
    # Add transcript excerpt at the end
    context_sections.append(f"""
    ## TRECHO DA TRANSCRIÇÃO DA REUNIÃO
    
    {short_transcript}
    """)
    
    # Combine all sections
    return "\n\n".join(context_sections)

def generate_template_based_report(
    sales_data: Dict[str, Any],
    linkedin_profiles: List[Dict[str, Any]],
    company_data: Dict[str, Any]
) -> str:
    """
    Fallback function to generate a basic report using templates when LLM is not available.
    """
    report = f"""
    <div class="sales-report">
        <h3>Relatório de Inteligência de Vendas</h3>
        
        <div class="report-section">
            <h4>Dados da Reunião</h4>
            <p><strong>Empresa:</strong> {sales_data.get('empresa', 'Não identificada')}</p>
            <p><strong>Contatos-chave:</strong> {', '.join(sales_data.get('stakeholders', ['Não identificados']))}</p>
        </div>
        
        <div class="report-section">
            <h4>Análise SPIN</h4>
            <div class="spin-analysis">
                <h5>Situação: </h5>
                <p>{sales_data.get('spin', {}).get('situacao', 'Não identificada')}</p>
                
                <h5>Problema: </h5>
                <p>{sales_data.get('spin', {}).get('problema', 'Não identificado')}</p>
                
                <h5>Implicação: </h5>
                <p>{sales_data.get('spin', {}).get('implicacao', 'Não identificada')}</p>
                
                <h5>Necessidade: </h5>
                <p>{sales_data.get('spin', {}).get('necessidade', 'Não identificada')}</p>
            </div>
        </div>
        
        <div class="report-section">
            <h4>Análise BANT</h4>
            <div class="bant-analysis">
                <h5>Budget (Orçamento): </h5>
                <p>{sales_data.get('bant', {}).get('budget', 'Não identificado')}</p>
                
                <h5>Authority (Autoridade): </h5>
                <p>{sales_data.get('bant', {}).get('authority', 'Não identificada')}</p>
                
                <h5>Need (Necessidade): </h5>
                <p>{sales_data.get('bant', {}).get('need', 'Não identificada')}</p>
                
                <h5>Timeline (Cronograma): </h5>
                <p>{sales_data.get('bant', {}).get('timeline', 'Não identificado')}</p>
            </div>
        </div>
        
        <div class="report-section">
            <h4>Perfis do LinkedIn</h4>
            <div class="profiles-list">
    """
    
    # Add LinkedIn profiles information
    for profile in linkedin_profiles:
        report += f"""
                <div class="profile-card">
                    <h5>{profile.get('name', 'Nome não disponível')}</h5>
                    <p><em>{profile.get('headline', '')}</em></p>
                    <p><strong>Empresa:</strong> {profile.get('company', 'Não disponível')}</p>
                    <p><strong>Localização:</strong> {profile.get('location', 'Não disponível')}</p>
                    <p><a href="{profile.get('profile_url', '#')}" target="_blank">Ver perfil completo</a></p>
                </div>
        """
    
    if not linkedin_profiles:
        report += "<p>Nenhum perfil do LinkedIn encontrado</p>"
        
    report += """
            </div>
        </div>
    """
    
    # Add company website data if available
    if company_data and not company_data.get("error"):
        report += f"""
        <div class="report-section">
            <h4>Dados da Empresa</h4>
            <p><strong>Nome:</strong> {company_data.get('name', 'Não disponível')}</p>
            <p><strong>Sobre:</strong> {company_data.get('about', 'Informação não disponível')}</p>
        """
        
        # Add services/products if available
        services = company_data.get('services', [])
        if services:
            report += "<div class='subsection'><h5>Serviços/Produtos</h5><ul>"
            for service in services:
                service_name = service.get('name', '')
                service_desc = service.get('description', '')
                report += f"<li><strong>{service_name}</strong>"
                if service_desc:
                    report += f": {service_desc}"
                report += "</li>"
            report += "</ul></div>"
        
        # Add team information if available
        team = company_data.get('team', [])
        if team:
            report += "<div class='subsection'><h5>Equipe</h5><ul>"
            for member in team:
                member_name = member.get('name', '')
                member_position = member.get('position', '')
                report += f"<li><strong>{member_name}</strong>"
                if member_position:
                    report += f" - {member_position}"
                report += "</li>"
            report += "</ul></div>"
        
        # Add contact information if available
        contact = company_data.get('contact', {})
        if contact:
            report += "<div class='subsection'><h5>Contato</h5>"
            if contact.get('email'):
                report += f"<p><strong>Email:</strong> {contact.get('email')}</p>"
            if contact.get('phone'):
                report += f"<p><strong>Telefone:</strong> {contact.get('phone')}</p>"
            if contact.get('address'):
                report += f"<p><strong>Endereço:</strong> {contact.get('address')}</p>"
            report += "</div>"
        
        # Add social links if available
        social = company_data.get('social_links', {})
        if social:
            report += "<div class='subsection'><h5>Redes Sociais</h5><ul>"
            for platform, url in social.items():
                report += f"<li><a href='{url}' target='_blank'>{platform.title()}</a></li>"
            report += "</ul></div>"
        
        # Add technologies if available
        technologies = company_data.get('technologies', [])
        if technologies:
            report += "<div class='subsection'><h5>Tecnologias Mencionadas</h5><ul>"
            for tech in technologies:
                report += f"<li>{tech}</li>"
            report += "</ul></div>"
            
        report += "</div>"
        
    report += """
        <div class="report-section">
            <h4>Dores e Oportunidades</h4>
            <div class="two-columns">
                <div class="column">
                    <h5>Dores Identificadas</h5>
                    <ul>
    """
    
    # Add pain points
    pain_points = sales_data.get('dores', [])
    if pain_points:
        for point in pain_points:
            report += f"<li>{point}</li>"
    else:
        report += "<li>Nenhuma dor específica identificada</li>"
    
    report += """
                    </ul>
                </div>
                <div class="column">
                    <h5>Oportunidades</h5>
                    <ul>
    """
    
    # Add opportunities
    opportunities = sales_data.get('oportunidades', [])
    if opportunities:
        for opp in opportunities:
            report += f"<li>{opp}</li>"
    else:
        report += "<li>Nenhuma oportunidade específica identificada</li>"
        
    report += """
                    </ul>
                </div>
            </div>
        </div>
        
        <div class="report-section">
            <h4>Recomendações de Venda</h4>
            <p>Com base na análise da transcrição e nos dados enriquecidos, recomendamos:</p>
            <ul>
                <li>Focar nos stakeholders-chave identificados no LinkedIn para personalizar a abordagem de vendas</li>
                <li>Destacar como seus produtos/serviços podem resolver as dores identificadas</li>
                <li>Utilizar os dados do website da empresa para entender melhor seu contexto e necessidades</li>
            </ul>
        </div>
    </div>
    
    <style>
        .sales-report {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
            color: #333;
            line-height: 1.6;
        }
        
        .report-section {
            margin-bottom: 1.5rem;
            padding-bottom: 1rem;
            border-bottom: 1px solid #eee;
        }
        
        .report-section h4 {
            color: #7158e2;
            margin-bottom: 0.75rem;
        }
        
        .subsection {
            margin-top: 1rem;
            margin-bottom: 1rem;
        }
        
        .subsection h5 {
            margin-bottom: 0.5rem;
            color: #666;
        }
        
        .two-columns {
            display: flex;
            gap: 2rem;
        }
        
        .column {
            flex: 1;
        }
        
        .profiles-list {
            display: flex;
            flex-wrap: wrap;
            gap: 1rem;
            margin-top: 1rem;
        }
        
        .profile-card {
            background: #f5f5f5;
            border-radius: 0.5rem;
            padding: 1rem;
            flex: 1 1 300px;
        }
        
        .profile-card h5 {
            margin-top: 0;
            margin-bottom: 0.5rem;
            color: #333;
        }
        
        .profile-card p {
            margin: 0.25rem 0;
        }
        
        .profile-card a {
            color: #7158e2;
            text-decoration: none;
        }
        
        .profile-card a:hover {
            text-decoration: underline;
        }
        
        .spin-analysis, .bant-analysis {
            background-color: #f5f5f5;
            padding: 1rem;
            border-radius: 0.5rem;
            margin-bottom: 1rem;
            border: 1px solid #e0e0e0;
        }
    </style>
    """
    
    return report

async def store_website_task(transcript_id: str, website_url: str) -> str:
    """
    Store a website scraping task in the database.
    
    Args:
        transcript_id: The transcript ID
        website_url: The website URL to scrape
        
    Returns:
        The ID of the created website enrichment record
    """
    try:
        client_to_use = supabase.admin_client if supabase.admin_client else supabase.client
        if not client_to_use:
            logger.warning("No Supabase client available, can't store website task")
            return ""
            
        # Insert the website enrichment record
        result = client_to_use.table('website_enrichments').insert({
            "transcript_id": transcript_id,
            "website_url": website_url,
            "status": "pending"
        }).execute()
        
        if result.data and len(result.data) > 0:
            return result.data[0]['id']
        return ""
    except Exception as e:
        logger.error(f"Error storing website task: {str(e)}")
        return ""
        
async def update_website_status(website_id: str, status: str, data: Dict[str, Any] = None) -> bool:
    """
    Update the status of a website scraping task.
    
    Args:
        website_id: The ID of the website enrichment record
        status: The new status (completed, failed)
        data: The scraped data (if successful)
        
    Returns:
        True if successful, False otherwise
    """
    if not website_id:
        return False
        
    try:
        client_to_use = supabase.admin_client if supabase.admin_client else supabase.client
        if not client_to_use:
            logger.warning("No Supabase client available, can't update website status")
            return False
            
        # Prepare the update data
        update_data = {
            "status": status,
            "scraped_at": datetime.now().isoformat()
        }
        
        if data:
            update_data["parsed_data"] = data
            
        # Update the record
        client_to_use.table('website_enrichments').update(update_data).eq('id', website_id).execute()
        return True
    except Exception as e:
        logger.error(f"Error updating website status: {str(e)}")
        return False
        
async def store_linkedin_task(transcript_id: str, linkedin_url: str) -> str:
    """
    Store a LinkedIn scraping task in the database.
    
    Args:
        transcript_id: The transcript ID
        linkedin_url: The LinkedIn profile URL to scrape
        
    Returns:
        The ID of the created LinkedIn enrichment record
    """
    try:
        client_to_use = supabase.admin_client if supabase.admin_client else supabase.client
        if not client_to_use:
            logger.warning("No Supabase client available, can't store LinkedIn task")
            return ""
            
        # Insert the LinkedIn enrichment record
        result = client_to_use.table('linkedin_enrichments').insert({
            "transcript_id": transcript_id,
            "linkedin_url": linkedin_url,
            "status": "pending"
        }).execute()
        
        if result.data and len(result.data) > 0:
            return result.data[0]['id']
        return ""
    except Exception as e:
        logger.error(f"Error storing LinkedIn task: {str(e)}")
        return ""
        
async def update_linkedin_status(linkedin_id: str, status: str, data: Dict[str, Any] = None) -> bool:
    """
    Update the status of a LinkedIn scraping task.
    
    Args:
        linkedin_id: The ID of the LinkedIn enrichment record
        status: The new status (completed, failed)
        data: The scraped profile data (if successful)
        
    Returns:
        True if successful, False otherwise
    """
    if not linkedin_id:
        return False
        
    try:
        client_to_use = supabase.admin_client if supabase.admin_client else supabase.client
        if not client_to_use:
            logger.warning("No Supabase client available, can't update LinkedIn status")
            return False
            
        # Prepare the update data
        update_data = {
            "status": status,
            "scraped_at": datetime.now().isoformat()
        }
        
        if data:
            update_data["profile_data"] = data
            
        # Update the record
        client_to_use.table('linkedin_enrichments').update(update_data).eq('id', linkedin_id).execute()
        return True
    except Exception as e:
        logger.error(f"Error updating LinkedIn status: {str(e)}")
        return False

async def scrape_website(url: str) -> Dict[str, Any]:
    """
    Scrape a website using Scrapy.
    
    Args:
        url: The website URL to scrape
        
    Returns:
        The scraped data
    """
    try:
        from run_website_scraper import run_website_scraper
        
        logger.info(f"Scraping website with Scrapy: {url}")
        # Call the website scraper implementation with save_to_file=False to avoid local storage
        company_data = run_website_scraper(url, output_file=None, save_to_file=False)
        
        # Log the status
        if company_data:
            logger.info(f"Successfully scraped website: {url}")
        else:
            logger.warning(f"Website scraping returned no data: {url}")
            
        return company_data
    except Exception as e:
        logger.error(f"Error in website scraping: {str(e)}")
        # Return empty data on error to avoid breaking the flow
        return {}
    
async def scrape_linkedin_profile(url: str) -> Dict[str, Any]:
    """
    Scrape a LinkedIn profile using BrightData.
    
    Args:
        url: The LinkedIn profile URL to scrape
        
    Returns:
        The scraped profile data
    """
    try:
        logger.info(f"Scraping LinkedIn profile with BrightData: {url}")
        
        # Use our new BrightData integration
        from brightdata_supabase_integration import LinkedInProfileEnricher
        
        # Create a temporary transcript ID for standalone use
        # In real usage, this would be provided by the caller
        temp_transcript_id = str(uuid.uuid4())
        
        # Initialize the enricher
        enricher = LinkedInProfileEnricher()
        
        # Enrich the profile
        result = await enricher.enrich_profile(url, temp_transcript_id)
        
        if result and result.get("status") == "ok" and result.get("profile_data"):
            logger.info(f"Successfully scraped LinkedIn profile: {url}")
            return result.get("profile_data")
        else:
            error_msg = result.get("message") if result else "Unknown error"
            logger.warning(f"Failed to scrape LinkedIn profile: {url}. Error: {error_msg}")
            raise ValueError(f"Failed to scrape LinkedIn profile: {error_msg}")
                
    except Exception as e:
        logger.error(f"Error in LinkedIn profile scraping: {str(e)}")
        
        # Instead of creating mock data, return a meaningful error object
        return {
            "error": True,
            "message": f"Failed to scrape LinkedIn profile: {str(e)}",
            "url": url,
            "timestamp": datetime.now().isoformat()
        }

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    
    print(f"\n🚀 Whisper Transcription App is running!")
    print(f"📊 Open http://localhost:{9000 if port == 8000 else port} in your browser\n")
    
    uvicorn.run("app:app", host=host, port=port, reload=True) 