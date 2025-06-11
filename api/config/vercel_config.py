import os
from typing import Dict, Any
from dotenv import load_dotenv

load_dotenv()

class VercelConfig:
    """Configuration for Vercel deployment"""
    
    def __init__(self):
        # Database configuration
        self.supabase_url = os.getenv("SUPABASE_URL")
        self.supabase_anon_key = os.getenv("SUPABASE_ANON_KEY") 
        self.supabase_service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        
        # External API keys
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.brightdata_api_key = os.getenv("BRIGHTDATA_API_KEY")
        self.scrapingdog_api_key = os.getenv("SCRAPINGDOG_API_KEY")
        
        # Service endpoints
        self.transcription_service_url = os.getenv("TRANSCRIPTION_SERVICE_URL", "https://api.openai.com/v1")
        self.enrichment_service_url = os.getenv("ENRICHMENT_SERVICE_URL", "https://api.scrapingdog.com/")
        
        # Vercel-specific settings
        self.max_file_size = 25 * 1024 * 1024  # 25MB (Vercel limit)
        self.request_timeout = 290  # Just under Vercel's 300s limit
        
    def get_openai_headers(self) -> Dict[str, str]:
        """Get headers for OpenAI API requests"""
        return {
            "Authorization": f"Bearer {self.openai_api_key}",
            "Content-Type": "application/json"
        }
    
    def get_scraping_headers(self) -> Dict[str, str]:
        """Get headers for web scraping API requests"""
        return {
            "X-API-Key": self.scrapingdog_api_key or self.brightdata_api_key,
            "Content-Type": "application/json"
        }
    
    def is_ready(self) -> bool:
        """Check if all required configuration is available"""
        required_vars = [
            self.supabase_url,
            self.supabase_anon_key,
            self.openai_api_key
        ]
        return all(var for var in required_vars)

# Global config instance
_config = None

def get_config() -> VercelConfig:
    """Get the global configuration instance"""
    global _config
    if _config is None:
        _config = VercelConfig()
    return _config 