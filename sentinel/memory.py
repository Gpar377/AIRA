"""
Battle Memory (Unified Database Bridge) — Cross-round learning store for Red and Blue agents.
Delegates to core.unified_memory for robust database storage (PostgreSQL with SQLite fallback).
"""
import os
import sys
from typing import Dict, Any, List
from datetime import datetime
from pathlib import Path

# Add core and root directories to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.unified_memory import UnifiedMemoryStore

# Instantiate global DB unified memory store
_db_store = UnifiedMemoryStore()


def empty_memory() -> Dict[str, Any]:
    """Returns a fresh memory structure and initializes the arena run session in the database."""
    arena_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Initialize the run record in SQL
    return _db_store.init_arena_run(arena_id)


def load_memory() -> Dict[str, Any]:
    """Load the latest arena run from the database or start a new one if none exists."""
    recent_runs = _db_store.get_all_arena_runs(limit=1)
    if recent_runs:
        return recent_runs[0]
    return empty_memory()


def save_memory(memory: Dict[str, Any]) -> None:
    """
    Persist memory to disk/DB.
    In the unified DB schema, memory is already persisted immediately at round end by
    record_round(), making this a clean no-op.
    """
    pass


def record_round(
    memory: Dict[str, Any],
    round_num: int,
    attack: Dict[str, Any],
    defense: Dict[str, Any],
    score_before: float,
    score_after: float,
    opa_decision: str
) -> Dict[str, Any]:
    """Record a completed round to the SQL battle_rounds database table."""
    arena_id = memory.get("arena_id") or memory.get("id") or datetime.now().strftime("%Y%m%d_%H%M%S")
    return _db_store.record_battle_round(
        arena_id=arena_id,
        round_num=round_num,
        attack=attack,
        defense=defense,
        score_before=score_before,
        score_after=score_after,
        opa_decision=opa_decision
    )


def get_red_context(memory: Dict[str, Any]) -> str:
    """Retrieve formatted battle learning history context for Red Agent Gemini prompt."""
    arena_id = memory.get("arena_id") or memory.get("id")
    if not arena_id:
        return "No previous rounds. This is round 1 - scan everything."
    return _db_store.get_red_agent_context(arena_id)


def get_blue_context(memory: Dict[str, Any]) -> str:
    """Retrieve formatted battle learning history context for Blue Agent Gemini prompt."""
    arena_id = memory.get("arena_id") or memory.get("id")
    if not arena_id:
        return "No previous rounds. Start by hardening highest-severity vulnerabilities."
    return _db_store.get_blue_agent_context(arena_id)
