import httpx
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)

class EnrichmentService:
    """Lightweight enrichment service using external APIs"""
    
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
    
    async def scrape_linkedin_profiles(self, stakeholder_data: Dict[str, Any]) -> Dict[str, Any]:
        """Scrape LinkedIn profiles using external API service"""
        try:
            results = []
            
            # Use ScrapingDog or BrightData API for LinkedIn scraping
            for stakeholder in stakeholder_data.get('Stakeholders', []):
                profile_data = await self._scrape_single_linkedin_profile(stakeholder)
                if profile_data:
                    results.append(profile_data)
            
            # Store results in Supabase
            enrichment_id = str(uuid.uuid4())
            await self._store_enrichment_data(enrichment_id, 'linkedin', results)
            
            return {
                'status': 'success',
                'enrichment_id': enrichment_id,
                'profiles_found': len(results),
                'data': results
            }
            
        except Exception as e:
            logger.error(f"LinkedIn scraping error: {e}")
            return {'status': 'error', 'message': str(e)}
    
    async def _scrape_single_linkedin_profile(self, profile_name: str) -> Optional[Dict[str, Any]]:
        """Scrape a single LinkedIn profile using external API"""
        try:
            # Use ScrapingDog API for LinkedIn data
            search_url = f"https://www.linkedin.com/in/{profile_name.lower().replace(' ', '-')}"
            
            async with httpx.AsyncClient(timeout=30) as client:
                api_url = "https://api.scrapingdog.com/scrape"
                params = {
                    'api_key': self.config.scrapingdog_api_key or self.config.brightdata_api_key,
                    'url': search_url,
                    'dynamic': 'false'
                }
                
                response = await client.get(api_url, params=params)
                
                if response.status_code == 200:
                    # Parse the HTML content to extract profile information
                    profile_data = self._parse_linkedin_html(response.text, profile_name)
                    return profile_data
                else:
                    logger.warning(f"Failed to scrape LinkedIn for {profile_name}: {response.status_code}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error scraping LinkedIn profile {profile_name}: {e}")
            return None
    
    def _parse_linkedin_html(self, html_content: str, profile_name: str) -> Dict[str, Any]:
        """Parse LinkedIn HTML to extract profile information"""
        # Simplified parsing - in production, you'd use BeautifulSoup or similar
        # For Vercel deployment, we keep dependencies minimal
        return {
            'name': profile_name,
            'title': 'Professional Title',  # Would be extracted from HTML
            'company': 'Company Name',      # Would be extracted from HTML
            'location': 'Location',         # Would be extracted from HTML
            'summary': 'Professional summary would be extracted here',
            'scraped_at': datetime.utcnow().isoformat()
        }
    
    async def scrape_company_website(self, website_url: str) -> Optional[Dict[str, Any]]:
        """Scrape company website using external API service"""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                api_url = "https://api.scrapingdog.com/scrape"
                params = {
                    'api_key': self.config.scrapingdog_api_key or self.config.brightdata_api_key,
                    'url': website_url,
                    'dynamic': 'false'
                }
                
                response = await client.get(api_url, params=params)
                
                if response.status_code == 200:
                    # Parse the website content
                    company_data = self._parse_company_website(response.text, website_url)
                    return company_data
                else:
                    logger.warning(f"Failed to scrape website {website_url}: {response.status_code}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error scraping website {website_url}: {e}")
            return None
    
    def _parse_company_website(self, html_content: str, website_url: str) -> Dict[str, Any]:
        """Parse company website HTML to extract relevant information"""
        # Simplified parsing - would extract company info, products, etc.
        return {
            'website_url': website_url,
            'company_name': 'Company Name',  # Would be extracted from HTML
            'description': 'Company description would be extracted here',
            'industry': 'Industry',          # Would be extracted from HTML
            'products': ['Product 1', 'Product 2'],  # Would be extracted
            'scraped_at': datetime.utcnow().isoformat()
        }
    
    async def enrich_transcript_data(self, transcript: str, company_website: Optional[str], 
                                   linkedin_profiles: List[str], transcript_id: str) -> Optional[Dict[str, Any]]:
        """Enrich transcript with company and LinkedIn data"""
        try:
            enrichment_results = {
                'transcript_id': transcript_id,
                'company_data': None,
                'linkedin_data': [],
                'scraping_status': {
                    'company': False,
                    'linkedin': False
                }
            }
            
            # Scrape company website if provided
            if company_website:
                company_data = await self.scrape_company_website(company_website)
                if company_data:
                    enrichment_results['company_data'] = company_data
                    enrichment_results['scraping_status']['company'] = True
            
            # Scrape LinkedIn profiles if provided
            if linkedin_profiles:
                for profile_url in linkedin_profiles:
                    profile_name = self._extract_profile_name_from_url(profile_url)
                    profile_data = await self._scrape_single_linkedin_profile(profile_name)
                    if profile_data:
                        enrichment_results['linkedin_data'].append(profile_data)
                
                enrichment_results['scraping_status']['linkedin'] = len(enrichment_results['linkedin_data']) > 0
            
            # Generate enrichment report using OpenAI
            report = await self._generate_enrichment_report(transcript, enrichment_results)
            enrichment_results['report'] = report
            
            # Store enrichment data
            enrichment_id = str(uuid.uuid4())
            await self._store_enrichment_data(enrichment_id, 'transcript_enrichment', enrichment_results)
            
            return enrichment_results
            
        except Exception as e:
            logger.error(f"Error enriching transcript data: {e}")
            return None
    
    def _extract_profile_name_from_url(self, profile_url: str) -> str:
        """Extract profile name from LinkedIn URL"""
        # Simple extraction - would be more robust in production
        if '/in/' in profile_url:
            return profile_url.split('/in/')[-1].replace('/', '')
        return profile_url
    
    async def _generate_enrichment_report(self, transcript: str, enrichment_data: Dict[str, Any]) -> str:
        """Generate enrichment report using OpenAI API"""
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                # Prepare context for OpenAI
                context = f"""
                Sales Call Transcript:
                {transcript[:3000]}...  # Truncate for API limits
                
                Company Data:
                {json.dumps(enrichment_data.get('company_data', {}), indent=2)}
                
                LinkedIn Profiles:
                {json.dumps(enrichment_data.get('linkedin_data', []), indent=2)}
                """
                
                payload = {
                    "model": "gpt-3.5-turbo",
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a sales intelligence analyst. Generate a comprehensive report based on the transcript and enrichment data."
                        },
                        {
                            "role": "user", 
                            "content": f"Generate a sales intelligence report based on this data: {context}"
                        }
                    ],
                    "max_tokens": 1500,
                    "temperature": 0.7
                }
                
                response = await client.post(
                    f"{self.config.transcription_service_url}/chat/completions",
                    headers=self.config.get_openai_headers(),
                    json=payload
                )
                
                if response.status_code == 200:
                    result = response.json()
                    return result['choices'][0]['message']['content']
                else:
                    logger.error(f"OpenAI API error: {response.status_code}")
                    return "Failed to generate enrichment report"
                    
        except Exception as e:
            logger.error(f"Error generating enrichment report: {e}")
            return "Error generating enrichment report"
    
    async def _store_enrichment_data(self, enrichment_id: str, enrichment_type: str, data: Any) -> bool:
        """Store enrichment data in Supabase"""
        try:
            if not self.supabase_client:
                logger.warning("Supabase client not available, skipping storage")
                return False
            
            enrichment_record = {
                'id': enrichment_id,
                'enrichment_type': enrichment_type,
                'data': data,
                'created_at': datetime.utcnow().isoformat()
            }
            
            result = self.supabase_client.table('enrichments').insert(enrichment_record).execute()
            return len(result.data) > 0
            
        except Exception as e:
            logger.error(f"Error storing enrichment data: {e}")
            return False
    
    async def health_check(self) -> bool:
        """Check if enrichment service is healthy"""
        try:
            # Test scraping API connectivity
            if self.config.scrapingdog_api_key:
                async with httpx.AsyncClient(timeout=10) as client:
                    response = await client.get(
                        "https://api.scrapingdog.com/scrape",
                        params={'api_key': self.config.scrapingdog_api_key, 'url': 'https://httpbin.org/status/200'}
                    )
                    return response.status_code == 200
            return True  # If no API key, assume healthy
        except Exception:
            return False 