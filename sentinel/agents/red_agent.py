"""
Red Agent — LangGraph node for the adversarial attacker.
Uses Gemini to reason about vulnerabilities and propose chained attack scenarios.

Decision loop:
1. Scan cluster for vulnerabilities (via mock_scanner)
2. Read cross-round memory (what's patched, what worked)
3. Call Gemini to reason and propose an attack action (structured JSON)
4. Store proposed action in state — Orchestrator decides if it runs
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import re
from datetime import datetime
from typing import Dict, Any, Optional

from google import genai
from google.genai import types

from config import settings
from state import ArenaState, AttackAction, ArenaEvent
from tools.real_scanner import get_all_vulnerabilities, calculate_attack_surface_score
from memory import get_red_context
from llm_utils import call_gemini, RedActionSchema

# Lazy Gemini client init
_client: Optional[genai.Client] = None

def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _client


RED_SYSTEM_PROMPT = """You are an elite Red Team security researcher operating inside a CONTROLLED Kubernetes sandbox.
Your mission: identify and chain vulnerabilities to simulate realistic attack scenarios.

RULES YOU MUST FOLLOW:
- Only target resources that appear in the vulnerability list
- Do NOT target kube-system namespace
- Do NOT propose host escapes, etcd access, or deletion of all resources
- Keep blast_radius between 0.0 and 0.74 (higher values get blocked by policy)
- Chain vulnerabilities when possible (e.g., use RBAC access to read secrets, then use secret to pivot)
- Avoid resources marked as patched in your memory

You must respond with ONLY valid JSON (no markdown, no explanation):
{{
  "vuln_type": "cve | rbac | secret | network | privilege",
  "target_namespace": "exact namespace name",
  "target_resource": "exact resource name",
  "method": "specific technique in 1-2 sentences",
  "rationale": "why this is effective given current cluster state and memory",
  "blast_radius": 0.0-0.74,
  "chained_from": "vulnerability ID this builds on, or null"
}}"""


def _parse_llm_json(text: str) -> Dict[str, Any]:
    """Extract JSON from LLM response, handling markdown code fences."""
    # Strip markdown code blocks if present
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE)
    text = text.strip()

    # Find the first complete JSON object
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group())
    return json.loads(text)


def _generate_fallback_attack(vulns: list, round_num: int) -> Dict[str, Any]:
    """Rule-based fallback if LLM call fails."""
    # Find first unpatched exploitable vuln
    for v in vulns:
        if not v["patched"] and v["exploitable"]:
            return {
                "vuln_type": v["vuln_type"],
                "target_namespace": v["namespace"],
                "target_resource": v["resource"],
                "method": f"Exploit {v['id']}: {v['description'][:80]}",
                "rationale": "Fallback: targeting highest severity unpatched vulnerability",
                "blast_radius": 0.4,
                "chained_from": v["id"],
            }
    return {
        "vuln_type": "network",
        "target_namespace": "default",
        "target_resource": "webapp-service",
        "method": "Network reconnaissance — enumerate accessible services",
        "rationale": "Fallback: probing network after all other vectors exhausted",
        "blast_radius": 0.2,
        "chained_from": None,
    }


def red_agent_node(state: ArenaState) -> Dict[str, Any]:
    """
    LangGraph node — Red Agent's full decision cycle.
    Returns partial state update.
    """
    round_num = state["round"]
    memory = state["memory"]
    events = list(state["events"])

    # ── Step 1: Scan ──────────────────────────────────────────────────────────
    patched_resources = memory.get("patched_resources", [])
    vulns = get_all_vulnerabilities(patched_resources=patched_resources)
    current_score = calculate_attack_surface_score(vulns)

    events.append(ArenaEvent(
        timestamp=datetime.now().isoformat(),
        round=round_num,
        agent="red",
        event_type="scan",
        message=f"Scanned cluster → {len(vulns)} vulnerabilities found | Score: {current_score}",
        data={"vuln_count": len(vulns), "score": current_score,
              "critical": sum(1 for v in vulns if v["severity"] == "CRITICAL" and not v["patched"]),
              "high": sum(1 for v in vulns if v["severity"] == "HIGH" and not v["patched"])},
    ))

    # ── Step 2: Build prompt ──────────────────────────────────────────────────
    unpatched_vulns = [v for v in vulns if not v["patched"] and v["exploitable"]]
    severity_map = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "UNKNOWN": 4}
    unpatched_vulns = sorted(unpatched_vulns, key=lambda x: severity_map.get(x["severity"], 4))
    unpatched_vulns = unpatched_vulns[:15]
    memory_ctx = get_red_context(memory)

    vuln_summary = "\n".join([
        f"  [{v['severity']}] {v['id']} | {v['namespace']}/{v['resource']} | {v['description'][:100]}"
        for v in unpatched_vulns
    ])

    prompt = f"""{RED_SYSTEM_PROMPT}

CURRENT CLUSTER STATE — UNPATCHED VULNERABILITIES:
{vuln_summary if vuln_summary else "No unpatched vulnerabilities found."}

ATTACK SURFACE SCORE: {current_score}/100

{memory_ctx}

Round: {round_num}/{state['max_rounds']}
Choose your next attack. Remember: chain vulnerabilities, avoid patched resources."""

    # ── Step 3: LLM reasoning (with retry + Pydantic validation) ────────────
    raw_text = call_gemini(_get_client(), settings.GEMINI_MODEL, prompt)
    if raw_text:
        schema, valid = RedActionSchema.parse_llm_output(raw_text)
        proposed_attack_data = schema.model_dump() if valid else None
    else:
        proposed_attack_data = None

    if proposed_attack_data is None:
        proposed_attack_data = _generate_fallback_attack(unpatched_vulns, round_num)

    # ── Step 4: Structure the action ──────────────────────────────────────────
    proposed_attack = AttackAction(
        round=round_num,
        vuln_type=proposed_attack_data.get("vuln_type", "unknown"),
        target_namespace=proposed_attack_data.get("target_namespace", "default"),
        target_resource=proposed_attack_data.get("target_resource", "unknown"),
        method=proposed_attack_data.get("method", ""),
        rationale=proposed_attack_data.get("rationale", ""),
        blast_radius=float(proposed_attack_data.get("blast_radius", 0.4)),
        chained_from=proposed_attack_data.get("chained_from"),
        opa_decision="pending",
        opa_reason="",
        outcome="pending",
    )

    events.append(ArenaEvent(
        timestamp=datetime.now().isoformat(),
        round=round_num,
        agent="red",
        event_type="propose_attack",
        message=f"Proposed attack → [{proposed_attack['vuln_type'].upper()}] "
                f"{proposed_attack['target_namespace']}/{proposed_attack['target_resource']}",
        data={
            "attack": proposed_attack,
            "method_preview": proposed_attack["method"][:120],
        },
    ))

    return {
        "vulnerabilities": vulns,
        "proposed_attack": proposed_attack,
        "attack_surface_score": current_score,
        "score_history": state["score_history"] + [current_score],
        "events": events,
    }
