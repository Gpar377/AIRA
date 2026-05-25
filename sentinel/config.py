"""
SentinelArena Configuration
Loads all settings from .env file
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    MAX_ROUNDS: int = int(os.getenv("MAX_ROUNDS", "8"))
    SPIRAL_THRESHOLD: int = int(os.getenv("SPIRAL_THRESHOLD", "3"))
    BLAST_RADIUS_LIMIT: float = float(os.getenv("BLAST_RADIUS_LIMIT", "0.75"))
    RED_RATE_LIMIT: int = int(os.getenv("RED_RATE_LIMIT_PER_ROUND", "2"))
    MEMORY_FILE: str = os.getenv("MEMORY_FILE", "memory_store/battle_memory.json")

    def validate(self):
        if not self.GEMINI_API_KEY or self.GEMINI_API_KEY == "your_gemini_api_key_here":
            raise ValueError(
                "\n\n❌ GEMINI_API_KEY not set!\n"
                "1. Get a FREE key at: https://aistudio.google.com\n"
                "2. Copy .env.example to .env\n"
                "3. Paste your key in the .env file\n"
            )


settings = Settings()
