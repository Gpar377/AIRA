"""
Purple Agent — Meta-observer that synthesizes Red/Blue battle patterns
into actionable security intelligence.

Runs ONCE at the end of a battle (not every round). Analyses the full
attack/defense timeline and produces a structured Security Posture Report.

Responsibilities:
1. Statistical analysis — attack type distribution, success rates, chain depth
2. Defense gap analysis — which namespaces/resources were never defended
3. Governance review — OPA block rates, escalation attempts
4. LLM-driven pattern synthesis — blind spots, trends, prioritized recommendations
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collections import Counter
from datetime import datetime
from typing import Dict, Any, List, Optional

from google import genai

from config import settings
from state import ArenaState, ArenaEvent, PurpleReport
from llm_utils import call_gemini, extract_json

# Lazy Gemini client init
_client: Optional[genai.Client] = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _client


PURPLE_SYSTEM_PROMPT = """You are a Purple Team security analyst. You have just observed a complete
Red vs Blue adversarial battle on a Kubernetes cluster. Your job is to synthesize the battle data
into actionable security intelligence.

You will be given:
- The full attack timeline (Red Agent actions, types, targets, outcomes)
- The full defense timeline (Blue Agent actions, types, targets, outcomes)
- OPA governance decisions
- Score trajectory (attack surface over time)

Analyse the data and respond with ONLY valid JSON:
{
  "pattern_synthesis": "2-3 sentence summary of the dominant attack/defense patterns observed",
  "blind_spots": "2-3 sentences identifying namespaces, resources, or vulnerability classes that were never adequately addressed",
  "recommendations": [
    "First priority remediation action",
    "Second priority remediation action",
    "Third priority remediation action"
  ],
  "risk_rating": "CRITICAL | HIGH | MEDIUM | LOW"
}

RULES:
- Be specific. Reference actual namespaces, resources, and CVE IDs from the battle data.
- Recommendations should be actionable (e.g. "Apply NetworkPolicy to isolate namespace X" not "improve security").
- risk_rating should reflect the FINAL state: CRITICAL if score > 60, HIGH if > 40, MEDIUM if > 20, LOW if <= 20.
- Keep each field concise. No markdown, no code fences, only JSON."""


# ─────────────────────────────────────────────────────────────────────────────
# Statistical Analysis (deterministic — no LLM needed)
# ─────────────────────────────────────────────────────────────────────────────

def _compute_attack_stats(attacks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute attack-side statistics from the battle history."""
    if not attacks:
        return {
            "types": {}, "success_rate": 0.0, "chain_depth": 0,
            "top_namespace": "none", "top_resource": "none",
        }

    type_counts = Counter(a.get("vuln_type", "unknown") for a in attacks)
    successes = sum(1 for a in attacks if a.get("outcome") == "success")
    success_rate = round(successes / len(attacks), 3) if attacks else 0.0

    # Chain depth: count longest chained_from sequence
    chain_depth = 0
    for a in attacks:
        depth = 1
        chain_from = a.get("chained_from")
        seen = {a.get("target_resource")}
        while chain_from and chain_from not in seen:
            depth += 1
            seen.add(chain_from)
            # Find the parent attack
            parent = next((x for x in attacks if x.get("target_resource") == chain_from), None)
            chain_from = parent.get("chained_from") if parent else None
        chain_depth = max(chain_depth, depth)

    ns_counts = Counter(a.get("target_namespace", "unknown") for a in attacks)
    res_counts = Counter(a.get("target_resource", "unknown") for a in attacks)

    return {
        "types": dict(type_counts),
        "success_rate": success_rate,
        "chain_depth": chain_depth,
        "top_namespace": ns_counts.most_common(1)[0][0] if ns_counts else "none",
        "top_resource": res_counts.most_common(1)[0][0] if res_counts else "none",
    }


def _compute_defense_stats(defenses: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute defense-side statistics from the battle history."""
    if not defenses:
        return {
            "types": {}, "coverage_gaps": [], "pre_emptive_rate": 0.0,
        }

    type_counts = Counter(d.get("defense_type", "unknown") for d in defenses)
    pre_emptive = sum(1 for d in defenses if d.get("pre_emptive", False))
    pre_emptive_rate = round(pre_emptive / len(defenses), 3) if defenses else 0.0

    defended_resources = set()
    for d in defenses:
        defended_resources.add(f"{d.get('target_namespace', '?')}/{d.get('target_resource', '?')}")

    return {
        "types": dict(type_counts),
        "coverage_gaps": [],  # Will be populated by comparing against attack targets
        "pre_emptive_rate": pre_emptive_rate,
        "defended_resources": defended_resources,
    }


def _compute_governance_stats(opa_decisions: List[Dict[str, Any]], kill_switch: bool) -> Dict[str, Any]:
    """Compute OPA governance statistics."""
    if not opa_decisions:
        return {"block_rate": 0.0, "escalation_attempts": 0, "kill_switch": kill_switch}

    blocks = sum(1 for d in opa_decisions if d.get("decision") == "DENY" or not d.get("allowed", True))
    block_rate = round(blocks / len(opa_decisions), 3)
    escalations = sum(1 for d in opa_decisions if "escalation" in str(d.get("reason", "")).lower())

    return {
        "block_rate": block_rate,
        "escalation_attempts": escalations,
        "kill_switch": kill_switch,
    }


def _find_coverage_gaps(
    attacks: List[Dict[str, Any]],
    defended_resources: set,
) -> List[str]:
    """Identify attack targets that were never defended."""
    attacked_resources = set()
    for a in attacks:
        if a.get("outcome") == "success":
            attacked_resources.add(f"{a.get('target_namespace', '?')}/{a.get('target_resource', '?')}")

    gaps = attacked_resources - defended_resources
    return sorted(gaps)


# ─────────────────────────────────────────────────────────────────────────────
# LLM-Driven Pattern Synthesis
# ─────────────────────────────────────────────────────────────────────────────

def _build_battle_summary(
    attacks: List[Dict[str, Any]],
    defenses: List[Dict[str, Any]],
    score_history: List[float],
    opa_decisions: List[Dict[str, Any]],
) -> str:
    """Build a human-readable battle timeline for the LLM prompt."""
    lines = [f"BATTLE SUMMARY ({len(score_history)-1} rounds)\n"]

    lines.append(f"Score trajectory: {' → '.join(str(int(s)) for s in score_history)}")
    lines.append(f"Score reduction: {score_history[0]:.0f} → {score_history[-1]:.0f} "
                 f"({((score_history[0] - score_history[-1]) / max(score_history[0], 1)) * 100:.1f}% reduced)\n")

    lines.append("ATTACK TIMELINE:")
    for i, a in enumerate(attacks):
        outcome_icon = "✓" if a.get("outcome") == "success" else "✗"
        lines.append(f"  R{a.get('round', '?')}: [{outcome_icon}] {a.get('vuln_type', '?').upper()} → "
                     f"{a.get('target_namespace', '?')}/{a.get('target_resource', '?')} "
                     f"(blast: {a.get('blast_radius', 0):.2f}, OPA: {a.get('opa_decision', '?')})")

    lines.append("\nDEFENSE TIMELINE:")
    for d in defenses:
        pre = "⚡PRE" if d.get("pre_emptive") else "  RXN"
        lines.append(f"  R{d.get('round', '?')}: [{pre}] {d.get('defense_type', '?')} → "
                     f"{d.get('target_namespace', '?')}/{d.get('target_resource', '?')} "
                     f"(Δ score: {d.get('score_delta', 0):+.1f})")

    opa_blocks = sum(1 for d in opa_decisions if d.get("decision") == "DENY" or not d.get("allowed", True))
    lines.append(f"\nOPA GOVERNANCE: {len(opa_decisions)} decisions, {opa_blocks} blocked")

    return "\n".join(lines)


def _generate_llm_insights(battle_summary: str, final_score: float) -> Dict[str, Any]:
    """Call Gemini to generate pattern synthesis, blind spots, and recommendations."""
    prompt = f"""{PURPLE_SYSTEM_PROMPT}

{battle_summary}

FINAL ATTACK SURFACE SCORE: {final_score:.0f}/100

Generate your security posture analysis now."""

    raw_text = call_gemini(_get_client(), settings.GEMINI_MODEL, prompt)

    if raw_text:
        data = extract_json(raw_text)
        if data:
            return {
                "pattern_synthesis": data.get("pattern_synthesis", "Analysis unavailable."),
                "blind_spots": data.get("blind_spots", "No blind spots identified."),
                "recommendations": data.get("recommendations", ["Run additional campaigns for more data."]),
                "risk_rating": data.get("risk_rating", "MEDIUM"),
            }

    # Deterministic fallback if LLM fails
    if final_score > 60:
        rating = "CRITICAL"
    elif final_score > 40:
        rating = "HIGH"
    elif final_score > 20:
        rating = "MEDIUM"
    else:
        rating = "LOW"

    return {
        "pattern_synthesis": "LLM analysis unavailable. Statistical data has been computed from battle records.",
        "blind_spots": "Manual review of coverage gaps recommended.",
        "recommendations": [
            "Review coverage gaps listed in this report",
            "Increase campaign rounds for deeper attack surface exploration",
            "Ensure all critical namespaces have active NetworkPolicies",
        ],
        "risk_rating": rating,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Purple Agent LangGraph Node
# ─────────────────────────────────────────────────────────────────────────────

def purple_agent_node(state: ArenaState) -> Dict[str, Any]:
    """
    LangGraph node — Purple Agent. Runs once at end of battle.
    Analyses the full attack/defense timeline and produces a PurpleReport.
    """
    attacks = state.get("attacks", [])
    defenses = state.get("defenses", [])
    opa_decisions = state.get("opa_decisions", [])
    score_history = state.get("score_history", [0])
    kill_switch = state.get("kill_switch", False)
    events = list(state.get("events", []))
    arena_id = state.get("memory", {}).get("arena_id", "unknown")

    # ── Step 1: Deterministic statistical analysis ────────────────────────────
    attack_stats = _compute_attack_stats(attacks)
    defense_stats = _compute_defense_stats(defenses)
    governance_stats = _compute_governance_stats(opa_decisions, kill_switch)
    coverage_gaps = _find_coverage_gaps(attacks, defense_stats.get("defended_resources", set()))

    # ── Step 2: LLM-driven pattern synthesis ──────────────────────────────────
    battle_summary = _build_battle_summary(attacks, defenses, score_history, opa_decisions)
    llm_insights = _generate_llm_insights(battle_summary, score_history[-1])

    # ── Step 3: Assemble PurpleReport ─────────────────────────────────────────
    initial_score = score_history[0] if score_history else 100.0
    final_score = score_history[-1] if score_history else 100.0
    score_reduction = round(((initial_score - final_score) / max(initial_score, 1)) * 100, 1)

    report = PurpleReport(
        campaign_id=arena_id,
        total_rounds=state.get("round", 1) - 1,
        # Attack analysis
        attack_types_attempted=attack_stats["types"],
        attack_success_rate=attack_stats["success_rate"],
        attack_chain_depth=attack_stats["chain_depth"],
        most_exploited_namespace=attack_stats["top_namespace"],
        most_exploited_resource=attack_stats["top_resource"],
        # Defense analysis
        defense_types_deployed=defense_stats["types"],
        defense_coverage_gaps=coverage_gaps,
        pre_emptive_defense_rate=defense_stats["pre_emptive_rate"],
        # Governance
        opa_block_rate=governance_stats["block_rate"],
        escalation_attempts=governance_stats["escalation_attempts"],
        kill_switch_triggered=governance_stats["kill_switch"],
        # Score trajectory
        initial_score=initial_score,
        final_score=final_score,
        score_reduction_pct=score_reduction,
        # LLM-generated insights
        pattern_synthesis=llm_insights["pattern_synthesis"],
        blind_spots=llm_insights["blind_spots"],
        recommendations=llm_insights["recommendations"],
        risk_rating=llm_insights["risk_rating"],
    )

    # ── Step 4: Emit event ────────────────────────────────────────────────────
    events.append(ArenaEvent(
        timestamp=datetime.now().isoformat(),
        round=state.get("round", 0),
        agent="purple",
        event_type="purple_report",
        message=(
            f"🟣 Purple Agent Report | Risk: {report['risk_rating']} | "
            f"Score: {initial_score:.0f} → {final_score:.0f} ({score_reduction:+.1f}%) | "
            f"Attacks: {len(attacks)} ({attack_stats['success_rate']*100:.0f}% success) | "
            f"Coverage gaps: {len(coverage_gaps)}"
        ),
        data=dict(report),
    ))

    # Print report to console
    _print_report(report)

    return {
        "purple_report": report,
        "events": events,
        "status": "completed",
    }


def _print_report(report: PurpleReport) -> None:
    """Pretty-print the Purple Agent security posture report to console."""
    print("\n" + "=" * 72)
    print("  🟣 PURPLE AGENT — SECURITY POSTURE REPORT")
    print("=" * 72)
    print(f"  Campaign:    {report['campaign_id']}")
    print(f"  Rounds:      {report['total_rounds']}")
    print(f"  Risk Rating: {report['risk_rating']}")
    print("-" * 72)

    print(f"\n  📊 SCORE TRAJECTORY")
    print(f"     Initial: {report['initial_score']:.0f}  →  Final: {report['final_score']:.0f}"
          f"  ({report['score_reduction_pct']:+.1f}% reduction)")

    print(f"\n  🔴 ATTACK ANALYSIS")
    print(f"     Types attempted:  {report['attack_types_attempted']}")
    print(f"     Success rate:     {report['attack_success_rate']*100:.1f}%")
    print(f"     Chain depth:      {report['attack_chain_depth']}")
    print(f"     Top namespace:    {report['most_exploited_namespace']}")
    print(f"     Top resource:     {report['most_exploited_resource']}")

    print(f"\n  🔵 DEFENSE ANALYSIS")
    print(f"     Types deployed:   {report['defense_types_deployed']}")
    print(f"     Pre-emptive rate: {report['pre_emptive_defense_rate']*100:.1f}%")
    if report['defense_coverage_gaps']:
        print(f"     ⚠️  Coverage gaps: {', '.join(report['defense_coverage_gaps'])}")
    else:
        print(f"     ✅ No coverage gaps detected")

    print(f"\n  🛡️  GOVERNANCE")
    print(f"     OPA block rate:       {report['opa_block_rate']*100:.1f}%")
    print(f"     Escalation attempts:  {report['escalation_attempts']}")
    print(f"     Kill switch triggered: {'YES ⚡' if report['kill_switch_triggered'] else 'No'}")

    print(f"\n  🧠 PATTERN SYNTHESIS")
    print(f"     {report['pattern_synthesis']}")

    print(f"\n  👁️  BLIND SPOTS")
    print(f"     {report['blind_spots']}")

    print(f"\n  📋 RECOMMENDATIONS")
    for i, rec in enumerate(report['recommendations'], 1):
        print(f"     {i}. {rec}")

    print("\n" + "=" * 72 + "\n")
