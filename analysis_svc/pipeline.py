from typing import Dict, Any, Optional
import logging
import json
import os
from datetime import datetime

from analysis_svc.nodes import extract_call_analysis_node
from analysis_svc.nodes import extract_sales_data_node

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def run_analysis_pipeline(transcript_id: str) -> Dict[str, Any]:
    """
    Run the sales intelligence analysis pipeline on a transcript.
    
    Args:
        transcript_id: The ID of the transcript to analyze
        
    Returns:
        A dictionary containing the results of each step in the pipeline,
        including the final sales_data and call_analysis.
    """
    # Initialize state with transcript ID
    state = {"transcript_id": transcript_id}
    
    logger.info(f"Starting analysis pipeline for transcript {transcript_id}")
    
    # First check if there's an existing analysis in the database
    existing_analysis = await get_existing_analysis(transcript_id)
    if existing_analysis:
        logger.info(f"Found existing analysis for transcript {transcript_id}, using cached data")
        logger.info(f"Existing analysis content: sales_data present: {'sales_data' in existing_analysis}, call_analysis present: {'call_analysis' in existing_analysis}")
        return existing_analysis
    
    # Add detailed logging of the pipeline execution
    logger.info(f"Starting pipeline execution with the following nodes:")
    logger.info(f"  - load_transcript_node")
    logger.info(f"  - extract_sales_data_node")
    logger.info(f"  - extract_call_analysis_node")
    
    # Run the pipeline with timeouts and error handling for each step
    try:
        # Run in sequence with individual error handling for each node
        try:
            state = await load_transcript_node(state)
            logger.info(f"Transcript loaded successfully.")
        except Exception as e:
            logger.error(f"Error loading transcript: {e}")
            # Continue with empty transcript
            state["transcript_text"] = ""
            state["language"] = "pt"
        
        try:
            logger.info(f"Extracting sales data...")
            state = await extract_sales_data_node(state)
            logger.info(f"Sales data extracted successfully.")
        except Exception as e:
            logger.error(f"Error extracting sales data: {e}")
            # Continue with empty sales data
            state["sales_data"] = {}
        
        try:
            logger.info(f"Extracting call analysis...")
            state = await extract_call_analysis_node(state)
            logger.info(f"Call analysis extracted successfully.")
        except Exception as e:
            logger.error(f"Error extracting call analysis: {e}")
            # Continue with empty call analysis
            state["call_analysis"] = {}
    except Exception as e:
        logger.error(f"Unexpected error running pipeline: {e}")
        # Ensure we have minimal valid data to return
        if "sales_data" not in state:
            state["sales_data"] = {}
        if "call_analysis" not in state:
            state["call_analysis"] = {}
    
    # Process and return final result
    logger.info(f"Analysis pipeline for transcript {transcript_id} completed. Adding results to state.")
    state["result"] = {
        "transcript_id": transcript_id,
        "sales_data": state.get("sales_data", {}),
        "call_analysis": state.get("call_analysis", {})
    }
    
    # Add detailed logging of what's being returned
    logger.info(f"Returning sales_data keys: {state.get('sales_data', {}).keys() if isinstance(state.get('sales_data', {}), dict) else 'Not a dict'}")
    logger.info(f"Returning call_analysis keys: {state.get('call_analysis', {}).keys() if isinstance(state.get('call_analysis', {}), dict) else 'Not a dict'}")
    
    # Try to store the analysis results in the database, but don't block on errors
    try:
        stored = await store_analysis_result(transcript_id, state["result"])
        logger.info(f"Analysis results stored in database: {stored}")
    except Exception as e:
        logger.error(f"Error storing analysis results: {e}")
    
    # Return the combined results
    return state["result"]

async def get_existing_analysis(transcript_id: str) -> Optional[Dict[str, Any]]:
    """
    Check if there's an existing analysis for the transcript in the database.
    
    Args:
        transcript_id: The ID of the transcript
        
    Returns:
        The existing analysis if found, None otherwise
    """
    try:
        from db import supabase
        
        # Check if the analyses table exists in the database
        client_to_use = supabase.admin_client if supabase.admin_client else supabase.client
        if not client_to_use:
            logger.warning("No Supabase client available, can't check for existing analysis")
            return None
            
        try:
            # Query the analyses table
            result = client_to_use.table('analyses').select('*').eq('transcript_id', transcript_id).execute()
            
            if result.data and len(result.data) > 0:
                analysis_data = result.data[0]
                logger.info(f"Found existing analysis data: {list(analysis_data.keys())}")
                
                # Return the existing analysis with both sales_data and call_analysis if available
                response = {"transcript_id": transcript_id}
                
                if analysis_data.get('sales_data'):
                    response["sales_data"] = analysis_data['sales_data']
                    logger.info(f"Found existing sales_data of size: {len(str(analysis_data['sales_data']))}")
                    
                if analysis_data.get('call_analysis'):
                    response["call_analysis"] = analysis_data['call_analysis']
                    logger.info(f"Found existing call_analysis of size: {len(str(analysis_data['call_analysis']))}")
                    
                if "sales_data" in response or "call_analysis" in response:
                    logger.info(f"Found existing analysis in database for transcript {transcript_id}")
                    logger.info(f"Response keys: {list(response.keys())}")
                    return response
                
        except Exception as e:
            # If the query fails, likely because the table doesn't exist
            logger.warning(f"Error querying analyses table: {e}")
            
        return None
        
    except Exception as e:
        logger.error(f"Error checking for existing analysis: {e}")
        return None

async def store_analysis_result(transcript_id: str, state: Dict[str, Any]) -> bool:
    """
    Store the analysis result in the database for future use.
    
    Args:
        transcript_id: The ID of the transcript
        state: The analysis state containing sales_data and/or call_analysis
        
    Returns:
        True if successful, False otherwise
    """
    try:
        from db import supabase
        
        # Only proceed if we have analysis data to store
        if "sales_data" not in state and "call_analysis" not in state:
            logger.warning(f"No analysis data to store for transcript {transcript_id}")
            return False
            
        # Check if the analyses table exists in the database
        client_to_use = supabase.admin_client if supabase.admin_client else supabase.client
        if not client_to_use:
            logger.warning("No Supabase client available, can't store analysis")
            return False
            
        # Prepare the analysis data
        now = supabase.get_current_timestamp()
        
        analysis_data = {
            "transcript_id": transcript_id,
            "updated_at": now
        }
        
        # Add sales_data if available
        if "sales_data" in state:
            analysis_data["sales_data"] = state["sales_data"]
            logger.info(f"Including sales_data in the update, size: {len(str(state['sales_data']))}")
            
        # Add call_analysis if available
        if "call_analysis" in state:
            analysis_data["call_analysis"] = state["call_analysis"]
            logger.info(f"Including call_analysis in the update, size: {len(str(state['call_analysis']))}")
        
        # Try to insert or update
        try:
            # Check if there's an existing analysis
            result = client_to_use.table('analyses').select('id').eq('transcript_id', transcript_id).execute()
            
            if result.data and len(result.data) > 0:
                # Update existing record
                update_data = {
                    "updated_at": now
                }
                
                if "sales_data" in state:
                    update_data["sales_data"] = state["sales_data"]
                    
                if "call_analysis" in state:
                    update_data["call_analysis"] = state["call_analysis"]
                    
                client_to_use.table('analyses').update(update_data).eq('id', result.data[0]['id']).execute()
                logger.info(f"Updated existing analysis for transcript {transcript_id} with keys: {list(update_data.keys())}")
            else:
                # Insert new record
                client_to_use.table('analyses').insert(analysis_data).execute()
                logger.info(f"Inserted new analysis for transcript {transcript_id} with keys: {list(analysis_data.keys())}")
                
            return True
            
        except Exception as db_error:
            logger.error(f"Error storing analysis in database: {db_error}")
            return False
            
    except Exception as e:
        logger.error(f"Error storing analysis result: {e}")
        return False

async def run_enrichment_pipeline(
    transcript_id: str, 
    linkedin_profiles: list, 
    company_website: Optional[str] = None
) -> Dict[str, Any]:
    """
    Run the enrichment pipeline, which combines LinkedIn and website data.
    
    Args:
        transcript_id: The ID of the transcript
        linkedin_profiles: List of LinkedIn profile URLs
        company_website: Optional website URL
        
    Returns:
        Enrichment results
    """
    # This is a placeholder for now - the actual implementation is in app.py
    # In a real production app, this would be refactored to move that code here
    logger.info(f"Enrichment pipeline requested for transcript {transcript_id}")
    
    # Ensure we have run the analysis pipeline first
    analysis_result = await run_analysis_pipeline(transcript_id)
    
    # Return placeholder result 
    return {
        "transcript_id": transcript_id,
        "analysis_complete": "sales_data" in analysis_result,
        "enrichment_requested": {
            "linkedin_profiles": linkedin_profiles,
            "company_website": company_website
        }
    } 

async def load_transcript_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Load transcript text from the database.
    
    Args:
        state: The current state with transcript_id
        
    Returns:
        Updated state with transcript_text added
    """
    transcript_id = state.get("transcript_id", "")
    
    try:
        from shared.db import get_transcript_by_id
        
        # Get transcript from database
        transcript_text, language = get_transcript_by_id(transcript_id)
        
        if not transcript_text:
            logger.warning(f"No transcript text found for ID {transcript_id}")
            state["transcript_text"] = ""
            return state
            
        logger.info(f"Loaded transcript {transcript_id} with {len(transcript_text)} characters")
        state["transcript_text"] = transcript_text
        state["language"] = language
        return state
        
    except Exception as e:
        logger.error(f"Error loading transcript: {e}")
        state["transcript_text"] = ""
        return state 