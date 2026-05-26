"""
Unified Memory Store — SQLAlchemy Models and Service for SentinelArena & NeuralOps.
Bridges battle memory and system incidents in one PostgreSQL schema.
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, Text, Boolean, ForeignKey, desc
from sqlalchemy.orm import relationship
from datetime import datetime
from typing import Dict, Any, List, Optional
import structlog

from core.db import Base, get_core_database

logger = structlog.get_logger()


# ─────────────────────────────────────────────────────────────────────────────
# 1. SentinelArena Models
# ─────────────────────────────────────────────────────────────────────────────

class ArenaRun(Base):
    """Represents a single cross-agent security battle run (SentinelArena)."""
    __tablename__ = "arena_runs"
    
    id = Column(String(50), primary_key=True)  # Format: YYYYMMDD_HHMMSS
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Aggregated learning arrays (stored as JSON arrays of strings)
    red_learned = Column(JSON, default=list, nullable=False)
    blue_learned = Column(JSON, default=list, nullable=False)
    patched_resources = Column(JSON, default=list, nullable=False)
    attempted_attacks = Column(JSON, default=list, nullable=False)
    successful_attacks = Column(JSON, default=list, nullable=False)
    
    # Score tracking over rounds (JSON timeline)
    score_timeline = Column(JSON, default=list, nullable=False)
    
    # Relationships
    rounds = relationship("BattleRound", back_populates="arena", cascade="all, delete-orphan")
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "arena_id": self.id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "red_learned": self.red_learned,
            "blue_learned": self.blue_learned,
            "patched_resources": self.patched_resources,
            "attempted_attacks": self.attempted_attacks,
            "successful_attacks": self.successful_attacks,
            "score_timeline": self.score_timeline,
        }


class BattleRound(Base):
    """Represents a single round of battle within a SentinelArena execution."""
    __tablename__ = "battle_rounds"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    arena_id = Column(String(50), ForeignKey("arena_runs.id"), nullable=False, index=True)
    round_number = Column(Integer, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Attack Agent Details
    attack_type = Column(String(100))
    attack_target = Column(String(255))
    attack_method = Column(Text)
    attack_outcome = Column(String(50))
    
    # OPA Governance Decision
    opa_decision = Column(String(50))
    
    # Defense Agent Details
    defense_type = Column(String(100))
    defense_target = Column(String(255))
    defense_method = Column(Text)
    defense_outcome = Column(String(50))
    defense_score_delta = Column(Float, default=0.0)
    
    # Overall Scores
    score_before = Column(Float)
    score_after = Column(Float)
    score_delta = Column(Float)
    
    # Relationships
    arena = relationship("ArenaRun", back_populates="rounds")
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "round": self.round_number,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "attack": {
                "type": self.attack_type,
                "target": self.attack_target,
                "method": self.attack_method,
                "opa_decision": self.opa_decision,
                "outcome": self.attack_outcome,
            },
            "defense": {
                "type": self.defense_type,
                "target": self.defense_target,
                "method": self.defense_method,
                "outcome": self.defense_outcome,
                "score_delta": self.defense_score_delta,
            },
            "score_before": self.score_before,
            "score_after": self.score_after,
            "score_delta": self.score_delta,
        }


# ─────────────────────────────────────────────────────────────────────────────
# 2. Unified Memory Service
# ─────────────────────────────────────────────────────────────────────────────

class UnifiedMemoryStore:
    """Core memory database service combining Sentinel battle logic and hooks for NeuralOps."""
    
    def __init__(self):
        self.db = get_core_database()
        
    # ── Arena Initialization & Management ───────────────────────────────
    
    def init_arena_run(self, arena_id: Optional[str] = None) -> Dict[str, Any]:
        """Start a new arena run session and create its record in the database."""
        aid = arena_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        with self.db.get_session() as session:
            existing = session.query(ArenaRun).filter(ArenaRun.id == aid).first()
            if not existing:
                run = ArenaRun(
                    id=aid,
                    created_at=datetime.utcnow(),
                    red_learned=[],
                    blue_learned=[],
                    patched_resources=[],
                    attempted_attacks=[],
                    successful_attacks=[],
                    score_timeline=[]
                )
                session.add(run)
                logger.info("arena_run_db_initialized", arena_id=aid)
                return run.to_dict()
            return existing.to_dict()

    def record_battle_round(
        self,
        arena_id: str,
        round_num: int,
        attack: Dict[str, Any],
        defense: Dict[str, Any],
        score_before: float,
        score_after: float,
        opa_decision: str
    ) -> Dict[str, Any]:
        """Record a round of combat and update the cross-round aggregate learnings in the database."""
        with self.db.get_session() as session:
            # 1. Fetch current Arena run state
            arena = session.query(ArenaRun).filter(ArenaRun.id == arena_id).first()
            if not arena:
                arena = ArenaRun(
                    id=arena_id,
                    created_at=datetime.utcnow(),
                    red_learned=[],
                    blue_learned=[],
                    patched_resources=[],
                    attempted_attacks=[],
                    successful_attacks=[],
                    score_timeline=[]
                )
                session.add(arena)
                session.flush()

            # 2. Extract values for round table entry
            attack_target = f"{attack.get('target_namespace')}/{attack.get('target_resource')}"
            defense_target = f"{defense.get('target_namespace')}/{defense.get('target_resource')}"
            
            battle_round = BattleRound(
                arena_id=arena_id,
                round_number=round_num,
                timestamp=datetime.utcnow(),
                attack_type=attack.get("vuln_type", "unknown"),
                attack_target=attack_target,
                attack_method=attack.get("method", ""),
                attack_outcome=attack.get("outcome", "unknown"),
                opa_decision=opa_decision,
                defense_type=defense.get("defense_type", "unknown"),
                defense_target=defense_target,
                defense_method=defense.get("method", ""),
                defense_outcome=defense.get("outcome", "unknown"),
                defense_score_delta=defense.get("score_delta", 0.0),
                score_before=score_before,
                score_after=score_after,
                score_delta=round(score_after - score_before, 2)
            )
            session.add(battle_round)

            # 3. Update mutable JSON lists locally
            red_learned = list(arena.red_learned)
            blue_learned = list(arena.blue_learned)
            patched_resources = list(arena.patched_resources)
            attempted_attacks = list(arena.attempted_attacks)
            successful_attacks = list(arena.successful_attacks)
            score_timeline = list(arena.score_timeline)

            # Red learned patterns (avoid blocked/OPA rules)
            if attack.get("outcome") in ("blocked_opa", "blocked_blue"):
                avoid_str = f"AVOID: {attack_target} - {attack.get('outcome')}"
                if avoid_str not in red_learned:
                    red_learned.append(avoid_str)

            # Blue patched resources
            if defense.get("outcome") == "success":
                if defense_target not in patched_resources:
                    patched_resources.append(defense_target)

            # Attempted and successful attack lists
            attack_type = attack.get("vuln_type", "unknown")
            if attack_type not in attempted_attacks:
                attempted_attacks.append(attack_type)

            if attack.get("outcome") == "success":
                if attack_target not in successful_attacks:
                    successful_attacks.append(attack_target)

            # Blue learned watch lists
            watch_str = f"Red targets {attack_type} - watch: {attack_target}"
            if not any(attack_target in item for item in blue_learned):
                blue_learned.append(watch_str)

            # Record core score timeline
            score_timeline.append({
                "round": round_num,
                "score": score_after
            })

            # Save arrays back to force SQLAlchemy JSON detection
            arena.red_learned = red_learned
            arena.blue_learned = blue_learned
            arena.patched_resources = patched_resources
            arena.attempted_attacks = attempted_attacks
            arena.successful_attacks = successful_attacks
            arena.score_timeline = score_timeline
            
            logger.info("battle_round_db_recorded", arena_id=arena_id, round=round_num)
            
            return {
                "arena_id": arena.id,
                "red_learned": red_learned,
                "blue_learned": blue_learned,
                "patched_resources": patched_resources,
                "attempted_attacks": attempted_attacks,
                "successful_attacks": successful_attacks,
                "score_timeline": score_timeline
            }

    # ── Agent Context Generation ───────────────────────────────────────
    
    def get_red_agent_context(self, arena_id: str) -> str:
        """Fetch database battle logs and format as dynamic context string for Red Agent prompting."""
        with self.db.get_session() as session:
            arena = session.query(ArenaRun).filter(ArenaRun.id == arena_id).first()
            if not arena or not arena.rounds:
                return "No previous rounds. This is round 1 - scan everything."
            
            lines = [
                f"=== RED AGENT UNIFIED DATABASE MEMORY ({len(arena.rounds)} previous rounds) ===",
                "",
                "THINGS TO AVOID (already patched or blocked):",
            ]
            for item in arena.red_learned[-10:]:
                lines.append(f"  - {item}")
                
            lines.append("")
            lines.append("ATTACK TYPES ALREADY TRIED:")
            for t in arena.attempted_attacks:
                lines.append(f"  - {t}")
                
            lines.append("")
            lines.append("SUCCESSFUL ATTACKS (build on these):")
            for t in arena.successful_attacks[-5:]:
                lines.append(f"  - {t}")
                
            lines.append("")
            lines.append("SCORE TREND (attack surface exposure):")
            for s in arena.score_timeline[-5:]:
                lines.append(f"  Round {s['round']}: {s['score']}")
                
            lines.append("")
            lines.append("STRATEGY HINT: Focus on unpatched resources. Chain vulnerabilities.")
            lines.append("If a resource was patched, find a new vector.")
            
            return "\n".join(lines)

    def get_blue_agent_context(self, arena_id: str) -> str:
        """Fetch database battle logs and format as dynamic context string for Blue Agent prompting."""
        with self.db.get_session() as session:
            arena = session.query(ArenaRun).filter(ArenaRun.id == arena_id).first()
            if not arena or not arena.rounds:
                return "No previous rounds. Start by hardening highest-severity vulnerabilities."
                
            lines = [
                f"=== BLUE AGENT UNIFIED DATABASE MEMORY ({len(arena.rounds)} previous rounds) ===",
                "",
                "RED AGENT ATTACK PATTERNS (what to expect):",
            ]
            for item in arena.blue_learned[-10:]:
                lines.append(f"  - {item}")
                
            lines.append("")
            lines.append("RESOURCES ALREADY PATCHED (don't re-patch):")
            for r in arena.patched_resources[-10:]:
                lines.append(f"  [OK] {r}")
                
            # Details of last round
            last_round = session.query(BattleRound).filter(BattleRound.arena_id == arena_id).order_by(desc(BattleRound.round_number)).first()
            if last_round:
                lines.append("")
                lines.append("LAST ROUND OUTCOME:")
                lines.append(f"  Attack: {last_round.attack_type} -> {last_round.attack_outcome}")
                lines.append(f"  Your defense: {last_round.defense_type} -> {last_round.defense_outcome}")
                lines.append(f"  Score change: {last_round.score_before} -> {last_round.score_after} ({last_round.score_delta:+.1f})")
                
            lines.append("")
            lines.append("STRATEGY HINT: Pre-harden resources Red hasn't hit yet.")
            lines.append("Focus on CRITICAL severity vulnerabilities first.")
            
            return "\n".join(lines)

    # ── History Queries (for Dashboard) ──────────────────────────────────
    
    def get_all_arena_runs(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetch recent Arena runs and return their schema structure."""
        with self.db.get_session() as session:
            runs = session.query(ArenaRun).order_by(desc(ArenaRun.created_at)).limit(limit).all()
            return [r.to_dict() for r in runs]
            
    def get_arena_rounds(self, arena_id: str) -> List[Dict[str, Any]]:
        """Fetch all individual rounds for an Arena session."""
        with self.db.get_session() as session:
            rounds = session.query(BattleRound).filter(BattleRound.arena_id == arena_id).order_by(BattleRound.round_number).all()
            return [r.to_dict() for r in rounds]
