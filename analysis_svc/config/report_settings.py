#!/usr/bin/env python3
"""
Configurações para personalização de relatórios de vendas.

Este arquivo contém configurações que permitem personalizar o formato,
conteúdo e estilo dos relatórios de vendas gerados pelo sistema.
"""

from typing import Dict, Any, List

# Definição dos modelos de LLM a serem usados para cada etapa do relatório
LLM_MODELS = {
    # Modelo utilizado para a análise inicial da transcrição
    "analysis": "gpt-4o-mini",
    
    # Modelo utilizado para a geração do relatório estratégico final
    "report": "gpt-4o"
}

# Configurações para a geração do relatório
REPORT_SETTINGS = {
    # Quantidade de tokens máxima para o relatório final
    "max_tokens": 4000,
    
    # Temperatura para o LLM ao gerar o relatório (0.0 a 1.0)
    # - Valores mais baixos: mais consistente, determinístico
    # - Valores mais altos: mais criativo, variado
    "temperature": 0.2,
    
    # Nível de detalhe do relatório (1-5)
    # 1: Resumido, 3: Equilibrado, 5: Altamente detalhado
    "detail_level": 3,
    
    # Seções a incluir no relatório (True: incluir, False: omitir)
    "sections": {
        "executive_summary": True,
        "situation_diagnosis": True,
        "bant_analysis": True,
        "stakeholders_map": True,
        "value_proposition": True,
        "engagement_plan": True,
        "resources": True,
        "implementation_timeline": True
    }
}

# Configurações para personalização visual do relatório
STYLE_SETTINGS = {
    # Cor principal usada nos elementos de destaque (títulos, bordas)
    "primary_color": "#7158e2",
    
    # Cor secundária para elementos complementares
    "secondary_color": "#f5f7ff",
    
    # Fonte principal para o relatório
    "font_family": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif",
    
    # Incluir logotipo da empresa no relatório
    "include_logo": False,
    
    # URL do logotipo (se include_logo = True)
    "logo_url": "",
    
    # Incluir informações de rodapé
    "include_footer": True,
    
    # Texto de rodapé (se include_footer = True)
    "footer_text": "Relatório gerado automaticamente com base na análise de dados da reunião, LinkedIn e website."
}

# Personalização específica para diferentes tipos de clientes
CLIENT_SPECIFIC = {
    # Configurações para empresas de tecnologia
    "tech": {
        "focus_areas": ["inovação", "escalabilidade", "integração", "automação"],
        "terminology": ["API", "cloud", "microserviços", "DevOps", "IA", "machine learning"]
    },
    
    # Configurações para empresas de manufatura
    "manufacturing": {
        "focus_areas": ["otimização de processos", "redução de custos", "controle de qualidade", "cadeia de suprimentos"],
        "terminology": ["lean", "just-in-time", "kaizen", "six sigma", "automação industrial"]
    },
    
    # Configurações para empresas de serviços financeiros
    "financial": {
        "focus_areas": ["segurança", "compliance", "análise de risco", "automação de processos"],
        "terminology": ["ROI", "TCO", "compliance", "regulamentação", "escalabilidade", "integração"]
    },
    
    # Configurações para empresas de logística
    "logistics": {
        "focus_areas": ["otimização de rotas", "gestão de frota", "rastreamento", "redução de custos operacionais"],
        "terminology": ["last mile", "rastreabilidade", "gestão de frota", "otimização", "IoT", "telemetria"]
    }
}

# Configurações para adequação a diferentes fases do funil de vendas
SALES_FUNNEL_STAGES = {
    "awareness": {
        "focus": "educacional",
        "call_to_action": "agendar demonstração inicial",
        "content_type": "informativo e introdutório"
    },
    "consideration": {
        "focus": "diferenciação competitiva",
        "call_to_action": "análise detalhada de necessidades",
        "content_type": "comparativo e detalhado"
    },
    "decision": {
        "focus": "valor específico e ROI",
        "call_to_action": "proposta comercial formal",
        "content_type": "específico e orientado a resultados"
    },
    "implementation": {
        "focus": "cronograma e plano de sucesso",
        "call_to_action": "iniciar implementação",
        "content_type": "técnico e processual"
    }
}

# Função para obter as configurações baseadas no tipo de cliente
def get_client_specific_settings(client_type: str) -> Dict[str, Any]:
    """
    Retorna configurações específicas para um determinado tipo de cliente.
    
    Args:
        client_type: O tipo de cliente (tech, manufacturing, financial, logistics)
        
    Returns:
        Um dicionário com as configurações específicas para o tipo de cliente
    """
    return CLIENT_SPECIFIC.get(client_type, {})

# Função para obter as configurações baseadas na fase do funil de vendas
def get_funnel_stage_settings(stage: str) -> Dict[str, Any]:
    """
    Retorna configurações para uma determinada fase do funil de vendas.
    
    Args:
        stage: A fase do funil de vendas (awareness, consideration, decision, implementation)
        
    Returns:
        Um dicionário com as configurações para a fase especificada
    """
    return SALES_FUNNEL_STAGES.get(stage, SALES_FUNNEL_STAGES["consideration"]) 