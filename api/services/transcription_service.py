import httpx
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)

class TranscriptionService:
    """Lightweight transcription service using OpenAI Whisper API"""
    
    def __init__(self, config):
        self.config = config
        self.supabase_client = self._init_supabase()
    
    def _init_supabase(self):
        """Initialize Supabase client for database operations"""
        try:
            from supabase import create_client
            return create_client(self.config.supabase_url, self.config.supabase_anon_key)
        except Exception as e:
            logger.error(f"Failed to initialize Supabase: {e}")
            return None
    
    async def transcribe_audio(self, audio_content: bytes, filename: str, transcript_id: str) -> Optional[Dict[str, Any]]:
        """Transcribe audio using OpenAI Whisper API"""
        try:
            # Check file size (Vercel limit: 25MB)
            if len(audio_content) > self.config.max_file_size:
                raise ValueError(f"File too large: {len(audio_content)} bytes. Max: {self.config.max_file_size}")
            
            # Call OpenAI Whisper API
            async with httpx.AsyncClient(timeout=self.config.request_timeout) as client:
                files = {
                    'file': (filename, audio_content, 'audio/mpeg'),
                    'model': (None, 'whisper-1'),
                    'language': (None, 'en'),
                    'response_format': (None, 'json')
                }
                
                response = await client.post(
                    f"{self.config.transcription_service_url}/audio/transcriptions",
                    headers={"Authorization": f"Bearer {self.config.openai_api_key}"},
                    files=files
                )
                
                if response.status_code != 200:
                    logger.error(f"OpenAI API error: {response.status_code} - {response.text}")
                    return None
                
                result = response.json()
                transcript_text = result.get('text', '')
                
                # Calculate approximate duration (OpenAI doesn't return duration)
                # Rough estimate: 150 words per minute
                word_count = len(transcript_text.split())
                duration_seconds = max(1, int(word_count / 2.5))  # 150 words/min = 2.5 words/sec
                
                # Store in Supabase
                transcript_data = {
                    'id': transcript_id,
                    'transcript': transcript_text,
                    'storage_path': f"transcripts/{transcript_id}.json",
                    'duration_seconds': duration_seconds,
                    'language': 'en',
                    'created_at': datetime.utcnow().isoformat()
                }
                
                await self._store_transcript(transcript_data)
                
                return {
                    'transcript_id': transcript_id,
                    'filename': filename,
                    'transcript': transcript_text,
                    'duration_seconds': duration_seconds,
                    'language': 'en'
                }
                
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            return None
    
    async def _store_transcript(self, transcript_data: Dict[str, Any]) -> bool:
        """Store transcript in Supabase"""
        try:
            if not self.supabase_client:
                logger.warning("Supabase client not available, skipping storage")
                return False
            
            result = self.supabase_client.table('transcripts').insert(transcript_data).execute()
            return len(result.data) > 0
            
        except Exception as e:
            logger.error(f"Error storing transcript: {e}")
            return False
    
    async def get_transcript(self, transcript_id: str) -> Optional[Dict[str, Any]]:
        """Get transcript by ID from Supabase"""
        try:
            if not self.supabase_client:
                logger.warning("Supabase client not available")
                return None
            
            result = self.supabase_client.table('transcripts').select('*').eq('id', transcript_id).execute()
            
            if result.data:
                return result.data[0]
            return None
            
        except Exception as e:
            logger.error(f"Error retrieving transcript {transcript_id}: {e}")
            return None
    
    async def get_transcripts(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """Get list of transcripts with pagination"""
        try:
            if not self.supabase_client:
                logger.warning("Supabase client not available")
                return []
            
            result = self.supabase_client.table('transcripts')\
                .select('id,transcript,storage_path,duration_seconds,language,created_at')\
                .order('created_at', desc=True)\
                .range(offset, offset + limit - 1)\
                .execute()
            
            return result.data or []
            
        except Exception as e:
            logger.error(f"Error retrieving transcripts: {e}")
            return []
    
    async def health_check(self) -> bool:
        """Check if transcription service is healthy"""
        try:
            # Test OpenAI API connectivity
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    f"{self.config.transcription_service_url}/models",
                    headers={"Authorization": f"Bearer {self.config.openai_api_key}"}
                )
                return response.status_code == 200
        except Exception:
            return False 