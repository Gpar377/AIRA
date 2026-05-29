"""
AIRA formatting_templates.py — Phase 3 SFT Dataset Prep
======================================================
Defines domain-agnostic system prompts, observations schemas,
and ChatML SFT formatting helpers.

Supports:
  - Domain v1 (Kubernetes): resource URIs like k8s://namespace/pod
  - Domain v2 (Web/App): resource URIs like web://domain/endpoint
  - Domain v3 (Network): resource URIs like net://ip-address/port
"""
from typing import Dict, Any, List

# ─────────────────────────────────────────────────────────────────────────────
# 1. System Prompt for AIRA Fine-tuning
# ─────────────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = (
    "You are AIRA (Autonomous Infrastructure Resilience Architecture), a domain-agnostic "
    "cybersecurity and site-reliability intelligence system. Your goal is to analyze the "
    "target state, reason about security threats or reliability anomalies, and execute precise "
    "remediation tools governed by safety policies.\n\n"
    "Available Domains:\n"
    "  - k8s (Kubernetes): resource URIs like k8s://namespace/pod-name\n"
    "  - web_app (Web/App Security): resource URIs like web://domain/endpoint\n"
    "  - network (Network Security): resource URIs like net://ip-address/port\n\n"
    "For every input, you must first reason thoroughly about the state, anomalies, CVE severity, "
    "or telemetry precursor spikes in a <thought>...</thought> block. Then, output your selected "
    "action in a structured JSON code block matching this format:\n\n"
    "```json\n"
    "{\n"
    "  \"action_type\": \"<action_name>\",\n"
    "  \"target_resource\": \"<domain://resource-uri>\",\n"
    "  \"parameters\": { ... }\n"
    "}\n"
    "```\n\n"
    "Keep reasoning humble, realistic, and focused strictly on the provided observations."
)

# ─────────────────────────────────────────────────────────────────────────────
# 2. Template formatters for observations (User Prompt)
# ─────────────────────────────────────────────────────────────────────────────

def format_user_prompt(domain: str, target: str, observations: List[str], past_actions: List[str] = None) -> str:
    """Constructs a clean, structured user observation prompt."""
    past = past_actions or ["none"]
    obs_lines = "\n".join(f"- {o}" for o in observations)
    past_lines = "\n".join(f"- {p}" for p in past)
    
    return (
        f"DOMAIN: {domain}\n"
        f"TARGET: {target}\n\n"
        f"OBSERVATIONS:\n{obs_lines}\n\n"
        f"PAST ACTIONS:\n{past_lines}\n\n"
        f"What action will you take?"
    )

def format_assistant_response(reasoning: str, action_type: str, target_resource: str, parameters: Dict[str, Any]) -> str:
    """Constructs the standard expected assistant response with JSON wrapper."""
    import json
    action_json = {
        "action_type": action_type,
        "target_resource": target_resource,
        "parameters": parameters
    }
    action_block = json.dumps(action_json, indent=2)
    return (
        f"<thought>\n{reasoning.strip()}\n</thought>\n"
        f"```json\n{action_block}\n```"
    )

# ─────────────────────────────────────────────────────────────────────────────
# 3. ChatML / SFT message builder
# ─────────────────────────────────────────────────────────────────────────────

def build_chatml_sample(
    domain: str,
    target: str,
    observations: List[str],
    reasoning: str,
    action_type: str,
    target_resource: str,
    parameters: Dict[str, Any],
    past_actions: List[str] = None
) -> Dict[str, Any]:
    """
    Compiles a complete instruction sample ready for HuggingFace SFT loaders.
    
    Note for Gemma 4 SFT Training:
    Instead of hardcoding a raw text chat template string (which changed between Gemma 2 and 4),
    this function outputs a structured messages list. SFTTrainer automatically applies the 
    tokenizer's built-in chat template dynamically:
        
        tokenizer = AutoTokenizer.from_pretrained("google/gemma-4-e4b-it")
        formatted = tokenizer.apply_chat_template(messages, tokenize=False)
    """
    user_content = format_user_prompt(domain, target, observations, past_actions)
    assistant_content = format_assistant_response(reasoning, action_type, target_resource, parameters)
    
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": assistant_content}
        ]
    }
