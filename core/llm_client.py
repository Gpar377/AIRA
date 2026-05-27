"""
Unified LLM Client — Single shared AI client for AIRA (both Sentinel & NeuralOps).
Implements the google-genai SDK wrapper, exponential backoff retries,
and safely parses structured Pydantic schemas.
"""
import time
import json
import re
import os
import sys
from pathlib import Path
from typing import Optional, Type, Tuple, TypeVar, Any
from pydantic import BaseModel
import structlog
from google import genai
from google.genai import types

# Allow importing from AIRA root
sys.path.insert(0, str(Path(__file__).parent.parent))

from neuralops.config import settings as neuralops_settings
from sentinel.config import settings as sentinel_settings

logger = structlog.get_logger()

# Type variable for Pydantic Schema returning
T = TypeVar('T', bound=BaseModel)


class AIRALLMClient:
    """Unified client manager for interacting with Gemini/Gemma models."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        default_model: Optional[str] = None,
        temperature: float = 0.0
    ):
        # Resolve backend: gemini or ollama
        self.backend = os.getenv("AIRA_LLM_BACKEND", "gemini").lower()
        
        # Resolve key and model from available settings sources
        self.api_key = api_key or sentinel_settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY", "")
        self.model = default_model or sentinel_settings.GEMINI_MODEL or "gemini-2.0-flash"
        self.temperature = temperature
        
        if self.backend == "ollama":
            self.model = os.getenv("OLLAMA_MODEL", "aira-gemma")
            logger.info("unified_llm_client_initialized_ollama_backend", model=self.model, url=os.getenv("OLLAMA_URL", "http://localhost:11434"))
            self.client = None
        else:
            # Instantiate Google GenAI client if key is present
            if self.api_key:
                self.client = genai.Client(api_key=self.api_key)
                logger.info("unified_llm_client_initialized_gemini_backend", model=self.model)
            else:
                self.client = None
                logger.warning("unified_llm_client_missing_api_key", model=self.model)

    def call_ollama(
        self,
        prompt: str,
        max_retries: int = 3,
        model: Optional[str] = None,
        temperature: Optional[float] = None
    ) -> Optional[str]:
        """Call local Ollama instance over HTTP with exponential backoff."""
        target_model = model or os.getenv("OLLAMA_MODEL", "aira-gemma")
        ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        temp = temperature if temperature is not None else self.temperature
        
        payload = {
            "model": target_model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "stream": False,
            "options": {
                "temperature": temp
            }
        }
        
        import httpx
        last_error = None
        for attempt in range(max_retries):
            try:
                response = httpx.post(
                    f"{ollama_url}/api/chat",
                    json=payload,
                    timeout=90.0
                )
                if response.status_code == 200:
                    resp_json = response.json()
                    return resp_json.get("message", {}).get("content", "")
                else:
                    last_error = f"Ollama API returned status {response.status_code}: {response.text}"
                    logger.warning("ollama_call_failed", attempt=attempt+1, error=last_error)
            except Exception as e:
                last_error = str(e)
                logger.warning("ollama_call_retry_triggered", attempt=attempt+1, error=last_error)
                
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                time.sleep(wait)
                
        logger.error("ollama_call_exhausted_retries", error=last_error)
        return None

    def call_gemini(
        self,
        prompt: str,
        max_retries: int = 3,
        model: Optional[str] = None,
        temperature: Optional[float] = None
    ) -> Optional[str]:
        """
        Callconfigured LLM backend (Gemini or local Ollama) with exponential backoff.
        
        Returns:
            String response content, or None if client/retries fail.
        """
        if self.backend == "ollama":
            return self.call_ollama(prompt, max_retries, model, temperature)

        if not self.client:
            logger.warning("llm_call_skipped_no_client")
            return None
            
        target_model = model or self.model
        temp = temperature if temperature is not None else self.temperature
        
        config = types.GenerateContentConfig(
            temperature=temp
        )
        
        last_error = None
        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model=target_model,
                    contents=prompt,
                    config=config
                )
                return response.text
            except Exception as e:
                last_error = e
                logger.warn("llm_call_retry_triggered", attempt=attempt+1, error=str(e))
                if attempt < max_retries - 1:
                    wait = 2 ** attempt  # 1, 2, 4 seconds
                    time.sleep(wait)
                    
        logger.error("llm_call_exhausted_retries", error=str(last_error))
        return None

    def call_gemini_structured(
        self,
        prompt: str,
        schema: Type[T],
        max_retries: int = 3,
        model: Optional[str] = None
    ) -> Tuple[T, bool]:
        """
        Call Gemini and strictly parse the output into a Pydantic Schema model.
        
        Returns:
            Tuple: (Parsed Pydantic instance, IsValid Boolean)
        """
        # Append instruction ensuring LLM returns valid JSON matching the schema
        schema_fields = schema.model_fields.keys()
        formatted_prompt = (
            f"{prompt}\n\n"
            f"IMPORTANT: You MUST respond ONLY with a raw JSON object containing these keys: "
            f"{', '.join(schema_fields)}. "
            f"Do not wrap in markdown syntax, do not include explainers."
        )
        
        response_text = self.call_gemini(
            prompt=formatted_prompt,
            max_retries=max_retries,
            model=model
        )
        
        if not response_text:
            return schema(), False
            
        parsed_dict = self.extract_json(response_text)
        if parsed_dict is None:
            return schema(), False
            
        try:
            return schema(**parsed_dict), True
        except Exception as e:
            logger.error("llm_structured_parse_failed", error=str(e))
            return schema(), False

    @staticmethod
    def extract_json(text: str) -> Optional[dict]:
        """Safely extract and load a JSON dictionary block from the raw LLM output text."""
        if not text:
            return None

        # Clean standard Markdown JSON delimiters if present
        cleaned = re.sub(r"```(?:json)?\s*", "", text)
        cleaned = re.sub(r"```\s*$", "", cleaned, flags=re.MULTILINE)
        cleaned = cleaned.strip()

        # Direct JSON load try
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # Target first bracket match as fallback
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        return None


# Global llm client instance
_llm_client_instance = None


def get_llm_client() -> AIRALLMClient:
    """Retrieve the global singleton instance of the LLM Client."""
    global _llm_client_instance
    if _llm_client_instance is None:
        _llm_client_instance = AIRALLMClient()
    return _llm_client_instance
