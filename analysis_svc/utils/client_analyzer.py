#!/usr/bin/env python3
"""
Utilitário para análise automática de clientes e estágio no funil de vendas.

Este módulo fornece funções para determinar automaticamente o tipo de empresa
e a fase do funil de vendas com base nos dados da transcrição, LinkedIn e website.
"""

import re
from typing import Dict, Any, Tuple, List, Optional
import logging

# Configurar logging
logger = logging.getLogger(__name__)

# Palavras-chave para detecção de indústria
INDUSTRY_KEYWORDS = {
    "tech": [
        "software", "tecnologia", "desenvolvimento", "programação", "api", "saas", 
        "cloud", "nuvem", "startup", "aplicativo", "app", "digital", "internet", 
        "tecnológica", "sistema", "plataforma", "marketplace", "e-commerce", 
        "devops", "big data", "agile", "tech", "machine learning", "ia", "ai", 
        "inteligência artificial", "blockchain", "desenvolvimento web"
    ],
    "manufacturing": [
        "manufatura", "fábrica", "produção", "linha de montagem", "industrial", 
        "indústria", "processo produtivo", "lean", "kaizen", "just-in-time", 
        "estoque", "matéria-prima", "produto final", "supply chain", "insumos", 
        "sensores", "automação industrial", "manutenção", "equipamentos", 
        "máquinas", "peças", "qualidade", "controle de qualidade", "six sigma"
    ],
    "financial": [
        "banco", "financeira", "financeiro", "fintech", "investimento", "crédito", 
        "empréstimo", "seguro", "securitização", "pagamento", "cartão", "capital", 
        "risco", "compliance", "regulação", "bancos", "seguros", "corretora", 
        "mercado financeiro", "câmbio", "finanças", "contabilidade", "contábil", 
        "patrimônio", "ativos", "passivos"
    ],
    "logistics": [
        "logística", "transporte", "entrega", "armazenagem", "armazém", "estoque", 
        "distribuição", "expedição", "carga", "caminhão", "frota", "rastreamento", 
        "shipping", "cadeia de suprimentos", "supply chain", "importação", "exportação", 
        "cross-docking", "fulfillment", "last mile", "logístico", "transportadora", 
        "modal", "rota", "malha logística", "operador logístico"
    ],
    "healthcare": [
        "saúde", "hospital", "médico", "clínica", "paciente", "tratamento", 
        "farmacêutica", "medicamento", "diagnóstico", "terapia", "laboratório", 
        "exame", "consulta", "telemedicina", "prontuário", "internação", "leito", 
        "healthtech", "assistencial", "plano de saúde", "operadora", "seguradora de saúde"
    ],
    "retail": [
        "varejo", "loja", "shopping", "atacado", "varejista", "comércio", "atacadista", 
        "consumidor", "cliente", "pdv", "ponto de venda", "merchandising", "prateleira", 
        "estoque", "inventário", "reposição", "venda", "compra", "revendedor", "franquia", 
        "rede", "omnichannel", "online", "offline", "marketplace"
    ],
    "education": [
        "educação", "escola", "ensino", "professor", "aluno", "estudante", "curso", 
        "faculdade", "universidade", "formação", "capacitação", "treinamento", "classe", 
        "acadêmico", "aula", "pedagógico", "edtech", "ead", "ensino a distância", 
        "material didático", "conteúdo"
    ]
}

# Palavras-chave para estágios do funil de vendas
FUNNEL_STAGE_KEYWORDS = {
    "awareness": [
        "conhecer", "aprender", "entender", "explorar", "descobrir", "informação", 
        "educação", "webinar", "demonstração inicial", "primeira reunião", 
        "ainda não sei", "estamos pesquisando", "analisando opções", "estamos começando", 
        "quero saber mais", "me interessei", "conhecer melhor"
    ],
    "consideration": [
        "comparando", "avaliando", "analisando", "concorrente", "alternativa", 
        "diferenças", "vantagens", "desvantagens", "preço", "funcionalidade", 
        "está no nosso radar", "estamos considerando", "quais são os diferenciais", 
        "comparativo", "teste", "prova de conceito", "poc", "piloto"
    ],
    "decision": [
        "decidir", "decidindo", "proposta", "contrato", "assinatura", "aprovação", 
        "investimento", "orçamento", "orçamentos", "aprovado", "roi", "retorno", 
        "prazo", "implementação", "implantação", "quando podemos começar", 
        "precisamos fechar até", "comitê", "decisores", "diretoria", "conselho"
    ],
    "implementation": [
        "implementar", "implementação", "implantação", "cronograma", "prazo", 
        "equipe técnica", "treinamento", "migração", "integração", "on-boarding", 
        "acompanhamento", "suporte", "já decidimos", "próximos passos", "go-live", 
        "plano de implantação", "projeto", "fases"
    ]
}

def detect_industry(text: str, company_data: Dict[str, Any]) -> str:
    """
    Detecta o tipo de indústria da empresa com base no texto e dados do site.
    
    Args:
        text: Texto da transcrição
        company_data: Dados coletados do site da empresa
        
    Returns:
        Tipo de indústria detectado (tech, manufacturing, etc.)
    """
    # Normalizar o texto para evitar problemas de case sensitivity
    text = text.lower()
    
    # Contadores para cada tipo de indústria
    counts = {industry: 0 for industry in INDUSTRY_KEYWORDS}
    
    # Contar ocorrências de palavras-chave no texto da transcrição
    for industry, keywords in INDUSTRY_KEYWORDS.items():
        for keyword in keywords:
            count = len(re.findall(r'\b' + re.escape(keyword) + r'\b', text))
            counts[industry] += count
    
    # Verificar dados da empresa para pistas adicionais
    if company_data and not company_data.get("error"):
        company_description = company_data.get("about", "")
        if company_description:
            company_text = company_description.lower()
            for industry, keywords in INDUSTRY_KEYWORDS.items():
                for keyword in keywords:
                    count = len(re.findall(r'\b' + re.escape(keyword) + r'\b', company_text))
                    counts[industry] += count * 2  # Dá mais peso às palavras-chave do site da empresa
    
    # Determinar a indústria com maior pontuação
    industry_scores = [(industry, count) for industry, count in counts.items()]
    industry_scores.sort(key=lambda x: x[1], reverse=True)
    
    logger.info(f"Industry scores: {industry_scores}")
    
    # Se não houver uma clara vencedora, retornar "general"
    if industry_scores[0][1] == 0 or (len(industry_scores) > 1 and industry_scores[0][1] == industry_scores[1][1]):
        return "general"
    
    return industry_scores[0][0]

def detect_funnel_stage(text: str, sales_data: Dict[str, Any]) -> str:
    """
    Detecta a fase do funil de vendas com base no texto e dados de vendas.
    
    Args:
        text: Texto da transcrição
        sales_data: Dados da análise de vendas
        
    Returns:
        Fase do funil detectada (awareness, consideration, decision, implementation)
    """
    # Normalizar o texto para evitar problemas de case sensitivity
    text = text.lower()
    
    # Contadores para cada estágio do funil
    counts = {stage: 0 for stage in FUNNEL_STAGE_KEYWORDS}
    
    # Contar ocorrências de palavras-chave no texto da transcrição
    for stage, keywords in FUNNEL_STAGE_KEYWORDS.items():
        for keyword in keywords:
            count = len(re.findall(r'\b' + re.escape(keyword) + r'\b', text))
            counts[stage] += count
    
    # Verificar dados BANT para pistas adicionais
    bant_data = sales_data.get('bant', {})
    
    # Timeline pode indicar a fase do funil
    timeline = bant_data.get('timeline', '').lower()
    if 'imediato' in timeline or 'urgente' in timeline or 'próxima semana' in timeline:
        counts['decision'] += 3
    elif 'próximo mês' in timeline or 'trimestre' in timeline:
        counts['consideration'] += 2
    elif 'estudo' in timeline or 'análise' in timeline or 'avaliação' in timeline:
        counts['awareness'] += 2
    elif 'implementação' in timeline or 'implantação' in timeline or 'roll-out' in timeline:
        counts['implementation'] += 3
    
    # Budget pode indicar a fase do funil
    budget = bant_data.get('budget', '').lower()
    if 'aprovado' in budget or 'disponível' in budget:
        counts['decision'] += 2
    elif 'alocado' in budget or 'reservado' in budget:
        counts['consideration'] += 2
    elif 'sem' in budget or 'não definido' in budget or 'ainda não' in budget:
        counts['awareness'] += 2
    
    # Authority pode indicar a fase do funil
    authority = bant_data.get('authority', '').lower()
    if 'ceo' in authority or 'diretor' in authority or 'comitê' in authority:
        counts['decision'] += 1
    
    # Determinar o estágio com maior pontuação
    stage_scores = [(stage, count) for stage, count in counts.items()]
    stage_scores.sort(key=lambda x: x[1], reverse=True)
    
    logger.info(f"Funnel stage scores: {stage_scores}")
    
    # Se não houver um claro vencedor, presumir "consideration"
    if stage_scores[0][1] == 0 or (len(stage_scores) > 1 and stage_scores[0][1] == stage_scores[1][1]):
        return "consideration"
    
    return stage_scores[0][0]

def analyze_client(
    transcript_text: str, 
    sales_data: Dict[str, Any], 
    company_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Analisa as características do cliente para personalização do relatório.
    
    Args:
        transcript_text: Texto da transcrição
        sales_data: Dados da análise de vendas
        company_data: Dados coletados do site da empresa
        
    Returns:
        Dicionário com o tipo de indústria e fase do funil de vendas
    """
    industry = detect_industry(transcript_text, company_data)
    funnel_stage = detect_funnel_stage(transcript_text, sales_data)
    
    logger.info(f"Client analysis results - Industry: {industry}, Funnel Stage: {funnel_stage}")
    
    return {
        "industry": industry,
        "funnel_stage": funnel_stage
    }

def extract_decision_criteria(
    transcript_text: str, 
    sales_data: Dict[str, Any]
) -> List[str]:
    """
    Extrai critérios de decisão mencionados pelo cliente.
    
    Args:
        transcript_text: Texto da transcrição
        sales_data: Dados da análise de vendas
        
    Returns:
        Lista de critérios de decisão identificados
    """
    # Critérios comuns de decisão a procurar
    criteria_keywords = [
        "critério", "critérios", "importante", "essencial", "fundamental", 
        "requisito", "necessário", "obrigatório", "prioridade", "decisivo", 
        "diferencial", "vantagem", "benefício", "preço", "custo", "valor", 
        "prazo", "tempo", "rapidez", "qualidade", "atendimento", "suporte", 
        "segurança", "confiança", "reputação", "garantia", "facilidade", 
        "experiência", "integração", "escalabilidade", "customização"
    ]
    
    decision_criteria = []
    
    # Procurar por menções diretas de critérios na transcrição
    for keyword in criteria_keywords:
        pattern = rf'\b{re.escape(keyword)}[^.!?]*(?:[.!?])'
        matches = re.findall(pattern, transcript_text, re.IGNORECASE)
        for match in matches:
            if len(match) > 10:  # Ignorar correspondências muito curtas
                decision_criteria.append(match.strip())
    
    # Deduzir critérios implícitos das dores e necessidades
    pain_points = sales_data.get('dores', [])
    needs = sales_data.get('spin', {}).get('necessidade', '')
    
    # Extrair frases com critérios implícitos das dores
    for pain in pain_points:
        if any(keyword in pain.lower() for keyword in ["precisamos", "necessitamos", "queremos", "buscamos"]):
            decision_criteria.append(f"Resolver: {pain}")
    
    # Extrair critérios da seção de necessidades
    if needs:
        needs_sentences = re.split(r'[.!?]', needs)
        for sentence in needs_sentences:
            if any(keyword in sentence.lower() for keyword in ["precisa", "necessita", "quer", "busca", "fundamental", "crucial"]):
                decision_criteria.append(f"Necessidade: {sentence.strip()}")
    
    # Remover duplicatas
    decision_criteria = list(set(decision_criteria))
    
    return decision_criteria

def identify_value_drivers(
    sales_data: Dict[str, Any], 
    industry: str
) -> Dict[str, List[str]]:
    """
    Identifica os principais impulsionadores de valor para o cliente.
    
    Args:
        sales_data: Dados da análise de vendas
        industry: Tipo de indústria do cliente
        
    Returns:
        Dicionário com categorias de impulsionadores de valor
    """
    # Possíveis categorias de impulsionadores de valor
    value_categories = {
        "financeiro": [],
        "operacional": [],
        "estratégico": [],
        "risco": []
    }
    
    # Mapear dores para categorias de valor
    pain_points = sales_data.get('dores', [])
    
    # Palavras-chave financeiras
    financial_keywords = ["custo", "preço", "orçamento", "gasto", "despesa", "investimento", 
                          "economia", "retorno", "lucro", "margem", "receita", "financeiro", 
                          "roi", "payback", "redução de custo"]
    
    # Palavras-chave operacionais
    operational_keywords = ["processo", "eficiência", "produtividade", "operação", "tempo", 
                            "velocidade", "agilidade", "automação", "manual", "retrabalho", 
                            "fluxo", "workflow", "integração"]
    
    # Palavras-chave estratégicas
    strategic_keywords = ["crescimento", "expansão", "mercado", "competitividade", "inovação", 
                          "diferenciação", "posicionamento", "vantagem", "competidor", "cliente", 
                          "estratégia", "futuro", "tendência"]
    
    # Palavras-chave de risco
    risk_keywords = ["risco", "segurança", "compliance", "conformidade", "regulação", "lei", 
                     "vulnerabilidade", "exposição", "falha", "erro", "multa", "penalidade", 
                     "problema", "perda"]
    
    # Categorizar cada dor
    for pain in pain_points:
        pain_lower = pain.lower()
        
        # Verificar categoria financeira
        if any(keyword in pain_lower for keyword in financial_keywords):
            value_categories["financeiro"].append(pain)
        
        # Verificar categoria operacional
        if any(keyword in pain_lower for keyword in operational_keywords):
            value_categories["operacional"].append(pain)
        
        # Verificar categoria estratégica
        if any(keyword in pain_lower for keyword in strategic_keywords):
            value_categories["estratégico"].append(pain)
        
        # Verificar categoria de risco
        if any(keyword in pain_lower for keyword in risk_keywords):
            value_categories["risco"].append(pain)
    
    # Para cada categoria vazia, tente inferir possíveis impulsionadores de valor
    # com base no tipo de indústria e dados SPIN
    spin_data = sales_data.get('spin', {})
    
    if not value_categories["financeiro"]:
        if industry == "logistics":
            value_categories["financeiro"].append("Redução de custos operacionais na gestão de frotas")
        elif industry == "tech":
            value_categories["financeiro"].append("Otimização de investimentos em tecnologia")
    
    if not value_categories["operacional"]:
        if "operacional" in spin_data.get('problema', '').lower() or "processo" in spin_data.get('problema', '').lower():
            value_categories["operacional"].append(f"Melhoria de processos relacionados a {spin_data.get('problema')}")
    
    if not value_categories["estratégico"]:
        if "competidor" in spin_data.get('implicacao', '').lower() or "mercado" in spin_data.get('implicacao', '').lower():
            value_categories["estratégico"].append("Fortalecimento da posição competitiva no mercado")
    
    if not value_categories["risco"]:
        if "falha" in spin_data.get('implicacao', '').lower() or "problema" in spin_data.get('implicacao', '').lower():
            value_categories["risco"].append("Mitigação de riscos operacionais e de conformidade")
    
    return value_categories 