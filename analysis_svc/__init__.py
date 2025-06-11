"""
Analysis service package for sales intelligence.

This package contains all the analysis services for sales intelligence,
including SPIN and BANT analysis, lead scoring, and report generation.
"""

__version__ = "1.0.0"

# Import core functionality to make it easily accessible
from analysis_svc.pipeline import run_analysis_pipeline, run_enrichment_pipeline
from analysis_svc import nodes
from analysis_svc.nodes import extract_call_analysis_node

# Utility modules
from analysis_svc.utils.client_analyzer import (
    analyze_client,
    detect_industry,
    detect_funnel_stage,
    extract_decision_criteria,
    identify_value_drivers
)

# Configuration
from analysis_svc.config.report_settings import (
    LLM_MODELS,
    REPORT_SETTINGS,
    STYLE_SETTINGS,
    CLIENT_SPECIFIC,
    SALES_FUNNEL_STAGES,
    get_client_specific_settings,
    get_funnel_stage_settings
) 