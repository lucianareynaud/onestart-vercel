#!/usr/bin/env python3
"""
Script to run the company website scraper from the main application.

This can be used to trigger website scraping from the FastAPI application.
"""
import os
import sys
import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def run_website_scraper(url: str, output_file: Optional[str] = None, save_to_file: bool = False) -> Dict[str, Any]:
    """
    Run the company website scraper directly.
    
    Args:
        url: URL of the company website
        output_file: Optional path to save JSON file
        
    Returns:
        Dictionary containing scraped company data
    """
    try:
        # Determine if we need to save to a file
        temp_output = None
        if save_to_file:
            # Ensure output directory exists if we're saving to a file
            if output_file:
                os.makedirs(os.path.dirname(output_file), exist_ok=True)
                temp_output = output_file
            else:
                # Use a temporary file instead of creating one in the output directory
                import tempfile
                temp_dir = tempfile.gettempdir()
                temp_output = os.path.join(temp_dir, f"company_{url.replace('https://', '').replace('http://', '').replace('/', '_').split('?')[0]}.json")
        
        # Se o site não estiver acessível, retornar um resultado básico com o nome da empresa extraído da URL
        domain = url.replace('https://', '').replace('http://', '').split('/')[0]
        company_name = domain.split('.')[0].capitalize()
        if '.' in domain and domain.split('.')[-2] != 'com':
            company_name = domain.split('.')[-2].capitalize()
            
        # Criar um resultado padrão mínimo como fallback
        fallback_data = {
            "name": company_name,
            "domain": domain,
            "about": f"Empresa com domínio {domain}",
            "services": [],
            "team": [],
            "contact": {},
            "social_links": {},
            "technologies": []
        }
        
        # Usar requests para verificar se o site está acessível
        import requests
        try:
            response = requests.get(url, timeout=10)
            if response.status_code != 200:
                logger.warning(f"Website returned status code {response.status_code}")
                return fallback_data
        except Exception as e:
            logger.warning(f"Couldn't access website: {e}")
            return fallback_data
        
        # Criar um spider temporário para extração
        spider_code = f"""
import sys
from pathlib import Path
import re
import logging
import urllib.parse
from typing import Dict, Any, Optional, List, Set
from datetime import datetime

import scrapy

class CompanyWebsiteSpider(scrapy.Spider):
    \"\"\"
    Spider temporário para extrair informações do website da empresa.
    \"\"\"
    name = "company_website_temp"
    
    def __init__(self, url=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if not url:
            self.logger.error("Company website URL is required")
            return
            
        # Parse and validate URL
        self.start_url = self._normalize_url(url)
        self.start_urls = [self.start_url]
        
        # Extract domain to limit crawling
        parsed_url = urllib.parse.urlparse(self.start_url)
        self.domain = parsed_url.netloc
        self.allowed_domains = [self.domain]
        
        # Initialize data containers
        domain = self.domain
        company_name = domain.split('.')[0].capitalize()
        if '.' in domain and domain.split('.')[-2] != 'com':
            company_name = domain.split('.')[-2].capitalize()
            
        self.company_data = {{
            "name": company_name,
            "domain": self.domain,
            "about": "",
            "services": [],
            "team": [],
            "contact": {{}},
            "social_links": {{}},
            "technologies": []
        }}
        
        # Track visited URLs to avoid duplicates
        self.visited_urls = set()
    
    def _normalize_url(self, url: str) -> str:
        \"\"\"Normalize URL to ensure it starts with http/https\"\"\"
        if not url.startswith(("http://", "https://")):
            return f"https://{{url}}"
        return url
        
    def parse(self, response):
        \"\"\"Main entry point for parsing the website\"\"\"
        self.logger.info(f"Parsing page: {{response.url}}")
        try:
            # Extract basic company info
            self._extract_company_name(response)
            self._extract_meta_description(response)
            
            # Extract contact information
            self._extract_contact_info(response)
            
            # Extract social links
            self._extract_social_links(response)
            
            # Follow links to other important pages
            for request in self._follow_important_links(response):
                yield request
            
            # Return the company data
            yield {{"company_data": self.company_data}}
        except Exception as e:
            self.logger.error(f"Error parsing response: {{e}}")
            # Still yield whatever data we have, even on error
            yield {{"company_data": self.company_data}}
    
    def _extract_company_name(self, response):
        \"\"\"Extract company name from the page\"\"\"
        # Try to get from title
        title = response.css('title::text').get() or ""
        if title:
            # Remove common suffixes like " - Home" or " | Official Website"
            cleaned_title = re.sub(r'\\s*[\\-|].*$', '', title).strip()
            if cleaned_title:
                self.company_data["name"] = cleaned_title
    
    def _extract_meta_description(self, response):
        \"\"\"Extract meta description\"\"\"
        meta_desc = response.css('meta[name="description"]::attr(content)').get()
        if meta_desc:
            self.company_data["about"] = meta_desc.strip()
            
        # If no meta description, try to find a reasonable about text
        if not self.company_data["about"]:
            about_candidates = [
                response.css('div.about p::text').getall(),
                response.css('section.about p::text').getall(),
                response.css('.about-section p::text').getall(),
                response.css('.about-us p::text').getall(),
                response.css('#about p::text').getall(),
                response.css('p:contains("sobre")::text').getall()
            ]
            
            for candidate in about_candidates:
                if candidate:
                    self.company_data["about"] = ' '.join([c.strip() for c in candidate])
                    break
    
    def _extract_contact_info(self, response):
        \"\"\"Extract contact information\"\"\"
        # Extract email addresses
        email_pattern = r'[\\w.+-]+@[\\w-]+\\.[\\w.-]+'
        emails = re.findall(email_pattern, response.text)
        if emails:
            # Filter out common false positives
            filtered_emails = [e for e in emails if not e.endswith(('.png', '.jpg', '.gif'))]
            if filtered_emails:
                self.company_data["contact"]["email"] = filtered_emails[0]
        
        # Extract phone numbers
        phone_pattern = r'\\+?[\\d\\s\\(\\)\\-]{10,}'
        phones = re.findall(phone_pattern, response.text)
        if phones:
            # Clean up phone numbers
            cleaned_phones = [re.sub(r'[^\\d+]', '', p) for p in phones]
            cleaned_phones = [p for p in cleaned_phones if len(p) >= 8]
            if cleaned_phones:
                self.company_data["contact"]["phone"] = cleaned_phones[0]
        
        # Look for addresses
        address_selectors = [
            'address',
            '.address',
            '.contact-address',
            'p:contains("endereço")',
            'p:contains("Endereço")'
        ]
        
        for selector in address_selectors:
            address_elements = response.css(f'{{selector}}::text').getall()
            if address_elements:
                self.company_data["contact"]["address"] = ' '.join([a.strip() for a in address_elements])
                break
    
    def _extract_social_links(self, response):
        \"\"\"Extract social media links\"\"\"
        social_platforms = {{
            'linkedin': ['linkedin.com'],
            'facebook': ['facebook.com', 'fb.com'],
            'twitter': ['twitter.com', 'x.com'],
            'instagram': ['instagram.com'],
            'youtube': ['youtube.com'],
            'github': ['github.com']
        }}
        
        for platform, domains in social_platforms.items():
            for domain in domains:
                links = response.css(f'a[href*="{{domain}}"]::attr(href)').getall()
                if links and platform not in self.company_data['social_links']:
                    self.company_data['social_links'][platform] = links[0]
    
    def _follow_important_links(self, response):
        \"\"\"Follow links to important pages\"\"\"
        important_pages = ['about', 'contact', 'services', 'team', 'products', 'solutions', 'sobre', 'contato', 'servicos', 'equipe', 'produtos', 'solucoes']
        
        for link in response.css('a::attr(href)'):
            href = link.get()
            if not href:
                continue
                
            # Process only absolute URLs or relative URLs from the same domain
            if href.startswith(('http://', 'https://')):
                if not href.startswith(self.start_url) and not href.startswith(f"https://{{self.domain}}") and not href.startswith(f"http://{{self.domain}}"):
                    continue
            
            # Check if this is an important page
            for page in important_pages:
                if page in href.lower() and href not in self.visited_urls:
                    self.visited_urls.add(href)
                    yield scrapy.Request(response.urljoin(href), callback=self.parse)
                    break
"""
        
        # Escrever o spider temporário para um arquivo
        temp_spider_path = "temp_company_spider.py"
        with open(temp_spider_path, "w") as f:
            f.write(spider_code)
        
        cmd = [
            sys.executable, 
            "-m", 
            "scrapy",
            "runspider",
            temp_spider_path,
            "-a", 
            f"url={url}",
            "-o",
            temp_output,
            "--nolog"  # Silence scrapy logs as we use our own logger
        ]
        
        logger.info(f"Running command: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(cmd, check=True, stderr=subprocess.PIPE, text=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"Scrapy process failed: {e}")
            logger.error(f"Stderr: {e.stderr}")
            # Return the fallback data on error
            return fallback_data
        
        # Load the data from the output file
        if os.path.exists(temp_output):
            with open(temp_output, 'r', encoding='utf-8') as f:
                try:
                    data = json.load(f)
                    
                    # Verificar se temos dados
                    if not data or len(data) == 0:
                        logger.warning(f"Scrapy produced empty result for {url}")
                        return fallback_data
                        
                    # Scrapy outputs a list, but we want just the company_data object
                    company_data = data[0].get('company_data', {}) if isinstance(data, list) and len(data) > 0 else {}
                    
                    if not company_data:
                        logger.warning(f"No company_data found in Scrapy results for {url}")
                        return fallback_data
                        
                    logger.info(f"Scraped company data from {url}")
                    
                    # Cleanup the temporary spider file
                    try:
                        os.remove(temp_spider_path)
                    except:
                        pass
                        
                    return company_data
                except json.JSONDecodeError:
                    logger.error(f"Error decoding JSON from {temp_output}")
                    return fallback_data
        else:
            logger.warning(f"Output file not found: {temp_output}")
            return fallback_data
    
    except Exception as e:
        logger.error(f"Error running company website scraper: {e}")
        # Return a basic result based on the URL in case of complete failure
        domain = url.replace('https://', '').replace('http://', '').split('/')[0]
        company_name = domain.split('.')[0].capitalize()
        if '.' in domain and domain.split('.')[-2] != 'com':
            company_name = domain.split('.')[-2].capitalize()
            
        return {
            "name": company_name,
            "domain": domain,
            "about": "Não foi possível extrair informações do site da empresa",
            "services": [],
            "team": [],
            "contact": {},
            "social_links": {},
            "technologies": [],
            "error": str(e)
        }

if __name__ == "__main__":
    # Example usage
    if len(sys.argv) > 1:
        website_url = sys.argv[1]
        output_path = sys.argv[2] if len(sys.argv) > 2 else None
        
        logger.info(f"Scraping website: {website_url}")
        company_data = run_website_scraper(website_url, output_path)
        
        print(json.dumps(company_data, indent=2, ensure_ascii=False))
    else:
        print("Usage: python run_website_scraper.py <website_url> [<output_file>]")
        sys.exit(1) 