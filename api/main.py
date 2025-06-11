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
import asyncio
from dotenv import load_dotenv

from fastapi import FastAPI, UploadFile, File, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import our lightweight services
from api.services.transcription_service import TranscriptionService
from api.services.enrichment_service import EnrichmentService
from api.services.analysis_service import AnalysisService
from api.config.vercel_config import get_config

# Initialize services
config = get_config()
transcription_service = TranscriptionService(config)
enrichment_service = EnrichmentService(config)
analysis_service = AnalysisService(config)

# Initialize app
app = FastAPI(title="Sales AI - Vercel Edition")

# Set up static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Models (keeping the same interface)
class TranscriptionResponse(BaseModel):
    transcript_id: str
    filename: str
    transcript: str
    duration_seconds: int
    language: str
    file_url: Optional[str] = None

class ErrorResponse(BaseModel):
    detail: str

class SalesAnalysisResponse(BaseModel):
    transcript_id: str
    sales_data: Dict[str, Any]
    call_analysis: Dict[str, Any]

class StakeholderData(BaseModel):
    Company: str
    Stakeholders: List[str]
    BANT_Analysis: Optional[Dict[str, str]] = None
    Personalization_Context: Optional[str] = None
    Research_Topics: Optional[List[str]] = None
    Pain_Points: Optional[List[str]] = None
    Opportunities: Optional[List[str]] = None

class EnrichmentRequest(BaseModel):
    transcript_id: str
    company_website: Optional[str] = None
    linkedin_profiles: List[str] = []

class EnrichmentResponse(BaseModel):
    transcript_id: str
    report: str
    scraping_status: Dict[str, bool]

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
    """Transcribe an audio/video file using OpenAI Whisper API"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")
    
    try:
        # Generate a unique ID for this transcription
        transcript_id = str(uuid.uuid4())
        
        # Read file content
        content = await file.read()
        
        # Use OpenAI Whisper API for transcription (no local processing)
        result = await transcription_service.transcribe_audio(
            content, 
            file.filename, 
            transcript_id
        )
        
        if not result:
            raise HTTPException(status_code=500, detail="Transcription failed")
        
        logger.info(f"Successfully transcribed file '{file.filename}' with ID '{transcript_id}'")
        
        return TranscriptionResponse(**result)
        
    except Exception as e:
        logger.error(f"Error transcribing file '{file.filename}': {str(e)}")
        raise HTTPException(status_code=500, detail=f"Transcription error: {str(e)}")

@app.get("/transcripts/")
async def list_transcripts(request: Request):
    """List all transcripts with pagination"""
    try:
        transcripts = await transcription_service.get_transcripts()
        return templates.TemplateResponse(
            "transcripts_list.html",
            {"request": request, "transcripts": transcripts}
        )
    except Exception as e:
        logger.error(f"Error listing transcripts: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve transcripts")

@app.get("/transcripts/{transcript_id}", response_model=dict)
async def get_transcript_api(transcript_id: str):
    """Get a specific transcript by ID"""
    try:
        transcript = await transcription_service.get_transcript(transcript_id)
        if not transcript:
            raise HTTPException(status_code=404, detail="Transcript not found")
        return transcript
    except Exception as e:
        logger.error(f"Error retrieving transcript {transcript_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve transcript")

@app.get("/transcript/{transcript_id}", response_class=HTMLResponse)
async def view_transcript(request: Request, transcript_id: str):
    """View transcript details page"""
    try:
        transcript = await transcription_service.get_transcript(transcript_id)
        if not transcript:
            raise HTTPException(status_code=404, detail="Transcript not found")
        
        return templates.TemplateResponse(
            "transcript.html",
            {"request": request, "transcript": transcript, "transcript_id": transcript_id}
        )
    except Exception as e:
        logger.error(f"Error viewing transcript {transcript_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to load transcript")

@app.post("/transcripts/{transcript_id}/analyze", response_model=SalesAnalysisResponse)
async def analyze_transcript(transcript_id: str):
    """Analyze transcript for sales insights using lightweight AI services"""
    try:
        # Get transcript
        transcript = await transcription_service.get_transcript(transcript_id)
        if not transcript:
            raise HTTPException(status_code=404, detail="Transcript not found")
        
        # Perform analysis using external AI services (OpenAI API)
        analysis_result = await analysis_service.analyze_sales_call(
            transcript['transcript'], 
            transcript_id
        )
        
        if not analysis_result:
            raise HTTPException(status_code=500, detail="Analysis failed")
        
        logger.info(f"Successfully analyzed transcript '{transcript_id}'")
        
        return SalesAnalysisResponse(**analysis_result)
        
    except Exception as e:
        logger.error(f"Error analyzing transcript {transcript_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Analysis error: {str(e)}")

@app.post("/linkedin/scrape/")
async def scrape_linkedin(data: StakeholderData):
    """Scrape LinkedIn using external API service"""
    try:
        # Use external scraping service instead of local scrapy
        result = await enrichment_service.scrape_linkedin_profiles(data.dict())
        
        return {
            "status": "success", 
            "job_id": str(uuid.uuid4()),
            "message": "LinkedIn scraping initiated"
        }
        
    except Exception as e:
        logger.error(f"Error scraping LinkedIn: {str(e)}")
        raise HTTPException(status_code=500, detail=f"LinkedIn scraping error: {str(e)}")

@app.post("/enrich-data/", response_model=EnrichmentResponse)
async def enrich_data(data: EnrichmentRequest):
    """Enrich transcript data with company and LinkedIn information"""
    try:
        # Get transcript
        transcript = await transcription_service.get_transcript(data.transcript_id)
        if not transcript:
            raise HTTPException(status_code=404, detail="Transcript not found")
        
        # Perform enrichment using external services
        enrichment_result = await enrichment_service.enrich_transcript_data(
            transcript['transcript'],
            data.company_website,
            data.linkedin_profiles,
            data.transcript_id
        )
        
        if not enrichment_result:
            raise HTTPException(status_code=500, detail="Enrichment failed")
        
        logger.info(f"Successfully enriched transcript '{data.transcript_id}'")
        
        return EnrichmentResponse(**enrichment_result)
        
    except Exception as e:
        logger.error(f"Error enriching data for transcript {data.transcript_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Enrichment error: {str(e)}")

@app.get("/health")
async def health_check():
    """Health check endpoint for Vercel"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "transcription": await transcription_service.health_check(),
            "enrichment": await enrichment_service.health_check(),
            "analysis": await analysis_service.health_check()
        }
    }

# Error handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global error: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={"message": "An internal server error occurred"}
    )

# Main handler for Vercel
def handler(request, context):
    """Main handler for Vercel serverless function"""
    return app(request, context) 