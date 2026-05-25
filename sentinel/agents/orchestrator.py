"""
Safety Orchestrator — Supervisor node that governs both agents.

Responsibilities:
1. OPA Policy Enforcement — evaluate every Red action before execution
2. Kill Switch — hard-stop if blast radius or escalation detected
3. Spiral Detector — break infinite attack-defend loops
4. Rate Limiter — cap Red actions per round
5. Audit Logging — every decision is logged

This is the crown jewel of SentinelArena's architecture.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from typing import Dict, Any

from state import ArenaState, ArenaEvent
from governance.opa_engine import (
    evaluate_red_action,
    evaluate_escalation_attempt,
    build_opa_decision_log,
)
from config import settings
from tools.mock_kubectl import execute_defense


def orchestrator_node(state: ArenaState) -> Dict[str, Any]:
    """
    LangGraph node — Safety Orchestrator.
    Evaluates the proposed Red action against all governance policies.
    Updates state with decision before Blue Agent runs.
    """
    proposed = state.get("proposed_attack")
    if not proposed:
        return {"events": state["events"]}

    round_num = state["round"]
    events = list(state["events"])
    opa_decisions = list(state["opa_decisions"])
    attacks = list(state["attacks"])
    spiral_counter = state["spiral_counter"]

    # ── Check 1: Kill switch already active ───────────────────────────────────
    if state["kill_switch"]:
        events.append(ArenaEvent(
            timestamp=datetime.now().isoformat(),
            round=round_num,
            agent="orchestrator",
            event_type="kill_switch",
            message="⚡ KILL SWITCH ACTIVE — Red Agent halted",
            data={"reason": "kill_switch_already_active"},
        ))
        updated = dict(proposed)
        updated["opa_decision"] = "blocked"
        updated["opa_reason"] = "kill_switch_active"
        updated["outcome"] = "blocked_opa"
        return {"proposed_attack": updated, "events": events}

    # ── Check 2: Escalation attempt ───────────────────────────────────────────
    is_escalation, esc_reason = evaluate_escalation_attempt(proposed, attacks)
    if is_escalation:
        events.append(ArenaEvent(
            timestamp=datetime.now().isoformat(),
            round=round_num,
            agent="orchestrator",
            event_type="kill_switch",
            message=f"🚨 ESCALATION DETECTED — Kill switch triggered: {esc_reason}",
            data={"reason": esc_reason},
        ))
        updated = dict(proposed)
        updated["opa_decision"] = "blocked"
        updated["opa_reason"] = esc_reason
        updated["outcome"] = "blocked_opa"
        return {
            "proposed_attack": updated,
            "kill_switch": True,
            "events": events,
        }

    # ── Check 3: OPA policy evaluation ───────────────────────────────────────
    allowed, reason, severity = evaluate_red_action(proposed, state["red_action_count"])
    opa_log = build_opa_decision_log(proposed, allowed, reason, severity, round_num)
    opa_decisions.append(opa_log)

    decision_emoji = "✅" if allowed else "❌"
    events.append(ArenaEvent(
        timestamp=datetime.now().isoformat(),
        round=round_num,
        agent="orchestrator",
        event_type="opa_check",
        message=f"{decision_emoji} OPA Decision: {'ALLOW' if allowed else 'DENY'} | {reason} | Blast: {proposed['blast_radius']:.2f}",
        data=opa_log,
    ))

    # ── Check 4: Spiral detection ────────────────────────────────────────────
    new_spiral_counter = spiral_counter
    if not allowed:
        new_spiral_counter += 1
        if new_spiral_counter >= settings.SPIRAL_THRESHOLD:
            events.append(ArenaEvent(
                timestamp=datetime.now().isoformat(),
                round=round_num,
                agent="orchestrator",
                event_type="kill_switch",
                message=f"🌀 SPIRAL DETECTED — {new_spiral_counter} consecutive blocks. Forcing strategy reset.",
                data={"consecutive_blocks": new_spiral_counter},
            ))
            # Reset spiral counter but inject learning hint into memory
            new_spiral_counter = 0
    else:
        new_spiral_counter = 0  # Reset on successful allow

    # ── Execute attack if allowed ─────────────────────────────────────────────
    updated_attack = dict(proposed)
    if allowed:
        # Simulate attack execution
        updated_attack["opa_decision"] = "allowed"
        updated_attack["opa_reason"] = reason
        updated_attack["outcome"] = "success"  # Blue may override this

        events.append(ArenaEvent(
            timestamp=datetime.now().isoformat(),
            round=round_num,
            agent="red",
            event_type="execute",
            message=f"💥 Attack executing → {proposed['vuln_type'].upper()} on "
                    f"{proposed['target_namespace']}/{proposed['target_resource']}",
            data={"method": proposed["method"][:200]},
        ))
    else:
        updated_attack["opa_decision"] = "blocked"
        updated_attack["opa_reason"] = reason
        updated_attack["outcome"] = "blocked_opa"

    attacks.append(updated_attack)

    return {
        "proposed_attack": updated_attack,
        "attacks": attacks,
        "opa_decisions": opa_decisions,
        "spiral_counter": new_spiral_counter,
        "red_action_count": state["red_action_count"] + 1,
        "events": events,
    }
