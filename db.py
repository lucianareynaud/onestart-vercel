from typing import Dict, Any, Optional, List
from supabase import create_client
import os
import uuid
import traceback
import requests
from urllib.parse import quote
from config import SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_STORAGE_BUCKET
import json
import time
import tempfile
import logging
import math
from pathlib import Path
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Import supabase (with optional mock for testing)
try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    logger.warning("Supabase SDK not installed. Using mock implementation.")
    SUPABASE_AVAILABLE = False
    
# Get configuration from environment variables
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_ANON_KEY = os.getenv('SUPABASE_ANON_KEY')
SUPABASE_SERVICE_ROLE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
SUPABASE_STORAGE_BUCKET = os.getenv('SUPABASE_STORAGE_BUCKET', 'transcripts')

# Check if we're in demo mode
is_demo_mode = False

# Maximum file size for Supabase uploads
MAX_SUPABASE_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 MB for safety (Supabase limit is 50MB)

class SupabaseManager:
    """Manages Supabase database operations and storage"""
    
    def __init__(self):
        self.client = None
        self.admin_client = None
        self.is_demo_mode = is_demo_mode
        
        # Skip initialization if in demo mode
        if self.is_demo_mode:
            logger.warning("Running in demo mode - no actual connection to Supabase")
            return
            
        # Make sure we have required environment variables
        if not SUPABASE_URL or not SUPABASE_ANON_KEY:
            logger.warning("Missing Supabase credentials. Set SUPABASE_URL and SUPABASE_ANON_KEY in .env file")
            self.is_demo_mode = True
            return
            
        try:
            # Initialize anon client for public operations
            if SUPABASE_AVAILABLE:
                self.client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
                logger.info(f"Supabase anon client connection established successfully. URL: {SUPABASE_URL[:20]}...")
                
                # Initialize admin client with service role key if available
                if SUPABASE_SERVICE_ROLE_KEY:
                    logger.info("Initializing admin client with service role key...")
                    self.admin_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
                    logger.info("Supabase admin client connection established successfully.")
            else:
                logger.warning("Supabase SDK not available. Using mock implementation.")
        except Exception as e:
            logger.exception(f"Failed to initialize Supabase connection: {str(e)}")
            logger.warning("Using demo mode as fallback due to connection failure")
            self.is_demo_mode = True
    
    def store_transcript(self, 
                         transcript_text: str, 
                         storage_path: str, 
                         duration_seconds: int,
                         language: str = 'pt',
                         transcript_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Store transcript metadata in the database
        
        Args:
            transcript_text: The actual transcript text from Whisper
            storage_path: Path where the file is stored in Supabase Storage
            duration_seconds: Duration of the audio/video in seconds
            language: Language code of the transcript
            transcript_id: Optional ID to use for the transcript (if not provided, one will be generated)
            
        Returns:
            The created transcript record
        """
        if self.is_demo_mode:
            # Return a mock record with a demo UUID in demo mode
            return {
                "id": transcript_id or str(uuid.uuid4()),
                "transcript": transcript_text,
                "storage_path": storage_path,
                "duration_seconds": duration_seconds,
                "language": language,
                "created_at": "2023-01-01T00:00:00.000Z"
            }
            
        data = {
            "transcript": transcript_text,
            "storage_path": storage_path,
            "duration_seconds": duration_seconds,
            "language": language
        }
        
        # If transcript_id is provided, use it
        if transcript_id:
            data["id"] = transcript_id
        
        # Use admin client if available to bypass RLS
        client_to_use = self.admin_client if self.admin_client else self.client
        
        try:
            logger.info(f"Inserting transcript record using {'admin' if self.admin_client else 'anon'} client...")
            
            # Insert record into the transcripts table
            response = client_to_use.table('transcripts').insert(data).execute()
            
            # Verify the response
            if not response.data or len(response.data) == 0:
                logger.warning(f"Insert operation executed but no data returned")
                raise ValueError("Failed to insert transcript record")
                
            logger.info(f"Successfully inserted transcript record with ID: {response.data[0]['id']}")
            
            # Verify the record was inserted correctly
            record_id = response.data[0]['id']
            verification = client_to_use.table('transcripts').select('*').eq('id', record_id).execute()
            
            if not verification.data or len(verification.data) == 0:
                logger.warning(f"Warning: Could not verify inserted record with ID {record_id}")
            
            return response.data[0]
        except Exception as e:
            logger.exception(f"Error inserting transcript record: {str(e)}")
            traceback.print_exc()
            
            # Try a simpler insert approach as fallback
            try:
                logger.info("Attempting fallback direct insert...")
                result = client_to_use.from_('transcripts').insert(data).execute()
                if result.data and len(result.data) > 0:
                    logger.info(f"Fallback insert successful, ID: {result.data[0]['id']}")
                    return result.data[0]
                else:
                    logger.warning(f"Fallback insert failed")
            except Exception as fallback_e:
                logger.exception(f"Fallback insert error: {str(fallback_e)}")
            
            # Re-raise the original exception if fallback fails
            raise
    
    def upload_file(self, file_path: str, storage_path: str, bucket: str = None) -> str:
        """
        Upload a file to Supabase Storage
        
        Args:
            file_path: Local path to the file
            storage_path: Target path in storage (including filename)
            bucket: Storage bucket name (default: from SUPABASE_STORAGE_BUCKET)
            
        Returns:
            Public URL of the uploaded file or local path in demo mode
        """
        # Use the configured bucket name if none is provided
        if bucket is None:
            bucket = SUPABASE_STORAGE_BUCKET
            
        if self.is_demo_mode:
            # In demo mode, just return the local path
            logger.info("Running in demo mode, skipping actual upload to Supabase")
            return file_path
            
        # Make sure the file exists and can be read
        if not os.path.exists(file_path):
            logger.error(f"❌ Error: File does not exist: {file_path}")
            return file_path
            
        # Check file size
        file_size = os.path.getsize(file_path)
        file_size_mb = file_size / (1024 * 1024)
        
        if file_size == 0:
            logger.error(f"❌ Error: File is empty: {file_path}")
            return file_path
            
        # Use admin client if available to bypass RLS
        client_to_use = self.admin_client if self.admin_client else self.client
        logger.info(f"Uploading file to '{bucket}' bucket using {'admin' if self.admin_client else 'anon'} client...")
        logger.info(f"File path: {file_path}, Storage path: {storage_path}")
        
        try:
            # Check file size - if greater than limit, use chunked upload
            if file_size > MAX_SUPABASE_UPLOAD_SIZE:
                logger.info(f"File size ({file_size_mb:.2f}MB) exceeds direct upload limit, using chunked upload")
                return self._chunked_upload(file_path, storage_path, bucket)
            
            # Regular non-chunked upload for smaller files
            with open(file_path, "rb") as file_content:
                # Try to upload, with retries
                max_retries = 3
                retry_count = 0
                upload_success = False
                
                while retry_count < max_retries and not upload_success:
                    try:
                        logger.info(f"Upload attempt {retry_count + 1}/{max_retries}...")
                        
                        # Upload with automatic file_options and content-type detection
                        response = client_to_use.storage.from_(bucket).upload(
                            path=storage_path,
                            file=file_content,
                            file_options={"upsert": "true"}
                        )
                        logger.info(f"Upload response: {response}")
                        upload_success = True
                    except Exception as upload_error:
                        logger.warning(f"Upload attempt {retry_count + 1} failed: {str(upload_error)}")
                        retry_count += 1
                        if retry_count < max_retries:
                            time.sleep(1)  # Wait before retrying
                            # Reset file pointer to beginning
                            file_content.seek(0)
            
            if upload_success:
                # Get the public URL for the file
                url = client_to_use.storage.from_(bucket).get_public_url(storage_path)
                logger.info(f"File uploaded successfully. Public URL: {url}")
                
                # List files in bucket to verify upload
                try:
                    files = client_to_use.storage.from_(bucket).list()
                    file_names = [f['name'] for f in files]
                    logger.info(f"Files in bucket: {file_names}")
                except Exception as e:
                    logger.warning(f"Warning: Could not list bucket contents: {str(e)}")
                    
                return url
            else:
                logger.error("❌ All upload attempts failed. Trying fallback method...")
            
            # Fallback upload method using requests
            try:
                supabase_url = SUPABASE_URL
                supabase_key = SUPABASE_SERVICE_ROLE_KEY or SUPABASE_ANON_KEY
                
                # URL encode the path
                encoded_path = quote(storage_path)
                upload_url = f"{supabase_url}/storage/v1/object/{bucket}/{encoded_path}"
                logger.info(f"Fallback upload URL: {upload_url}")
                
                # Prepare headers with auth
                headers = {
                    "Authorization": f"Bearer {supabase_key}",
                    "apikey": supabase_key,
                    "x-upsert": "true"  # Overwrite if exists
                }
                
                # Try multipart/form-data upload
                logger.info("Attempting multipart/form-data upload...")
                with open(file_path, 'rb') as f:
                    files = {'file': (os.path.basename(storage_path), f, 'application/octet-stream')}
                    upload_response = requests.post(
                        upload_url,
                        headers=headers,
                        files=files
                    )
                
                if upload_response.status_code >= 200 and upload_response.status_code < 300:
                    logger.info(f"✅ Fallback upload successful: {upload_response.status_code}")
                    url = f"{supabase_url}/storage/v1/object/public/{bucket}/{encoded_path}"
                    logger.info(f"File public URL: {url}")
                    return url
                else:
                    logger.error(f"❌ Fallback upload failed: {upload_response.status_code}")
                    
                    # Try binary upload as last resort
                    logger.info("Attempting direct binary upload...")
                    with open(file_path, 'rb') as f:
                        binary_response = requests.post(
                            upload_url,
                            headers={**headers, 'Content-Type': 'application/octet-stream'},
                            data=f
                        )
                    
                    if binary_response.status_code >= 200 and binary_response.status_code < 300:
                        logger.info(f"✅ Binary upload successful: {binary_response.status_code}")
                        url = f"{supabase_url}/storage/v1/object/public/{bucket}/{encoded_path}"
                        logger.info(f"File public URL: {url}")
                        return url
                    else:
                        logger.error(f"❌ Binary upload failed: {binary_response.status_code}")
                        return file_path  # Return local path as last resort
                    
            except Exception as fallback_error:
                logger.error(f"❌ All upload methods failed. Error: {str(fallback_error)}")
                return file_path  # Return local path as last resort
        
        except Exception as e:
            logger.exception(f"❌ Upload failed: {str(e)}")
            return file_path  # Return local path as last resort
    
    def get_transcript(self, transcript_id: str) -> Optional[Dict[str, Any]]:
        """Get transcript by ID"""
        if self.is_demo_mode:
            # Return a mock transcript in demo mode
            return {
                "id": transcript_id,
                "transcript": "This is a demo transcript text.",
                "storage_path": "uploads/demo.mp3",
                "duration_seconds": 120,
                "language": "pt",
                "created_at": "2023-01-01T00:00:00.000Z"
            }
            
        response = self.client.table('transcripts').select('*').eq('id', transcript_id).execute()
        
        if not response.data or len(response.data) == 0:
            return None
            
        return response.data[0]
    
    def get_all_transcripts(self) -> list:
        """Get all transcripts from the database"""
        if self.is_demo_mode:
            return [
                {
                    "id": "123e4567-e89b-12d3-a456-426614174000",
                    "transcript": "This is a sample transcript in demo mode.",
                    "storage_path": "demo/sample.mp3",
                    "duration_seconds": 120,
                    "language": "pt",
                    "created_at": "2023-01-01T00:00:00.000Z"
                }
            ]
            
        try:
            # Use admin client if available to bypass RLS
            client_to_use = self.admin_client if self.admin_client else self.client
            
            # Get all transcripts, ordered by creation date
            response = client_to_use.table('transcripts').select('*').order('created_at', desc=True).execute()
            
            if response.data:
                return response.data
            return []
        except Exception as e:
            logger.exception(f"Error getting all transcripts: {str(e)}")
            return []
    
    # Methods for website and LinkedIn enrichment
    def insert_website_enrichment(self, website_enrichment) -> Optional[Dict[str, Any]]:
        """
        Insert a new website enrichment record.
        
        Args:
            website_enrichment: WebsiteEnrichment object with transcript_id and website_url
            
        Returns:
            The created website enrichment record or None on failure
        """
        if self.is_demo_mode:
            # Return a mock record in demo mode
            return {
                "id": str(uuid.uuid4()),
                "transcript_id": website_enrichment.transcript_id,
                "website_url": website_enrichment.website_url,
                "status": "pending",
                "created_at": "2023-01-01T00:00:00.000Z",
                "updated_at": "2023-01-01T00:00:00.000Z"
            }
            
        data = {
            "transcript_id": website_enrichment.transcript_id,
            "website_url": website_enrichment.website_url,
            "status": website_enrichment.status
        }
        
        # Use admin client if available to bypass RLS
        client_to_use = self.admin_client if self.admin_client else self.client
        
        try:
            logger.info(f"Inserting website enrichment record for transcript {website_enrichment.transcript_id}...")
            
            # Insert record into the website_enrichments table
            response = client_to_use.table('website_enrichments').insert(data).execute()
            
            # Verify the response
            if not response.data or len(response.data) == 0:
                logger.warning(f"Insert operation executed but no data returned")
                return None
                
            logger.info(f"Successfully inserted website enrichment record with ID: {response.data[0]['id']}")
            return response.data[0]
        except Exception as e:
            logger.exception(f"Error inserting website enrichment record: {str(e)}")
            return None
    
    def update_website_enrichment(self, enrichment_id: str, update_data: Dict[str, Any]) -> bool:
        """
        Update a website enrichment record.
        
        Args:
            enrichment_id: ID of the website enrichment record
            update_data: Dictionary of fields to update
            
        Returns:
            True if successful, False otherwise
        """
        if self.is_demo_mode:
            return True
            
        # Use admin client if available to bypass RLS
        client_to_use = self.admin_client if self.admin_client else self.client
        
        try:
            logger.info(f"Updating website enrichment record {enrichment_id}...")
            
            # Always update the updated_at timestamp
            if "updated_at" not in update_data:
                update_data["updated_at"] = self.get_current_timestamp()
                
            # Update the record
            response = client_to_use.table('website_enrichments').update(update_data).eq('id', enrichment_id).execute()
            
            # Verify the response
            if not response.data or len(response.data) == 0:
                logger.warning(f"Update operation executed but no data returned")
                return False
                
            logger.info(f"Successfully updated website enrichment record")
            return True
        except Exception as e:
            logger.exception(f"Error updating website enrichment record: {str(e)}")
            return False
    
    def get_website_enrichment(self, transcript_id: str) -> Optional[Dict[str, Any]]:
        """
        Get website enrichment record for a transcript.
        
        Args:
            transcript_id: ID of the transcript
            
        Returns:
            Website enrichment record or None if not found
        """
        if self.is_demo_mode:
            return {
                "id": str(uuid.uuid4()),
                "transcript_id": transcript_id,
                "website_url": "https://example.com",
                "status": "ok",
                "parsed_data": {"name": "Example Company", "about": "This is a sample company"},
                "created_at": "2023-01-01T00:00:00.000Z",
                "updated_at": "2023-01-01T00:00:00.000Z"
            }
            
        # Use admin client if available to bypass RLS
        client_to_use = self.admin_client if self.admin_client else self.client
        
        try:
            logger.info(f"Getting website enrichment for transcript {transcript_id}...")
            
            # Query the website_enrichments table
            response = client_to_use.table('website_enrichments').select('*').eq('transcript_id', transcript_id).execute()
            
            if response.data and len(response.data) > 0:
                return response.data[0]
            
            logger.info(f"No website enrichment found for transcript {transcript_id}")
            return None
        except Exception as e:
            logger.exception(f"Error getting website enrichment: {str(e)}")
            return None
    
    # Methods for LinkedIn enrichment
    def insert_linkedin_enrichment(self, linkedin_enrichment) -> Optional[Dict[str, Any]]:
        """
        Insert a new LinkedIn enrichment record.
        
        Args:
            linkedin_enrichment: LinkedInEnrichment object with transcript_id and linkedin_url
            
        Returns:
            The created LinkedIn enrichment record or None on failure
        """
        if self.is_demo_mode:
            # Return a mock record in demo mode
            return {
                "id": str(uuid.uuid4()),
                "transcript_id": linkedin_enrichment.transcript_id,
                "linkedin_url": linkedin_enrichment.linkedin_url,
                "status": "pending",
                "created_at": "2023-01-01T00:00:00.000Z",
                "updated_at": "2023-01-01T00:00:00.000Z"
            }
            
        data = {
            "transcript_id": linkedin_enrichment.transcript_id,
            "linkedin_url": linkedin_enrichment.linkedin_url,
            "status": linkedin_enrichment.status
        }
        
        # Use admin client if available to bypass RLS
        client_to_use = self.admin_client if self.admin_client else self.client
        
        try:
            logger.info(f"Inserting LinkedIn enrichment record for transcript {linkedin_enrichment.transcript_id}...")
            
            # Insert record into the linkedin_enrichments table
            response = client_to_use.table('linkedin_enrichments').insert(data).execute()
            
            # Verify the response
            if not response.data or len(response.data) == 0:
                logger.warning(f"Insert operation executed but no data returned")
                return None
                
            logger.info(f"Successfully inserted LinkedIn enrichment record with ID: {response.data[0]['id']}")
            return response.data[0]
        except Exception as e:
            logger.exception(f"Error inserting LinkedIn enrichment record: {str(e)}")
            return None
    
    def update_linkedin_enrichment(self, enrichment_id: str, update_data: Dict[str, Any]) -> bool:
        """
        Update a LinkedIn enrichment record.
        
        Args:
            enrichment_id: ID of the LinkedIn enrichment record
            update_data: Dictionary of fields to update
            
        Returns:
            True if successful, False otherwise
        """
        if self.is_demo_mode:
            return True
            
        # Use admin client if available to bypass RLS
        client_to_use = self.admin_client if self.admin_client else self.client
        
        try:
            logger.info(f"Updating LinkedIn enrichment record {enrichment_id}...")
            
            # Always update the updated_at timestamp
            if "updated_at" not in update_data:
                update_data["updated_at"] = self.get_current_timestamp()
                
            # Update the record
            response = client_to_use.table('linkedin_enrichments').update(update_data).eq('id', enrichment_id).execute()
            
            # Verify the response
            if not response.data or len(response.data) == 0:
                logger.warning(f"Update operation executed but no data returned")
                return False
                
            logger.info(f"Successfully updated LinkedIn enrichment record")
            return True
        except Exception as e:
            logger.exception(f"Error updating LinkedIn enrichment record: {str(e)}")
            return False
    
    def get_linkedin_enrichments(self, transcript_id: str) -> List[Dict[str, Any]]:
        """
        Get all LinkedIn enrichment records for a transcript.
        
        Args:
            transcript_id: ID of the transcript
            
        Returns:
            List of LinkedIn enrichment records
        """
        if self.is_demo_mode:
            # Generate a random ID for demo mode
            demo_id = str(uuid.uuid4())
            return [
                {
                    "id": demo_id,
                    "transcript_id": transcript_id,
                    "linkedin_url": "https://www.linkedin.com/in/demo-profile",
                    "status": "ok",
                    "profile_data": {
                        "name": "Demo User",
                        "headline": "This is a demo profile for testing",
                        "company": "Demo Company",
                        "location": "Demo Location"
                    },
                    "created_at": self.get_current_timestamp(),
                    "updated_at": self.get_current_timestamp()
                }
            ]

        # Use admin client if available to bypass RLS
        client_to_use = self.admin_client if self.admin_client else self.client
        
        try:
            logger.info(f"Getting LinkedIn enrichments for transcript {transcript_id}...")
            
            # Query the linkedin_enrichments table
            response = client_to_use.table('linkedin_enrichments').select('*').eq('transcript_id', transcript_id).execute()
            
            if response.data:
                return response.data
            
            logger.info(f"No LinkedIn enrichments found for transcript {transcript_id}")
            return []
        except Exception as e:
            logger.exception(f"Error getting LinkedIn enrichments: {str(e)}")
            return []
            
    def get_current_timestamp(self) -> str:
        """Get the current timestamp in ISO format"""
        from datetime import datetime
        return datetime.utcnow().isoformat()

    def _chunked_upload(self, file_path: str, storage_path: str, bucket: str = None) -> str:
        """
        Upload a large file to Supabase Storage by splitting it into smaller segments
        
        Args:
            file_path: Local path to the file
            storage_path: Target path in storage (including filename)
            bucket: Storage bucket name (default: from SUPABASE_STORAGE_BUCKET)
            
        Returns:
            Public URL of the uploaded file or local path in demo mode
        """
        if bucket is None:
            bucket = SUPABASE_STORAGE_BUCKET
        
        file_size = os.path.getsize(file_path)
        file_size_mb = file_size / (1024 * 1024)
        logger.info(f"Starting chunked upload for file: {file_path} ({file_size_mb:.2f}MB)")
        
        # For very large files, we'll use a smaller intermediate optimized file if possible
        max_optimized_size = 100 * 1024 * 1024  # 100MB max for optimization
        
        # If the file is a media file and is large, try to optimize it first
        file_ext = os.path.splitext(file_path)[1].lower()
        media_extensions = ['.mp4', '.mov', '.avi', '.mkv', '.mp3', '.m4a', '.wav']
        
        optimized_path = None
        should_optimize = file_size > max_optimized_size and file_ext in media_extensions
        
        if should_optimize:
            try:
                import subprocess
                with tempfile.TemporaryDirectory() as temp_dir:
                    optimized_path = os.path.join(temp_dir, f"optimized{file_ext}")
                    # Optimize the media file
                    logger.info(f"Optimizing media file for storage: {file_path} -> {optimized_path}")
                    
                    # Use different parameters based on file type
                    is_audio = file_ext in ['.mp3', '.m4a', '.wav']
                    
                    if is_audio:
                        cmd = [
                            "ffmpeg", "-i", file_path, 
                            "-map_metadata", "-1",  # Remove metadata
                            "-ac", "1",             # Mono
                            "-c:a", "aac",          # AAC codec (widely supported)
                            "-b:a", "96k",          # Moderate bitrate
                            optimized_path, "-y"
                        ]
                    else:
                        # For video
                        cmd = [
                            "ffmpeg", "-i", file_path,
                            "-map_metadata", "-1",   # Remove metadata
                            "-c:v", "libx264",       # H.264 video
                            "-crf", "28",            # Compression quality (higher = smaller)
                            "-preset", "fast",       # Encoding speed
                            "-c:a", "aac",           # AAC audio
                            "-b:a", "96k",           # Audio bitrate
                            "-ac", "1",              # Mono audio
                            optimized_path, "-y"
                        ]
                        
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    
                    if result.returncode != 0:
                        logger.error(f"Error optimizing file: {result.stderr}")
                        optimized_path = None
                    else:
                        opt_size = os.path.getsize(optimized_path)
                        opt_size_mb = opt_size / (1024 * 1024)
                        logger.info(f"Optimized file: {file_size_mb:.2f}MB -> {opt_size_mb:.2f}MB")
                        
                        if opt_size < MAX_SUPABASE_UPLOAD_SIZE:
                            # If optimized file is small enough for direct upload
                            logger.info("Optimized file is small enough for direct upload")
                            with open(optimized_path, "rb") as file_content:
                                response = self.admin_client.storage.from_(bucket).upload(
                                    path=storage_path,
                                    file=file_content,
                                    file_options={"upsert": "true"}
                                )
                                url = self.admin_client.storage.from_(bucket).get_public_url(storage_path)
                                logger.info(f"Optimized file uploaded successfully. URL: {url}")
                                return url
            except Exception as opt_error:
                logger.exception(f"Error during file optimization: {str(opt_error)}")
                optimized_path = None
        
        # If we get here, either optimization failed or the optimized file is still too large
        # Since we decided not to store original files anymore, just return the original path
        logger.info("File too large for Supabase storage - returning original path as per policy to not store large files")
        return file_path

# Create global client instance for reuse
supabase = SupabaseManager()

