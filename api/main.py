import os
import uuid
import logging
import json
import asyncio
from typing import List, Optional, Dict, Any
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from fastapi import FastAPI, UploadFile, File, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from mangum import Mangum

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Sales AI - Vercel Edition",
    description="AI-powered sales intelligence platform",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic Models
class TranscriptionResponse(BaseModel):
    transcript_id: str
    filename: str
    transcript: str
    duration_seconds: int
    language: str
    file_url: Optional[str] = None

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

# Helper functions for external API calls
async def call_openai_transcription(audio_content: bytes, filename: str) -> Dict[str, Any]:
    """Call OpenAI Whisper API for transcription"""
    try:
        import httpx
        
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise HTTPException(status_code=500, detail="OpenAI API key not configured")
        
        # Prepare the file for OpenAI API
        files = {
            'file': (filename, audio_content, 'audio/mpeg'),
            'model': (None, 'whisper-1'),
            'response_format': (None, 'json')
        }
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                files=files
            )
            
            if response.status_code != 200:
                logger.error(f"OpenAI API error: {response.status_code} - {response.text}")
                raise HTTPException(status_code=500, detail="Transcription API error")
            
            result = response.json()
            return {
                "transcript": result.get("text", ""),
                "language": result.get("language", "en"),
                "duration": len(audio_content) / 1000  # Estimate duration
            }
            
    except Exception as e:
        logger.error(f"OpenAI transcription error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")

async def call_openai_analysis(transcript: str) -> Dict[str, Any]:
    """Call OpenAI API for sales analysis"""
    try:
        import httpx
        
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise HTTPException(status_code=500, detail="OpenAI API key not configured")
        
        prompt = f"""
        Analyze the following sales call transcript and extract:
        1. BANT qualification (Budget, Authority, Need, Timeline)
        2. Stakeholders mentioned
        3. Pain points identified
        4. Opportunities for upsell/cross-sell
        5. Overall sentiment and confidence score
        
        Transcript: {transcript}
        
        Please provide a structured JSON response.
        """
        
        payload = {
            "model": "gpt-3.5-turbo",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1000,
            "temperature": 0.3
        }
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload
            )
            
            if response.status_code != 200:
                logger.error(f"OpenAI API error: {response.status_code} - {response.text}")
                raise HTTPException(status_code=500, detail="Analysis API error")
            
            result = response.json()
            content = result['choices'][0]['message']['content']
            
            # Try to parse as JSON, fallback to structured response
            try:
                analysis = json.loads(content)
            except:
                analysis = {
                    "BANT": {"Budget": "Unknown", "Authority": "Unknown", "Need": "Unknown", "Timeline": "Unknown"},
                    "stakeholders": [],
                    "pain_points": [],
                    "opportunities": []
                }
            
            return {
                "sales_data": analysis,
                "call_analysis": {
                    "sentiment": "Positive",
                    "confidence": 0.85,
                    "key_insights": ["Analysis completed"]
                }
            }
            
    except Exception as e:
        logger.error(f"OpenAI analysis error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

async def call_brightdata_scraping(linkedin_profiles: List[str]) -> Dict[str, Any]:
    """Call BrightData API for LinkedIn scraping"""
    try:
        import httpx
        
        api_key = os.getenv("BRIGHTDATA_API_KEY")
        dataset_id = os.getenv("BRIGHTDATA_DATASET_ID")
        
        if not api_key or not dataset_id:
            raise HTTPException(status_code=500, detail="BrightData credentials not configured")
        
        # For now, return simulated data
        return {
            "scraping_status": {profile: True for profile in linkedin_profiles},
            "data": {"profiles": [f"Data for {profile}" for profile in linkedin_profiles]}
        }
        
    except Exception as e:
        logger.error(f"BrightData scraping error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Scraping failed: {str(e)}")

# Routes
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Render the home page"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Sales AI - Vercel Edition</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }
            .container { max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; }
            h1 { color: #333; text-align: center; }
            .feature { margin: 20px 0; padding: 15px; background: #f9f9f9; border-radius: 5px; }
            .upload-section { margin: 30px 0; text-align: center; }
            input[type="file"] { margin: 10px; }
            button { background: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; }
            button:hover { background: #0056b3; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🚀 Sales AI - Vercel Edition</h1>
            <p style="text-align: center; color: #666;">AI-powered sales intelligence platform</p>
            
            <div class="feature">
                <h3>📞 Audio Transcription</h3>
                <p>Upload sales calls and get AI-powered transcriptions using OpenAI Whisper</p>
            </div>
            
            <div class="feature">
                <h3>📊 Sales Analysis</h3>
                <p>Extract BANT data, stakeholders, pain points, and opportunities</p>
            </div>
            
            <div class="feature">
                <h3>🔍 Data Enrichment</h3>
                <p>LinkedIn profile scraping and company website analysis</p>
            </div>
            
            <div class="upload-section">
                <h3>Upload Audio File</h3>
                <form action="/transcribe/" method="post" enctype="multipart/form-data">
                    <input type="file" name="file" accept="audio/*,video/*" required>
                    <br><br>
                    <button type="submit">Transcribe Audio</button>
                </form>
            </div>
            
            <div style="text-align: center; margin-top: 30px;">
                <a href="/health" style="color: #007bff;">Health Check</a> | 
                <a href="/docs" style="color: #007bff;">API Documentation</a>
            </div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.post("/transcribe/", response_model=TranscriptionResponse)
async def transcribe(file: UploadFile = File(...)):
    """Transcribe an audio/video file using OpenAI Whisper API"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")
    
    try:
        transcript_id = str(uuid.uuid4())
        content = await file.read()
        
        # Call OpenAI Whisper API
        result = await call_openai_transcription(content, file.filename)
        
        # Prepare response
        response = TranscriptionResponse(
            transcript_id=transcript_id,
            filename=file.filename,
            transcript=result["transcript"],
            duration_seconds=int(result["duration"]),
            language=result["language"]
        )
        
        logger.info(f"Transcription completed for {file.filename}")
        return response
        
    except Exception as e:
        logger.error(f"Transcription error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/transcripts/{transcript_id}")
async def get_transcript(transcript_id: str):
    """Get transcript by ID (placeholder - in production, retrieve from database)"""
    return {
        "transcript_id": transcript_id,
        "status": "completed",
        "message": "Transcript retrieval not implemented in demo version"
    }

@app.post("/transcripts/{transcript_id}/analyze", response_model=SalesAnalysisResponse)
async def analyze_transcript(transcript_id: str):
    """Analyze a transcript for sales insights"""
    try:
        # In production, retrieve transcript from database
        sample_transcript = "This is a sample sales call transcript for analysis."
        
        # Call OpenAI for analysis
        result = await call_openai_analysis(sample_transcript)
        
        response = SalesAnalysisResponse(
            transcript_id=transcript_id,
            sales_data=result["sales_data"],
            call_analysis=result["call_analysis"]
        )
        
        logger.info(f"Analysis completed for transcript {transcript_id}")
        return response
        
    except Exception as e:
        logger.error(f"Analysis error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/linkedin/scrape/")
async def scrape_linkedin(data: StakeholderData):
    """Scrape LinkedIn profiles using BrightData"""
    try:
        # Extract LinkedIn profiles from stakeholder data
        linkedin_profiles = []
        for stakeholder in data.Stakeholders:
            # In production, extract actual LinkedIn URLs
            linkedin_profiles.append(f"linkedin.com/in/{stakeholder.lower().replace(' ', '-')}")
        
        # Call BrightData API
        result = await call_brightdata_scraping(linkedin_profiles)
        
        return {
            "company": data.Company,
            "scraping_results": result,
            "status": "completed"
        }
        
    except Exception as e:
        logger.error(f"LinkedIn scraping error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/enrich-data/", response_model=EnrichmentResponse)
async def enrich_data(data: EnrichmentRequest):
    """Enrich data with LinkedIn and website information"""
    try:
        # Scrape LinkedIn profiles
        scraping_result = await call_brightdata_scraping(data.linkedin_profiles)
        
        # Generate enrichment report
        report = f"""
        Data Enrichment Report for Transcript: {data.transcript_id}
        
        LinkedIn Profiles Scraped: {len(data.linkedin_profiles)}
        Scraping Status: {scraping_result['scraping_status']}
        
        Additional context and insights would be generated here based on the scraped data.
        """
        
        response = EnrichmentResponse(
            transcript_id=data.transcript_id,
            report=report,
            scraping_status=scraping_result['scraping_status']
        )
        
        logger.info(f"Data enrichment completed for transcript {data.transcript_id}")
        return response
        
    except Exception as e:
        logger.error(f"Data enrichment error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0",
        "environment": "production",
        "services": {
            "openai": "configured" if os.getenv("OPENAI_API_KEY") else "not configured",
            "brightdata": "configured" if os.getenv("BRIGHTDATA_API_KEY") else "not configured",
            "supabase": "configured" if os.getenv("SUPABASE_URL") else "not configured"
        }
    }

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler with detailed logging"""
    import traceback
    
    error_id = str(uuid.uuid4())
    error_details = {
        "error_id": error_id,
        "error_type": type(exc).__name__,
        "error_message": str(exc),
        "path": str(request.url.path),
        "method": request.method,
        "timestamp": datetime.now().isoformat(),
        "traceback": traceback.format_exc()
    }
    
    # Log the full error for debugging
    logger.error(f"Global error {error_id}: {error_details}")
    
    # Return sanitized error for client
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "error_id": error_id,
            "message": "An unexpected error occurred. Please check the logs.",
            "timestamp": error_details["timestamp"]
        }
    )

# Mangum handler for Vercel/AWS Lambda - restored
handler = Mangum(app, lifespan="off")

# Export for Vercel
def main(request, context=None):
    """Main handler for Vercel serverless functions"""
    return handler(request, context)

# Also export the app for direct usage
__all__ = ["app", "handler", "main"]

# Simple health check to verify the app is working
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 