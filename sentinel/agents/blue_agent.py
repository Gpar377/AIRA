"""
Blue Agent — LangGraph node for the defender.
Uses Gemini to reason about defenses — both reactive (responding to attacks)
and proactive (pre-hardening based on Red's memory patterns).

Decision loop:
1. Read Falco-like alerts (generated from Red's executed attacks)
2. Read cross-round memory (what has Red targeted? what's already patched?)
3. Call Gemini to decide the best defensive action
4. Execute defense via mock_kubectl
5. Update attack surface score
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
from state import ArenaState, DefenseAction, ArenaEvent
from tools.real_kubectl import execute_defense
from tools.real_scanner import get_all_vulnerabilities, calculate_attack_surface_score
from memory import get_blue_context
from llm_utils import call_gemini, BlueActionSchema

# Lazy Gemini client init
_client: Optional[genai.Client] = None

def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _client


BLUE_SYSTEM_PROMPT = """You are an expert Blue Team security engineer defending a Kubernetes cluster.
You have access to real-time Falco alerts and must respond to detected attacks AND proactively harden defenses.

AVAILABLE DEFENSE ACTIONS:
- rbac_patch: Remove excessive permissions from RBAC roles
- secret_rotation: Rotate and remove secrets from environment variables
- network_policy: Apply NetworkPolicy to isolate a namespace
- pod_restart: Restart pod with privileged:false and non-root security context
- image_update: Update container image to patched version

DEFENSE MATCHING RULES:
You MUST match your defense type to the active attack type or the target vulnerability type:
- If the attack or vulnerability is a NETWORK attack/vulnerability, you MUST use 'network_policy'.
- If the attack or vulnerability is a SECRET attack/vulnerability, you MUST use 'secret_rotation'.
- If the attack or vulnerability is an RBAC attack/vulnerability, you MUST use 'rbac_patch'.
- If the attack or vulnerability is a PRIVILEGE attack/vulnerability, you MUST use 'pod_restart'.
- If the attack or vulnerability is a CVE attack/vulnerability, you MUST use 'image_update'.

Failing to match the defense type to the attack type will result in the defense failing to block the attack.

DEFENSE TYPE PRIORITY: CRITICAL severity first, then HIGH, then proactive hardening.

You must respond with ONLY valid JSON (no markdown, no explanation):
{
  "defense_type": "rbac_patch | secret_rotation | network_policy | pod_restart | image_update",
  "target_namespace": "exact namespace name",
  "target_resource": "exact resource name",
  "method": "specific remediation in 1-2 sentences",
  "rationale": "why this defense is the most effective right now",
  "pre_emptive": true or false
}"""


def _parse_llm_json(text: str) -> Dict[str, Any]:
    """Extract JSON from LLM response."""
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE)
    text = text.strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group())
    return json.loads(text)


def _generate_falco_alerts(attack: Dict[str, Any]) -> list:
    """
    Simulate Falco runtime alerts triggered by Red's attack.
    In Phase 2: reads from Falco's gRPC output stream or log file.
    """
    if not attack or attack.get("outcome") == "blocked_opa":
        return []

    vuln_type = attack.get("vuln_type", "")
    alerts = []

    alert_templates = {
        "secret": {
            "rule": "Sensitive File Access",
            "priority": "CRITICAL",
            "message": f"Pod attempted to read secret environment variable: {attack.get('target_resource')}",
            "tags": ["secret", "data_exfiltration"],
        },
        "rbac": {
            "rule": "K8s ServiceAccount Created ClusterRoleBinding",
            "priority": "HIGH",
            "message": f"Unexpected API call to secrets endpoint from {attack.get('target_namespace')} namespace",
            "tags": ["rbac", "privilege_escalation"],
        },
        "privilege": {
            "rule": "Launch Privileged Container",
            "priority": "CRITICAL",
            "message": f"Privileged container activity detected in {attack.get('target_namespace')}/{attack.get('target_resource')}",
            "tags": ["privilege_escalation", "container_escape"],
        },
        "network": {
            "rule": "Unexpected Network Connection",
            "priority": "HIGH",
            "message": f"Pod in {attack.get('target_namespace')} connecting to unexpected external endpoint",
            "tags": ["network", "lateral_movement"],
        },
        "cve": {
            "rule": "Outbound Connection to Unexpected Destination",
            "priority": "HIGH",
            "message": f"CVE exploit traffic pattern detected from {attack.get('target_resource')}",
            "tags": ["cve", "exploit"],
        },
    }

    template = alert_templates.get(vuln_type, {
        "rule": "Suspicious Activity",
        "priority": "MEDIUM",
        "message": f"Anomalous activity in {attack.get('target_namespace')}",
        "tags": ["anomaly"],
    })
    template["timestamp"] = datetime.now().isoformat()
    template["namespace"] = attack.get("target_namespace", "default")
    template["resource"] = attack.get("target_resource", "unknown")
    alerts.append(template)
    return alerts


def _fallback_defense(vulns: list, patched: list) -> Dict[str, Any]:
    """Rule-based fallback defense if LLM call fails."""
    for v in sorted(vulns, key=lambda x: {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}.get(x["severity"], 0),
                    reverse=True):
        target = f"{v['namespace']}/{v['resource']}"
        if not v["patched"] and target not in patched:
            type_map = {
                "secret": "secret_rotation",
                "rbac": "rbac_patch",
                "network": "network_policy",
                "privilege": "pod_restart",
                "cve": "image_update",
            }
            return {
                "defense_type": type_map.get(v["vuln_type"], "rbac_patch"),
                "target_namespace": v["namespace"],
                "target_resource": v["resource"],
                "method": f"Fallback: remediate {v['id']} — {v['description'][:80]}",
                "rationale": "Highest severity unpatched vulnerability",
                "pre_emptive": False,
            }
    return {
        "defense_type": "network_policy",
        "target_namespace": "default",
        "method": "Apply default-deny NetworkPolicy as baseline hardening",
        "rationale": "Fallback: general hardening when no specific target available",
        "target_resource": "default-namespace",
        "pre_emptive": True,
    }


def blue_agent_node(state: ArenaState) -> Dict[str, Any]:
    """
    LangGraph node — Blue Agent's full defense cycle.
    Returns partial state update.
    """
    round_num = state["round"]
    memory = state["memory"]
    events = list(state["events"])
    defenses = list(state["defenses"])
    proposed_attack = state.get("proposed_attack")

    # ── Step 1: Generate Falco alerts from Red's attack ───────────────────────
    alerts = _generate_falco_alerts(proposed_attack or {})
    if alerts:
        for alert in alerts:
            events.append(ArenaEvent(
                timestamp=datetime.now().isoformat(),
                round=round_num,
                agent="blue",
                event_type="alert",
                message=f"🚨 Falco Alert [{alert['priority']}]: {alert['rule']} — {alert['message'][:100]}",
                data=alert,
            ))

    # ── Step 2: Get current vulnerabilities ──────────────────────────────────
    patched_resources = memory.get("patched_resources", [])
    vulns = get_all_vulnerabilities(patched_resources=patched_resources)
    unpatched_vulns = [v for v in vulns if not v["patched"]]
    severity_map = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "UNKNOWN": 4}
    unpatched_vulns = sorted(unpatched_vulns, key=lambda x: severity_map.get(x["severity"], 4))
    unpatched_vulns = unpatched_vulns[:15]
    memory_ctx = get_blue_context(memory)

    unpatched_summary = "\n".join([
        f"  [{v['severity']}] {v['id']} | {v['namespace']}/{v['resource']} | {v['description'][:80]}"
        for v in unpatched_vulns
    ])

    alerts_summary = "\n".join([
        f"  [{a['priority']}] {a['rule']}: {a['message']}"
        for a in alerts
    ])

    attack_context = ""
    if proposed_attack and proposed_attack.get("outcome") != "blocked_opa":
        attack_context = f"""
CURRENT ROUND ATTACK (respond to this):
  Type: {proposed_attack.get('vuln_type')}
  Target: {proposed_attack.get('target_namespace')}/{proposed_attack.get('target_resource')}
  Method: {proposed_attack.get('method', '')[:150]}
  Status: {proposed_attack.get('outcome', 'executed')}"""

    prompt = f"""{BLUE_SYSTEM_PROMPT}

FALCO RUNTIME ALERTS:
{alerts_summary if alerts_summary else "  No active alerts this round."}

{attack_context}

CURRENT UNPATCHED VULNERABILITIES:
{unpatched_summary if unpatched_summary else "  No unpatched vulnerabilities!"}

{memory_ctx}

Round: {round_num}/{state['max_rounds']}
Current attack surface score: {state['attack_surface_score']}/100

Choose ONE defense action. Prioritize: 1) respond to active attack, 2) patch CRITICAL vulns, 3) proactive hardening."""

    # ── Step 3: LLM reasoning (with retry + Pydantic validation) ────────────
    raw_text = call_gemini(_get_client(), settings.GEMINI_MODEL, prompt)
    if raw_text:
        schema, valid = BlueActionSchema.parse_llm_output(raw_text)
        defense_data = schema.model_dump() if valid else None
    else:
        defense_data = None

    if defense_data is None:
        defense_data = _fallback_defense(vulns, patched_resources)

    # ── Step 4: Execute defense ───────────────────────────────────────────────
    defense_type = defense_data.get("defense_type", "rbac_patch")
    target_ns = defense_data.get("target_namespace", "default")
    target_resource = defense_data.get("target_resource", "")

    success, kubectl_msg = execute_defense(defense_type, target_ns, target_resource)

    # Check if attack was blocked by the defense
    if proposed_attack and proposed_attack.get("outcome") == "success":
        attack_vuln_type = proposed_attack.get("vuln_type")
        # Map vuln_type to expected defense_type
        attack_to_defense_map = {
            "network": "network_policy",
            "secret": "secret_rotation",
            "rbac": "rbac_patch",
            "privilege": "pod_restart",
            "cve": "image_update"
        }
        expected_defense = attack_to_defense_map.get(attack_vuln_type)
        if defense_type == expected_defense:
            if (target_ns == proposed_attack.get("target_namespace") or
                    target_resource in proposed_attack.get("target_resource", "")):
                # Blue successfully blocked the attack
                if state.get("proposed_attack"):
                    proposed_attack = dict(proposed_attack)
                    proposed_attack["outcome"] = "blocked_blue"

    # Recalculate score after defense, passing the newly applied patch to bypass database lag
    local_patched = list(memory.get("patched_resources", []))
    if success:
        new_patch = f"{defense_type}:{target_ns}/{target_resource}"
        if new_patch not in local_patched:
            local_patched.append(new_patch)
            
    updated_vulns = get_all_vulnerabilities(patched_resources=local_patched)
    new_score = calculate_attack_surface_score(updated_vulns)
    score_delta = round(new_score - state["attack_surface_score"], 2)

    defense_action = DefenseAction(
        round=round_num,
        defense_type=defense_type,
        target_namespace=target_ns,
        target_resource=target_resource,
        method=defense_data.get("method", ""),
        rationale=defense_data.get("rationale", ""),
        pre_emptive=defense_data.get("pre_emptive", False),
        outcome="success" if success else "failed",
        score_delta=score_delta,
    )
    defenses.append(defense_action)

    events.append(ArenaEvent(
        timestamp=datetime.now().isoformat(),
        round=round_num,
        agent="blue",
        event_type="patch",
        message=f"🛡️ Defense applied → [{defense_type.upper()}] {target_ns}/{target_resource} | "
                f"Score: {state['attack_surface_score']} → {new_score} ({score_delta:+.1f})",
        data={
            "defense": defense_action,
            "kubectl_result": kubectl_msg,
            "score_before": state["attack_surface_score"],
            "score_after": new_score,
        },
    ))

    return_state = {
        "defenses": defenses,
        "alerts": state["alerts"] + alerts,
        "attack_surface_score": new_score,
        "score_history": state["score_history"] + [new_score],
        "events": events,
    }
    if proposed_attack:
        return_state["proposed_attack"] = proposed_attack

    return return_state
