"""
LLM Utility — Retry wrapper and Pydantic validators for Gemini calls.

Fixes two Phase 1 weaknesses:
  1. No retry logic — a single rate-limit kills the whole arena
  2. No JSON validation — bad LLM output crashes downstream nodes

Usage:
    from llm_utils import call_gemini, RedActionSchema, BlueActionSchema
"""
import time
import json
import re
import sys
from pathlib import Path
from typing import Optional, Tuple, Any

from pydantic import BaseModel, field_validator, model_validator

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.llm_client import get_llm_client


def call_gemini(client, model: str, prompt: str, max_retries: int = 3) -> Optional[str]:
    llm_client = get_llm_client()
    return llm_client.call_gemini(prompt=prompt, max_retries=max_retries, model=model)


# ─────────────────────────────────────────────────────────────────────────────
# JSON Extraction
# ─────────────────────────────────────────────────────────────────────────────

def extract_json(text: str) -> Optional[dict]:
    """
    Safely extract a JSON object from LLM output.
    Handles: raw JSON, markdown fenced blocks, JSON embedded in prose.
    Returns None if extraction fails.
    """
    if not text:
        return None

    # Strip markdown code fences
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE)
    text = text.strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting first JSON object
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic Schemas — Validated LLM Output
# ─────────────────────────────────────────────────────────────────────────────

VALID_VULN_TYPES = {"cve", "rbac", "secret", "network", "privilege"}
VALID_DEFENSE_TYPES = {"rbac_patch", "secret_rotation", "network_policy", "pod_restart", "image_update"}


class RedActionSchema(BaseModel):
    """Validates Red Agent attack proposals from Gemini."""
    vuln_type: str
    target_namespace: str
    target_resource: str
    method: str
    rationale: str
    blast_radius: float
    chained_from: Optional[str] = None

    @field_validator("vuln_type")
    @classmethod
    def valid_vuln_type(cls, v: str) -> str:
        v = v.lower().strip()
        if "cve" in v:
            return "cve"
        if "secret" in v:
            return "secret"
        if "rbac" in v:
            return "rbac"
        if "net" in v or "policy" in v:
            return "network"
        if "priv" in v or "root" in v:
            return "privilege"
        return v if v in VALID_VULN_TYPES else "network"

    @field_validator("blast_radius")
    @classmethod
    def cap_blast_radius(cls, v: float) -> float:
        """OPA will block > 0.75 anyway, but we cap at 0.74 to avoid wasted rounds."""
        return round(min(max(float(v), 0.0), 0.74), 2)

    @field_validator("target_namespace", "target_resource", "method")
    @classmethod
    def non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Field cannot be empty")
        return v.strip()

    @classmethod
    def parse_llm_output(cls, text: str) -> Tuple[Optional["RedActionSchema"], bool]:
        """
        Parse and validate LLM output.
        Returns (schema, is_valid).
        If invalid, returns (None, False).
        """
        data = extract_json(text)
        if data is None:
            return None, False
        try:
            return cls(**data), True
        except Exception:
            return None, False


class BlueActionSchema(BaseModel):
    """Validates Blue Agent defense proposals from Gemini."""
    defense_type: str
    target_namespace: str
    target_resource: str
    method: str
    rationale: str
    pre_emptive: bool

    @field_validator("defense_type")
    @classmethod
    def valid_defense_type(cls, v: str) -> str:
        v = v.lower().strip()
        if "rbac" in v:
            return "rbac_patch"
        if "secret" in v:
            return "secret_rotation"
        if "net" in v or "policy" in v:
            return "network_policy"
        if "restart" in v or "priv" in v:
            return "pod_restart"
        if "image" in v or "update" in v or "cve" in v:
            return "image_update"
        return v if v in VALID_DEFENSE_TYPES else "rbac_patch"

    @field_validator("target_namespace", "target_resource", "method")
    @classmethod
    def non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Field cannot be empty")
        return v.strip()

    @classmethod
    def parse_llm_output(cls, text: str) -> Tuple[Optional["BlueActionSchema"], bool]:
        data = extract_json(text)
        if data is None:
            return None, False
        try:
            return cls(**data), True
        except Exception:
            return None, False


class PurpleActionSchema(BaseModel):
    pattern_synthesis: str
    blind_spots: str
    recommended_defense_type: str
    recommended_target_namespace: str
    recommended_target_resource: str
    recommendation_rationale: str

    @field_validator("recommended_defense_type")
    @classmethod
    def valid_defense_type(cls, v: str) -> str:
        v = v.lower().strip()
        if "rbac" in v:
            return "rbac_patch"
        if "secret" in v:
            return "secret_rotation"
        if "net" in v or "policy" in v:
            return "network_policy"
        if "restart" in v or "priv" in v:
            return "pod_restart"
        if "image" in v or "update" in v or "cve" in v:
            return "image_update"
        return v if v in VALID_DEFENSE_TYPES else "rbac_patch"

    @field_validator("recommended_target_namespace", "recommended_target_resource")
    @classmethod
    def non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Field cannot be empty")
        return v.strip()

    @classmethod
    def parse_llm_output(cls, text: str) -> Tuple[Optional["PurpleActionSchema"], bool]:
        data = extract_json(text)
        if data is None:
            return None, False
        try:
            return cls(**data), True
        except Exception:
            return None, False
