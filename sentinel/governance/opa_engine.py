"""
OPA (Open Policy Agent) Engine — Python implementation of Rego-equivalent policies.
In Phase 2, this will call the real OPA server via HTTP:
    POST http://localhost:8181/v1/data/sentinel/redagent/allow

Every Red Agent action MUST be evaluated here before execution.
The Safety Orchestrator calls this as its primary governance mechanism.
"""
from typing import Dict, Any, Tuple


# ─────────────────────────────────────────────────────────────────────────────
# Policy Constants
# ─────────────────────────────────────────────────────────────────────────────

PROTECTED_NAMESPACES = {"kube-system", "kube-public", "sentinel-arena", "monitoring"}

FORBIDDEN_ACTION_TYPES = {
    "host_escape",        # Container escape to host
    "node_exec",          # Execute on the node directly
    "etcd_access",        # Direct etcd database access
    "delete_all",         # Mass deletion
    "apiserver_exploit",  # Direct API server exploit
    "dns_hijack",         # Cluster DNS manipulation
}

BLAST_RADIUS_LIMIT = 0.75  # Any action affecting > 75% of cluster is denied

# Severity of OPA violation
VIOLATION_SEVERITY = {
    "protected_namespace": "CRITICAL",
    "forbidden_action_type": "CRITICAL",
    "blast_radius_exceeded": "HIGH",
    "target_not_found": "MEDIUM",
    "rate_limit_exceeded": "HIGH",
    "invalid_action_format": "MEDIUM",
}


# ─────────────────────────────────────────────────────────────────────────────
# Policy Rules
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_red_action(action: Dict[str, Any], rate_count: int = 0) -> Tuple[bool, str, str]:
    """
    Main OPA policy evaluation function.
    Equivalent to: allow { ... } in Rego

    Returns:
        (allowed: bool, reason: str, severity: str)
    """
    violations = []

    # ── Rule 1: Protected namespace check ─────────────────────────────────────
    target_ns = action.get("target_namespace", "")
    if target_ns in PROTECTED_NAMESPACES:
        violations.append(("protected_namespace", f"Namespace '{target_ns}' is protected"))

    # ── Rule 2: Forbidden action type check ──────────────────────────────────
    action_type = action.get("vuln_type", action.get("type", ""))
    method = action.get("method", "").lower()
    for forbidden in FORBIDDEN_ACTION_TYPES:
        if forbidden in method or forbidden == action_type:
            violations.append(("forbidden_action_type", f"Action type '{forbidden}' is forbidden"))

    # ── Rule 3: Blast radius limit ────────────────────────────────────────────
    blast_radius = action.get("blast_radius", 0.0)
    if blast_radius > BLAST_RADIUS_LIMIT:
        violations.append(("blast_radius_exceeded",
                           f"Blast radius {blast_radius:.2f} exceeds limit {BLAST_RADIUS_LIMIT}"))

    # ── Rule 4: Action format validation ──────────────────────────────────────
    required_fields = ["target_namespace", "target_resource", "method"]
    missing = [f for f in required_fields if not action.get(f)]
    if missing:
        violations.append(("invalid_action_format", f"Missing required fields: {missing}"))

    # ── Rule 5: Rate limit check ──────────────────────────────────────────────
    if rate_count >= 2:
        violations.append(("rate_limit_exceeded",
                           f"Red Agent has made {rate_count} actions this round (limit: 2)"))

    # ── Decision ──────────────────────────────────────────────────────────────
    if violations:
        # Return the highest severity violation
        severity_order = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
        top_violation = max(violations,
                            key=lambda v: severity_order.get(VIOLATION_SEVERITY.get(v[0], "LOW"), 0))
        return False, top_violation[1], VIOLATION_SEVERITY.get(top_violation[0], "MEDIUM")

    return True, "all_policies_satisfied", "NONE"


def evaluate_escalation_attempt(action: Dict[str, Any],
                                 attack_history: list) -> Tuple[bool, str]:
    """
    Escalation guard — detects if Red is trying to escalate beyond sandbox scope.
    Returns (is_escalation: bool, reason: str)
    """
    method_lower = action.get("method", "").lower()
    rationale_lower = action.get("rationale", "").lower()
    combined = method_lower + " " + rationale_lower

    escalation_keywords = [
        "host filesystem", "/proc/1", "nsenter", "chroot",
        "real cluster", "production cluster", "escape sandbox",
        "aws metadata", "169.254.169.254",  # Cloud metadata
        "etcd", "api-server certificate",
    ]

    for keyword in escalation_keywords:
        if keyword in combined:
            return True, f"Escalation attempt detected: '{keyword}' in action"

    return False, ""


def build_opa_decision_log(action: Dict[str, Any],
                            allowed: bool, reason: str,
                            severity: str, round_num: int) -> Dict[str, Any]:
    """Create a structured OPA decision log entry."""
    return {
        "round": round_num,
        "timestamp": __import__("datetime").datetime.now().isoformat(),
        "action_type": action.get("vuln_type", "unknown"),
        "target": f"{action.get('target_namespace', '?')}/{action.get('target_resource', '?')}",
        "blast_radius": action.get("blast_radius", 0.0),
        "decision": "ALLOW" if allowed else "DENY",
        "reason": reason,
        "severity": severity,
        "policy_version": "1.0.0",
    }
