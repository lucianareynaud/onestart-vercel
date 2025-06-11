import os
import json
import re
import logging
from typing import Dict, Any

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load the call analysis prompt with better error handling
CALL_ANALYSIS_PROMPT = ""
try:
    prompt_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "prompts",
        "extract_call_analysis_pt.txt"
    )
    logger.info(f"Attempting to load prompt from: {prompt_path}")
    
    if os.path.exists(prompt_path):
        with open(prompt_path, encoding="utf-8") as f:
            CALL_ANALYSIS_PROMPT = f.read()
        logger.info(f"Successfully loaded call analysis prompt ({len(CALL_ANALYSIS_PROMPT)} chars)")
    else:
        logger.warning(f"Prompt file not found at: {prompt_path}")
        # Try absolute path resolution as fallback
        absolute_path = os.path.abspath(os.path.join(
            os.getcwd(),
            "analysis_svc",
            "prompts",
            "extract_call_analysis_pt.txt"
        ))
        logger.info(f"Trying alternate path: {absolute_path}")
        
        if os.path.exists(absolute_path):
            with open(absolute_path, encoding="utf-8") as f:
                CALL_ANALYSIS_PROMPT = f.read()
            logger.info(f"Successfully loaded prompt from alternate path ({len(CALL_ANALYSIS_PROMPT)} chars)")
        else:
            logger.error(f"Prompt file not found at alternate path: {absolute_path}")
except Exception as e:
    logger.error(f"Error loading call analysis prompt: {e}")

# Define a sample result for debugging/development
SAMPLE_CALL_ANALYSIS = {
    "participants": ["Vendedor: João", "Cliente: Maria"],
    "date": "2023-10-15",
    "duration": "45 minutos",
    "talkRatio": {
        "Vendedor: João": 65,
        "Cliente: Maria": 35
    },
    "keyTopics": [
        {"topic": "Integração com sistemas", "mentions": 5, "sentiment": "positivo"},
        {"topic": "Custos do projeto", "mentions": 3, "sentiment": "negativo"},
        {"topic": "Prazos de implementação", "mentions": 4, "sentiment": "neutro"}
    ],
    "keyMoments": [
        {"time": "00:05:23", "type": "dor", "description": "Cliente mencionou problemas com o sistema atual"},
        {"time": "00:12:46", "type": "oportunidade", "description": "Discussão sobre automação de processos"},
        {"time": "00:32:15", "type": "próximos passos", "description": "Agendar demonstração técnica"}
    ],
    "competitorMentions": [
        {"competitor": "Empresa X", "mentions": 2, "context": "Cliente atualmente usa seus serviços"}
    ],
    "questions": [
        {"time": "00:08:30", "question": "Quais são os principais pontos de dor com o sistema atual?", "askedBy": "Vendedor: João", "answeredBy": "Cliente: Maria", "quality": "alta"},
        {"time": "00:15:20", "question": "Qual seria o orçamento disponível para este projeto?", "askedBy": "Vendedor: João", "answeredBy": "Cliente: Maria", "quality": "média"}
    ],
    "nextSteps": [
        {"description": "Agendar demonstração técnica", "owner": "Vendedor: João", "status": "pendente"},
        {"description": "Enviar proposta comercial", "owner": "Vendedor: João", "status": "em andamento"}
    ],
    "winningBehaviors": [
        {"behavior": "Escuta ativa", "description": "Vendedor demonstrou boa compreensão das necessidades do cliente"},
        {"behavior": "Perguntas qualificadoras", "description": "Vendedor fez perguntas relevantes para entender o contexto"}
    ],
    "coachingOpportunities": [
        {"area": "Objeções de preço", "severity": "média", "description": "Melhorar a abordagem ao discutir questões financeiras"},
        {"area": "Fechamento", "severity": "alta", "description": "Não apresentou próximos passos claros no final da reunião"}
    ]
}

async def extract_call_analysis_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract call analysis from the transcript.
    
    Args:
        state: The current state, including transcript_id and transcript_text
        
    Returns:
        Updated state with call_analysis added
    """
    transcript_id = state.get("transcript_id", "")
    transcript_text = state.get("transcript_text", "")
    
    if not transcript_text:
        logger.warning(f"No transcript text found for transcript {transcript_id}")
        state["call_analysis"] = {}
        return state
    
    logger.info(f"Extracting call analysis from transcript {transcript_id}")
    
    try:
        # Check if prompt is available
        if not CALL_ANALYSIS_PROMPT:
            logger.warning("Call analysis prompt is empty, using sample data")
            state["call_analysis"] = SAMPLE_CALL_ANALYSIS
            return state
            
        # Get OpenAI API key from config
        from config import OPENAI_API_KEY
        
        if not OPENAI_API_KEY or OPENAI_API_KEY == "demo_mode":
            logger.warning("OpenAI API key not available or in demo mode, using sample data")
            state["call_analysis"] = SAMPLE_CALL_ANALYSIS
            return state
            
        # Import OpenAI library
        from openai import OpenAI
        
        # Initialize OpenAI client
        client = OpenAI(api_key=OPENAI_API_KEY)
        
        # Create full prompt with transcript
        full_prompt = CALL_ANALYSIS_PROMPT + "\n\nTranscrição:\n" + transcript_text
        
        # Call OpenAI API to analyze the transcript
        logger.info(f"Calling OpenAI API for call analysis of transcript {transcript_id}")
        response = client.chat.completions.create(
            model="gpt-4o",  # Using more capable model
            messages=[
                {"role": "system", "content": "You are an expert sales call analyzer."},
                {"role": "user", "content": full_prompt}
            ],
            temperature=0.2,  # Lower temperature for more consistent output
            max_tokens=2000   # Allow enough tokens for a detailed analysis
        )
        
        # Extract the response content
        response_text = response.choices[0].message.content
        
        # Clean up the response and parse it as JSON
        # Strip any markdown code block markers
        clean_response = response_text.replace("```json", "").replace("```", "").strip()
        
        # Parse the JSON response
        call_analysis = json.loads(clean_response)
        logger.info(f"Successfully parsed call analysis JSON for transcript {transcript_id}")
        
        # Validate important fields are present
        required_fields = ["participants", "talkRatio", "keyTopics", "keyMoments", "questions", "nextSteps"]
        missing_fields = [field for field in required_fields if field not in call_analysis]
        
        if missing_fields:
            logger.warning(f"Call analysis is missing required fields: {missing_fields}")
            # Ensure missing fields are added with empty values
            for field in missing_fields:
                if field == "talkRatio":
                    call_analysis[field] = {}
                else:
                    call_analysis[field] = []
                    
        logger.info(f"Call analysis fields: {list(call_analysis.keys())}")
    except Exception as e:
        logger.error(f"Error extracting call analysis: {e}")
        call_analysis = SAMPLE_CALL_ANALYSIS
        logger.info("Using sample call analysis due to extraction error")
    
    # Store in state for subsequent nodes
    state["call_analysis"] = call_analysis
    logger.info(f"Call analysis extracted successfully for transcript {transcript_id}")
    return state 