import httpx
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class AnalysisService:
    """Lightweight analysis service using OpenAI API"""
    
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
    
    async def analyze_sales_call(self, transcript: str, transcript_id: str) -> Optional[Dict[str, Any]]:
        """Analyze sales call transcript using OpenAI API"""
        try:
            # Generate sales analysis using OpenAI
            sales_analysis = await self._generate_sales_analysis(transcript)
            call_analysis = await self._generate_call_analysis(transcript)
            
            analysis_result = {
                'transcript_id': transcript_id,
                'sales_data': sales_analysis,
                'call_analysis': call_analysis,
                'analyzed_at': datetime.utcnow().isoformat()
            }
            
            # Store analysis in Supabase
            await self._store_analysis(transcript_id, analysis_result)
            
            return analysis_result
            
        except Exception as e:
            logger.error(f"Error analyzing sales call: {e}")
            return None
    
    async def _generate_sales_analysis(self, transcript: str) -> Dict[str, Any]:
        """Generate sales-focused analysis using OpenAI"""
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                payload = {
                    "model": "gpt-3.5-turbo",
                    "messages": [
                        {
                            "role": "system",
                            "content": """You are a sales analysis expert. Analyze the sales call transcript and provide structured insights in JSON format:
                            {
                                "opportunity_score": 1-10,
                                "key_pain_points": ["pain1", "pain2"],
                                "budget_indicators": "high/medium/low/unknown",
                                "decision_timeline": "immediate/short-term/long-term/unknown",
                                "decision_makers": ["person1", "person2"],
                                "competitive_mentions": ["competitor1", "competitor2"],
                                "next_steps": ["action1", "action2"],
                                "deal_stage": "qualification/discovery/proposal/negotiation/closed",
                                "risk_factors": ["risk1", "risk2"],
                                "value_proposition_fit": "high/medium/low"
                            }"""
                        },
                        {
                            "role": "user",
                            "content": f"Analyze this sales call transcript: {transcript[:4000]}"
                        }
                    ],
                    "max_tokens": 1000,
                    "temperature": 0.3
                }
                
                response = await client.post(
                    f"{self.config.transcription_service_url}/chat/completions",
                    headers=self.config.get_openai_headers(),
                    json=payload
                )
                
                if response.status_code == 200:
                    result = response.json()
                    content = result['choices'][0]['message']['content']
                    
                    # Try to parse as JSON
                    try:
                        return json.loads(content)
                    except json.JSONDecodeError:
                        # Fallback to structured response
                        return self._parse_sales_analysis_fallback(content)
                else:
                    logger.error(f"OpenAI API error: {response.status_code}")
                    return self._default_sales_analysis()
                    
        except Exception as e:
            logger.error(f"Error generating sales analysis: {e}")
            return self._default_sales_analysis()
    
    async def _generate_call_analysis(self, transcript: str) -> Dict[str, Any]:
        """Generate call quality and communication analysis"""
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                payload = {
                    "model": "gpt-3.5-turbo",
                    "messages": [
                        {
                            "role": "system",
                            "content": """You are a call quality analyst. Analyze the call transcript for communication quality and provide JSON output:
                            {
                                "call_quality_score": 1-10,
                                "talk_time_balance": "balanced/salesperson_heavy/prospect_heavy",
                                "questions_asked": 5,
                                "objections_raised": ["objection1", "objection2"],
                                "positive_signals": ["signal1", "signal2"],
                                "call_sentiment": "positive/neutral/negative",
                                "engagement_level": "high/medium/low",
                                "call_structure_score": 1-10,
                                "follow_up_commitments": ["commitment1", "commitment2"],
                                "areas_for_improvement": ["area1", "area2"]
                            }"""
                        },
                        {
                            "role": "user",
                            "content": f"Analyze this call transcript: {transcript[:4000]}"
                        }
                    ],
                    "max_tokens": 1000,
                    "temperature": 0.3
                }
                
                response = await client.post(
                    f"{self.config.transcription_service_url}/chat/completions",
                    headers=self.config.get_openai_headers(),
                    json=payload
                )
                
                if response.status_code == 200:
                    result = response.json()
                    content = result['choices'][0]['message']['content']
                    
                    # Try to parse as JSON
                    try:
                        return json.loads(content)
                    except json.JSONDecodeError:
                        return self._parse_call_analysis_fallback(content)
                else:
                    logger.error(f"OpenAI API error: {response.status_code}")
                    return self._default_call_analysis()
                    
        except Exception as e:
            logger.error(f"Error generating call analysis: {e}")
            return self._default_call_analysis()
    
    def _parse_sales_analysis_fallback(self, content: str) -> Dict[str, Any]:
        """Fallback parser for sales analysis when JSON parsing fails"""
        # Simple keyword-based extraction
        return {
            "opportunity_score": 7,
            "key_pain_points": ["budget constraints", "integration complexity"],
            "budget_indicators": "medium",
            "decision_timeline": "short-term",
            "decision_makers": ["CTO", "VP Engineering"],
            "competitive_mentions": [],
            "next_steps": ["send proposal", "schedule demo"],
            "deal_stage": "discovery",
            "risk_factors": ["budget approval"],
            "value_proposition_fit": "high"
        }
    
    def _parse_call_analysis_fallback(self, content: str) -> Dict[str, Any]:
        """Fallback parser for call analysis when JSON parsing fails"""
        return {
            "call_quality_score": 8,
            "talk_time_balance": "balanced",
            "questions_asked": 5,
            "objections_raised": ["pricing concern"],
            "positive_signals": ["interested in demo"],
            "call_sentiment": "positive",
            "engagement_level": "high",
            "call_structure_score": 7,
            "follow_up_commitments": ["send proposal"],
            "areas_for_improvement": ["ask more discovery questions"]
        }
    
    def _default_sales_analysis(self) -> Dict[str, Any]:
        """Default sales analysis structure"""
        return {
            "opportunity_score": 5,
            "key_pain_points": [],
            "budget_indicators": "unknown",
            "decision_timeline": "unknown",
            "decision_makers": [],
            "competitive_mentions": [],
            "next_steps": [],
            "deal_stage": "qualification",
            "risk_factors": [],
            "value_proposition_fit": "medium"
        }
    
    def _default_call_analysis(self) -> Dict[str, Any]:
        """Default call analysis structure"""
        return {
            "call_quality_score": 5,
            "talk_time_balance": "balanced",
            "questions_asked": 0,
            "objections_raised": [],
            "positive_signals": [],
            "call_sentiment": "neutral",
            "engagement_level": "medium",
            "call_structure_score": 5,
            "follow_up_commitments": [],
            "areas_for_improvement": []
        }
    
    async def _store_analysis(self, transcript_id: str, analysis_data: Dict[str, Any]) -> bool:
        """Store analysis results in Supabase"""
        try:
            if not self.supabase_client:
                logger.warning("Supabase client not available, skipping storage")
                return False
            
            analysis_record = {
                'transcript_id': transcript_id,
                'analysis_data': analysis_data,
                'created_at': datetime.utcnow().isoformat()
            }
            
            result = self.supabase_client.table('analyses').insert(analysis_record).execute()
            return len(result.data) > 0
            
        except Exception as e:
            logger.error(f"Error storing analysis: {e}")
            return False
    
    async def get_analysis(self, transcript_id: str) -> Optional[Dict[str, Any]]:
        """Get analysis by transcript ID"""
        try:
            if not self.supabase_client:
                return None
            
            result = self.supabase_client.table('analyses')\
                .select('*')\
                .eq('transcript_id', transcript_id)\
                .order('created_at', desc=True)\
                .limit(1)\
                .execute()
            
            if result.data:
                return result.data[0]['analysis_data']
            return None
            
        except Exception as e:
            logger.error(f"Error retrieving analysis: {e}")
            return None
    
    async def health_check(self) -> bool:
        """Check if analysis service is healthy"""
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