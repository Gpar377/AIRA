"""
ArenaState — Shared TypedDict state passed through the LangGraph pipeline.
Every node reads from and writes to this structure.
"""
from typing import TypedDict, List, Dict, Any, Optional


class VulnFinding(TypedDict):
    id: str                  # e.g. "CVE-2019-9511" or "RBAC-001"
    resource: str            # e.g. "nginx:1.14.0" or "pod-reader-role"
    namespace: str
    vuln_type: str           # cve | rbac | secret | network | privilege
    severity: str            # CRITICAL | HIGH | MEDIUM | LOW
    description: str
    cvss_score: float
    exploitable: bool
    patched: bool            # True once Blue patches it


class AttackAction(TypedDict):
    round: int
    vuln_type: str           # Maps to VulnFinding.vuln_type
    target_namespace: str
    target_resource: str
    method: str              # Specific technique used
    rationale: str           # LLM-generated reasoning
    blast_radius: float      # 0.0 (minimal) – 1.0 (catastrophic)
    chained_from: Optional[str]   # Vulnerability ID this came from
    opa_decision: str        # allowed | blocked
    opa_reason: str
    outcome: str             # success | blocked_opa | blocked_blue | failed


class DefenseAction(TypedDict):
    round: int
    defense_type: str        # rbac_patch | secret_rotation | network_policy | pod_restart | image_update
    target_namespace: str
    target_resource: str
    method: str
    rationale: str
    pre_emptive: bool        # True = proactive, False = reactive
    outcome: str
    score_delta: float       # How much it reduced the attack surface score


class ArenaEvent(TypedDict):
    timestamp: str
    round: int
    agent: str               # red | blue | orchestrator | system
    event_type: str          # scan | propose_attack | opa_check | execute | patch | round_end | kill_switch
    message: str
    data: Dict[str, Any]     # Structured payload for this event


class ArenaState(TypedDict):
    # Round tracking
    round: int
    max_rounds: int

    # Cluster representation
    cluster: Dict[str, Any]

    # Vulnerability landscape
    vulnerabilities: List[VulnFinding]

    # Red agent
    proposed_attack: Optional[AttackAction]
    attacks: List[AttackAction]
    red_action_count: int

    # Blue agent
    defenses: List[DefenseAction]
    alerts: List[Dict[str, Any]]

    # Scoring
    attack_surface_score: float
    score_history: List[float]

    # Governance
    opa_decisions: List[Dict[str, Any]]
    kill_switch: bool
    spiral_counter: int
    last_attack_type: Optional[str]

    # Cross-round memory (learning loop)
    memory: Dict[str, Any]

    # System status
    status: str              # running | stopped | completed

    # Event stream (for display and future WebSocket)
    events: List[ArenaEvent]
