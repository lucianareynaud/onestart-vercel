from typing import Tuple, Optional

from db import supabase

def get_transcript_by_id(transcript_id: str) -> tuple:
    """
    Get transcript text and language by transcript ID
    
    Args:
        transcript_id: The ID of the transcript to retrieve
        
    Returns:
        Tuple of (transcript_text, language)
    """
    try:
        # Get the transcript from Supabase
        transcript = supabase.get_transcript(transcript_id)
        if not transcript:
            return "", "pt"
            
        transcript_text = transcript.get("transcript", "")
        language = transcript.get("language", "pt")
        
        return transcript_text, language
    except Exception as e:
        print(f"Error getting transcript by ID: {e}")
        return "", "pt" 