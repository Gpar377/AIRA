"""
Battle Memory — Cross-round learning store for Red and Blue agents.
This is what makes the system genuinely adaptive rather than just a loop.

Red reads Blue's patches → avoids already-hardened resources.
Blue reads Red's history → pre-hardens resources Red is likely to target next.

Stored as a structured JSON file that persists across arena runs.
"""
import json
import os
from typing import Dict, Any, List
from datetime import datetime

from config import settings


# ─────────────────────────────────────────────────────────────────────────────
# Memory Structure
# ─────────────────────────────────────────────────────────────────────────────

def empty_memory() -> Dict[str, Any]:
    """Returns a fresh memory structure for a new arena run."""
    return {
        "arena_id": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "created_at": datetime.now().isoformat(),
        "rounds": [],
        "red_learned": [],     # What Red knows to avoid
        "blue_learned": [],    # What Blue knows Red targets
        "patched_resources": [],    # Resources Blue has hardened
        "attempted_attacks": [],    # All attack types Red has tried
        "successful_attacks": [],   # Attacks that got through
        "score_timeline": [],       # Attack surface score per round
    }


# ─────────────────────────────────────────────────────────────────────────────
# Load / Save
# ─────────────────────────────────────────────────────────────────────────────

def load_memory() -> Dict[str, Any]:
    """Load existing memory from disk, or return fresh memory."""
    path = settings.MEMORY_FILE
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                data = json.load(f)
                # If memory is from a previous run, start fresh but keep cross-run learnings
                return data
        except (json.JSONDecodeError, IOError):
            pass
    return empty_memory()


def save_memory(memory: Dict[str, Any]) -> None:
    """Persist memory to disk."""
    path = settings.MEMORY_FILE
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(memory, f, indent=2)


# ─────────────────────────────────────────────────────────────────────────────
# Memory Update Functions
# ─────────────────────────────────────────────────────────────────────────────

def record_round(memory: Dict[str, Any],
                 round_num: int,
                 attack: Dict[str, Any],
                 defense: Dict[str, Any],
                 score_before: float,
                 score_after: float,
                 opa_decision: str) -> Dict[str, Any]:
    """Record a completed round into memory."""

    round_record = {
        "round": round_num,
        "timestamp": datetime.now().isoformat(),
        "attack": {
            "type": attack.get("vuln_type", "unknown"),
            "target": f"{attack.get('target_namespace')}/{attack.get('target_resource')}",
            "method": attack.get("method", ""),
            "opa_decision": opa_decision,
            "outcome": attack.get("outcome", "unknown"),
        },
        "defense": {
            "type": defense.get("defense_type", "unknown"),
            "target": f"{defense.get('target_namespace')}/{defense.get('target_resource')}",
            "method": defense.get("method", ""),
            "pre_emptive": defense.get("pre_emptive", False),
            "outcome": defense.get("outcome", "unknown"),
            "score_delta": defense.get("score_delta", 0.0),
        },
        "score_before": score_before,
        "score_after": score_after,
        "score_delta": round(score_after - score_before, 2),
    }
    memory["rounds"].append(round_record)

    # Update aggregate learning stores
    attack_target = f"{attack.get('target_namespace')}/{attack.get('target_resource')}"

    if attack.get("outcome") in ("blocked_opa", "blocked_blue"):
        if attack_target not in memory["red_learned"]:
            memory["red_learned"].append(
                f"AVOID: {attack_target} — {attack.get('outcome')}"
            )

    if defense.get("outcome") == "success":
        patched = f"{defense.get('target_namespace')}/{defense.get('target_resource')}"
        if patched not in memory["patched_resources"]:
            memory["patched_resources"].append(patched)

    attack_type = attack.get("vuln_type", "unknown")
    if attack_type not in memory["attempted_attacks"]:
        memory["attempted_attacks"].append(attack_type)

    if attack.get("outcome") == "success":
        if attack_target not in memory["successful_attacks"]:
            memory["successful_attacks"].append(attack_target)

    if attack_target in [r.split(" — ")[0].replace("AVOID: ", "")
                          for r in memory["blue_learned"]]:
        pass
    else:
        memory["blue_learned"].append(
            f"Red targets {attack.get('vuln_type', '?')} — watch: {attack_target}"
        )

    memory["score_timeline"].append({
        "round": round_num,
        "score": score_after,
    })

    return memory


def get_red_context(memory: Dict[str, Any]) -> str:
    """Return memory context string for Red Agent prompt."""
    if not memory["rounds"]:
        return "No previous rounds. This is round 1 — scan everything."

    lines = [
        f"=== RED AGENT MEMORY ({len(memory['rounds'])} previous rounds) ===",
        "",
        "THINGS TO AVOID (already patched or blocked):",
    ]
    for item in memory["red_learned"][-10:]:  # Last 10 entries
        lines.append(f"  - {item}")

    lines.append("")
    lines.append("ATTACK TYPES ALREADY TRIED:")
    for t in memory["attempted_attacks"]:
        lines.append(f"  - {t}")

    lines.append("")
    lines.append("SUCCESSFUL ATTACKS (build on these):")
    for t in memory["successful_attacks"][-5:]:
        lines.append(f"  - {t}")

    lines.append("")
    lines.append("SCORE TREND (attack surface exposure):")
    for s in memory["score_timeline"][-5:]:
        lines.append(f"  Round {s['round']}: {s['score']}")

    lines.append("")
    lines.append("STRATEGY HINT: Focus on unpatched resources. Chain vulnerabilities.")
    lines.append("If a resource was patched, find a new vector.")

    return "\n".join(lines)


def get_blue_context(memory: Dict[str, Any]) -> str:
    """Return memory context string for Blue Agent prompt."""
    if not memory["rounds"]:
        return "No previous rounds. Start by hardening highest-severity vulnerabilities."

    lines = [
        f"=== BLUE AGENT MEMORY ({len(memory['rounds'])} previous rounds) ===",
        "",
        "RED AGENT ATTACK PATTERNS (what to expect):",
    ]
    for item in memory["blue_learned"][-10:]:
        lines.append(f"  - {item}")

    lines.append("")
    lines.append("RESOURCES ALREADY PATCHED (don't re-patch):")
    for r in memory["patched_resources"][-10:]:
        lines.append(f"  ✅ {r}")

    if memory["rounds"]:
        last = memory["rounds"][-1]
        lines.append("")
        lines.append(f"LAST ROUND OUTCOME:")
        lines.append(f"  Attack: {last['attack']['type']} → {last['attack']['outcome']}")
        lines.append(f"  Your defense: {last['defense']['type']} → {last['defense']['outcome']}")
        lines.append(f"  Score change: {last['score_before']} → {last['score_after']} ({last['score_delta']:+.1f})")

    lines.append("")
    lines.append("STRATEGY HINT: Pre-harden resources Red hasn't hit yet.")
    lines.append("Focus on CRITICAL severity vulnerabilities first.")

    return "\n".join(lines)
