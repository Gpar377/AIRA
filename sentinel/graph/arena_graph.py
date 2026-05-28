"""
LangGraph Arena Graph — Wires Red Agent, Safety Orchestrator, and Blue Agent
into a supervised multi-agent graph with conditional routing.

Graph topology:
  START → red_agent → orchestrator → blue_agent → memory_update → (loop or END)

The orchestrator is an interrupt-capable node — it can trigger kill switch
which terminates the loop immediately via conditional edge routing.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langgraph.graph import StateGraph, START, END
from datetime import datetime

from state import ArenaState, ArenaEvent
from agents.red_agent import red_agent_node
from agents.orchestrator import orchestrator_node
from agents.blue_agent import blue_agent_node
from memory import record_round, save_memory
from config import settings


# ─────────────────────────────────────────────────────────────────────────────
# Memory Update Node
# ─────────────────────────────────────────────────────────────────────────────

def memory_update_node(state: ArenaState) -> dict:
    """
    Updates cross-round memory after each full round.
    Increments round counter. Determines if arena should continue.
    """
    round_num = state["round"]
    memory = dict(state["memory"])
    events = list(state["events"])

    attack = state.get("proposed_attack") or {}
    defenses = state.get("defenses", [])
    defense = defenses[-1] if defenses else {}

    score_history = state.get("score_history", [])
    score_before = score_history[-2] if len(score_history) >= 2 else state["attack_surface_score"]
    score_after = state["attack_surface_score"]

    # Record this round into memory
    updated_memory = record_round(
        memory=memory,
        round_num=round_num,
        attack=attack,
        defense=defense,
        score_before=score_before,
        score_after=score_after,
        opa_decision=attack.get("opa_decision", "unknown"),
    )

    # Persist memory to disk
    save_memory(updated_memory)

    events.append(ArenaEvent(
        timestamp=datetime.now().isoformat(),
        round=round_num,
        agent="system",
        event_type="round_end",
        message=f"━━━ Round {round_num} Complete ━━━ | Score: {score_before} → {score_after} "
                f"({score_after - score_before:+.1f}) | Attacks: {len(state['attacks'])} | "
                f"Defenses: {len(state['defenses'])}",
        data={
            "round": round_num,
            "score_before": score_before,
            "score_after": score_after,
            "score_delta": round(score_after - score_before, 2),
            "attack_count": len(state["attacks"]),
            "defense_count": len(state["defenses"]),
            "opa_blocks": sum(1 for d in state["opa_decisions"] if d.get("decision") == "DENY"),
        },
    ))

    return {
        "round": round_num + 1,
        "memory": updated_memory,
        "red_action_count": 0,  # Reset per-round action counter
        "events": events,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Routing Functions
# ─────────────────────────────────────────────────────────────────────────────

def should_continue(state: ArenaState) -> str:
    """
    Conditional edge after memory_update.
    Decides whether to run another round or end the arena.
    """
    if state["kill_switch"]:
        return "end"
    if state["status"] == "stopped":
        return "end"
    if state["round"] > state["max_rounds"]:
        return "end"
    if state["attack_surface_score"] <= 10.0:
        return "end"  # Cluster fully hardened
    return "continue"


# ─────────────────────────────────────────────────────────────────────────────
# Build Graph
# ─────────────────────────────────────────────────────────────────────────────

def build_arena_graph():
    """
    Construct and compile the SentinelArena LangGraph.
    Returns a compiled graph ready for invocation.
    """
    graph = StateGraph(ArenaState)

    # Add nodes
    graph.add_node("red_agent", red_agent_node)
    graph.add_node("orchestrator", orchestrator_node)
    graph.add_node("blue_agent", blue_agent_node)
    graph.add_node("memory_update", memory_update_node)

    # Wire edges
    graph.add_edge(START, "red_agent")
    graph.add_edge("red_agent", "orchestrator")
    graph.add_edge("orchestrator", "blue_agent")   # Blue always runs (reactive or proactive)
    graph.add_edge("blue_agent", "memory_update")

    # Conditional: continue looping or end
    graph.add_conditional_edges(
        "memory_update",
        should_continue,
        {
            "continue": "red_agent",
            "end": END,
        },
    )

    return graph.compile()


# ─────────────────────────────────────────────────────────────────────────────
# Initial State Factory
# ─────────────────────────────────────────────────────────────────────────────

def create_initial_state(memory: dict, max_rounds: int = None) -> ArenaState:
    """Build the initial ArenaState for a new arena run."""
    from mock_cluster import get_cluster, reset_cluster
    from tools.real_scanner import get_all_vulnerabilities, calculate_attack_surface_score

    reset_cluster()
    cluster = get_cluster()
    patched_resources = memory.get("patched_resources", [])
    vulns = get_all_vulnerabilities(patched_resources=patched_resources)
    initial_score = calculate_attack_surface_score(vulns)

    return ArenaState(
        round=1,
        max_rounds=max_rounds or settings.MAX_ROUNDS,
        cluster=cluster,
        vulnerabilities=vulns,
        proposed_attack=None,
        attacks=[],
        red_action_count=0,
        defenses=[],
        alerts=[],
        attack_surface_score=initial_score,
        score_history=[initial_score],
        opa_decisions=[],
        kill_switch=False,
        spiral_counter=0,
        last_attack_type=None,
        memory=memory,
        status="running",
        events=[ArenaEvent(
            timestamp=datetime.now().isoformat(),
            round=0,
            agent="system",
            event_type="arena_start",
            message=f"⚔️  SentinelArena initialized | {len(vulns)} vulnerabilities loaded | "
                    f"Initial attack surface score: {initial_score}",
            data={"initial_score": initial_score, "vuln_count": len(vulns)},
        )],
    )
