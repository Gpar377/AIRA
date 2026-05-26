"""
NeuralOps Healing Agent — LangGraph-powered autonomous remediation.

Pipeline:
    PREDICT → DIAGNOSE → DECIDE → HEAL → REMEMBER

Each stage is a LangGraph node. The agent:
  1. Takes a PredictionResult from the LSTM
  2. Diagnoses root cause using LLM reasoning
  3. Decides action based on tiered autonomy (auto / notify / escalate)
  4. Executes remediation via K8s client
  5. Stores outcome in memory for future learning

Tiered Autonomy:
  - TIER_1 (auto):    confidence >= 0.85 AND past success rate > 0.8 → just do it
  - TIER_2 (notify):  confidence >= 0.65 → do it, but notify human
  - TIER_3 (escalate): confidence < 0.65 OR destructive action → wait for human
"""
import time
from datetime import datetime
from typing import Optional, Dict, Any, TypedDict, Literal
from dataclasses import dataclass, field

from langgraph.graph import StateGraph, END

from neuralops.prediction.lstm_model import PredictionResult


# ─────────────────────────────────────────────────────────────────────────────
# Agent State
# ─────────────────────────────────────────────────────────────────────────────

class HealingState(TypedDict):
    """Shared state across all healing pipeline nodes."""
    # Input
    prediction: Dict[str, Any]       # PredictionResult as dict
    pod_name: str
    namespace: str

    # Diagnosis
    root_cause: str
    diagnosis_confidence: float
    relevant_context: str

    # Decision
    autonomy_tier: str               # "TIER_1" | "TIER_2" | "TIER_3"
    chosen_action: str
    action_params: Dict[str, Any]
    requires_human: bool

    # Execution
    action_executed: bool
    action_success: bool
    action_result: str
    execution_time_seconds: float

    # Memory
    incident_id: Optional[int]
    similar_incidents_found: int
    past_success_rate: float

    # Meta
    events: list                     # log of events for streaming
    error: Optional[str]


# ─────────────────────────────────────────────────────────────────────────────
# Remediation Action Catalog
# ─────────────────────────────────────────────────────────────────────────────

REMEDIATION_CATALOG = {
    "memory_leak": {
        "primary": "pod_restart",
        "secondary": "scale_up",
        "description": "Restart leaking pod, scale replicas if restart fails",
        "destructive": False,
    },
    "cpu_throttle": {
        "primary": "scale_up",
        "secondary": "resource_increase",
        "description": "Add replicas to spread load, increase CPU limits",
        "destructive": False,
    },
    "cascading_timeout": {
        "primary": "circuit_break",
        "secondary": "pod_restart",
        "description": "Enable circuit breaker, restart affected pods",
        "destructive": False,
    },
    "disk_pressure": {
        "primary": "cleanup_logs",
        "secondary": "pvc_expand",
        "description": "Clean temp files and old logs, expand PVC if available",
        "destructive": False,
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Node 1: PREDICT (entry point — receive prediction from LSTM)
# ─────────────────────────────────────────────────────────────────────────────

def predict_node(state: HealingState) -> HealingState:
    """
    Entry node — validates incoming prediction and initializes pipeline state.
    The actual LSTM prediction happens BEFORE the agent is invoked.
    """
    pred = state["prediction"]

    state["events"].append({
        "timestamp": datetime.utcnow().isoformat(),
        "node": "predict",
        "message": f"[PREDICT] {pred['failure_class']} detected on "
                   f"{state['namespace']}/{state['pod_name']} | "
                   f"Confidence: {pred['confidence']:.0%} | "
                   f"TTF: {pred.get('time_to_failure_minutes', '?')} min",
    })

    return state


# ─────────────────────────────────────────────────────────────────────────────
# Node 2: DIAGNOSE (root cause analysis)
# ─────────────────────────────────────────────────────────────────────────────

def diagnose_node(state: HealingState) -> HealingState:
    """
    Diagnose root cause.
    Phase 1: Rule-based diagnosis from failure class.
    Phase 2+: LLM-powered with Prometheus/Loki/Jaeger context.
    """
    pred = state["prediction"]
    failure = pred["failure_class"]
    conf = pred["confidence"]

    # Rule-based root cause mapping (Phase 1)
    ROOT_CAUSE_MAP = {
        "memory_leak": {
            "cause": "Container memory growing linearly without release - likely unbounded "
                     "cache, connection pool leak, or buffer accumulation",
            "indicators": "memory_usage_pct rising steadily, restart_count stable",
        },
        "cpu_throttle": {
            "cause": "CPU usage hitting cgroup limits - periodic computation spike or "
                     "runaway thread consuming all available CPU shares",
            "indicators": "cpu_usage_pct spiking periodically, throttle_count increasing",
        },
        "cascading_timeout": {
            "cause": "Downstream service latency propagating upstream - likely database "
                     "slowdown or network partition causing retry storms",
            "indicators": "http_latency_p99 exponential growth, error_rate climbing",
        },
        "disk_pressure": {
            "cause": "Disk usage approaching capacity - log accumulation, temp files not "
                     "cleaned, or PVC undersized for workload",
            "indicators": "disk_usage_bytes growing steadily, inode count rising",
        },
    }

    diagnosis = ROOT_CAUSE_MAP.get(failure, {
        "cause": f"Unknown failure pattern: {failure}",
        "indicators": "No specific indicators matched",
    })

    state["root_cause"] = diagnosis["cause"]
    state["diagnosis_confidence"] = conf
    state["relevant_context"] = diagnosis["indicators"]

    state["events"].append({
        "timestamp": datetime.utcnow().isoformat(),
        "node": "diagnose",
        "message": f"[DIAGNOSE] Root cause: {diagnosis['cause'][:80]}... | "
                   f"Confidence: {conf:.0%}",
    })

    return state


# ─────────────────────────────────────────────────────────────────────────────
# Node 3: DECIDE (tiered autonomy)
# ─────────────────────────────────────────────────────────────────────────────

def decide_node(state: HealingState) -> HealingState:
    """
    Choose remediation action and autonomy tier.

    Tiered autonomy prevents the agent from doing destructive things
    without human approval:
      TIER_1: Auto-execute (high confidence + proven remedy)
      TIER_2: Execute + notify (medium confidence)
      TIER_3: Escalate to human (low confidence or destructive)
    """
    pred = state["prediction"]
    failure = pred["failure_class"]
    conf = pred["confidence"]
    past_rate = state.get("past_success_rate", 0.0)

    catalog = REMEDIATION_CATALOG.get(failure, {
        "primary": "pod_restart",
        "secondary": "scale_up",
        "destructive": False,
    })

    is_destructive = catalog.get("destructive", False)

    # Tier decision logic
    if conf >= 0.85 and past_rate >= 0.8 and not is_destructive:
        tier = "TIER_1"
        action = catalog["primary"]
        requires_human = False
    elif conf >= 0.65 and not is_destructive:
        tier = "TIER_2"
        action = catalog["primary"]
        requires_human = False  # execute, but notify
    else:
        tier = "TIER_3"
        action = catalog["primary"]
        requires_human = True   # wait for human

    state["autonomy_tier"] = tier
    state["chosen_action"] = action
    state["requires_human"] = requires_human
    state["action_params"] = {
        "failure_class": failure,
        "target_pod": state["pod_name"],
        "target_namespace": state["namespace"],
        "catalog_entry": catalog,
    }

    tier_labels = {
        "TIER_1": "AUTO-EXECUTE",
        "TIER_2": "EXECUTE + NOTIFY",
        "TIER_3": "ESCALATE TO HUMAN",
    }

    state["events"].append({
        "timestamp": datetime.utcnow().isoformat(),
        "node": "decide",
        "message": f"[DECIDE] {tier_labels[tier]} | Action: {action} | "
                   f"Past success rate: {past_rate:.0%}",
    })

    return state


# ─────────────────────────────────────────────────────────────────────────────
# Node 4: HEAL (execute remediation)
# ─────────────────────────────────────────────────────────────────────────────

def heal_node(state: HealingState) -> HealingState:
    """
    Execute the chosen remediation action.
    Phase 1: Mock execution (logs what would happen).
    Phase 2: Real kubectl via k8s_client.
    """
    if state["requires_human"]:
        state["action_executed"] = False
        state["action_success"] = False
        state["action_result"] = "Escalated to human — awaiting manual approval"
        state["execution_time_seconds"] = 0.0

        state["events"].append({
            "timestamp": datetime.utcnow().isoformat(),
            "node": "heal",
            "message": f"[HEAL] SKIPPED — escalated to human operator",
        })
        return state

    start = time.time()
    action = state["chosen_action"]
    pod = state["pod_name"]
    ns = state["namespace"]

    # ── Mock execution (Phase 1) ─────────────────────────────────────
    # In Phase 2, these call real k8s_client methods
    success = True
    result = ""

    if action == "pod_restart":
        result = f"kubectl delete pod {pod} -n {ns} (mock: pod would restart)"
    elif action == "scale_up":
        result = f"kubectl scale deployment --replicas=+1 -n {ns} (mock: replicas increased)"
    elif action == "resource_increase":
        result = f"kubectl patch deployment -n {ns} -p resources.limits.cpu=1000m (mock)"
    elif action == "circuit_break":
        result = f"Applied circuit breaker config to {pod} in {ns} (mock)"
    elif action == "cleanup_logs":
        result = f"kubectl exec {pod} -n {ns} -- rm -rf /tmp/logs/* (mock: logs cleaned)"
    elif action == "pvc_expand":
        result = f"kubectl patch pvc -n {ns} --patch storage=20Gi (mock: PVC expanded)"
    else:
        result = f"Unknown action: {action}"
        success = False

    elapsed = time.time() - start

    state["action_executed"] = True
    state["action_success"] = success
    state["action_result"] = result
    state["execution_time_seconds"] = round(elapsed, 3)

    status_str = "[OK]" if success else "[ERROR]"
    state["events"].append({
        "timestamp": datetime.utcnow().isoformat(),
        "node": "heal",
        "message": f"[HEAL] {status_str} {action} on {ns}/{pod} | {result}",
    })

    return state


# ─────────────────────────────────────────────────────────────────────────────
# Node 5: REMEMBER (store outcome in memory)
# ─────────────────────────────────────────────────────────────────────────────

def remember_node(state: HealingState) -> HealingState:
    """
    Store incident and outcome in PostgreSQL memory.
    Phase 1: Log only (no DB connection required).
    Phase 2: Uses neuralops.memory.store.MemoryStore.
    """
    # Phase 1: Just log the learning
    outcome = "SUCCESS" if state.get("action_success") else "FAILED"

    learning_entry = {
        "failure_class": state["prediction"]["failure_class"],
        "pod": state["pod_name"],
        "namespace": state["namespace"],
        "root_cause": state.get("root_cause", "unknown"),
        "action_taken": state.get("chosen_action", "none"),
        "autonomy_tier": state.get("autonomy_tier", "unknown"),
        "outcome": outcome,
        "confidence": state["prediction"]["confidence"],
        "timestamp": datetime.utcnow().isoformat(),
    }

    state["events"].append({
        "timestamp": datetime.utcnow().isoformat(),
        "node": "remember",
        "message": f"[REMEMBER] Stored: {learning_entry['failure_class']} "
                   f"-> {learning_entry['action_taken']} -> {outcome} | "
                   f"Next time: {'skip trial-and-error' if outcome == 'SUCCESS' else 'try secondary action'}",
    })

    return state


# ─────────────────────────────────────────────────────────────────────────────
# Graph Assembly
# ─────────────────────────────────────────────────────────────────────────────

def build_healing_graph() -> StateGraph:
    """
    Build the NeuralOps healing pipeline.

    Flow:
        predict → diagnose → decide → heal → remember → END
    """
    graph = StateGraph(HealingState)

    # Add nodes
    graph.add_node("predict",  predict_node)
    graph.add_node("diagnose", diagnose_node)
    graph.add_node("decide",   decide_node)
    graph.add_node("heal",     heal_node)
    graph.add_node("remember", remember_node)

    # Linear flow
    graph.set_entry_point("predict")
    graph.add_edge("predict",  "diagnose")
    graph.add_edge("diagnose", "decide")
    graph.add_edge("decide",   "heal")
    graph.add_edge("heal",     "remember")
    graph.add_edge("remember", END)

    return graph.compile()


# ─────────────────────────────────────────────────────────────────────────────
# Runner — Convenience function
# ─────────────────────────────────────────────────────────────────────────────

def run_healing_pipeline(prediction: PredictionResult) -> HealingState:
    """
    Run the full healing pipeline on a prediction result.

    Args:
        prediction: PredictionResult from the LSTM engine

    Returns:
        Final HealingState with all events logged
    """
    graph = build_healing_graph()

    initial_state: HealingState = {
        "prediction": {
            "failure_class": prediction.failure_class,
            "confidence": prediction.confidence,
            "time_to_failure_minutes": prediction.time_to_failure_minutes,
            "all_probabilities": prediction.all_probabilities,
            "is_anomaly": prediction.is_anomaly,
            "anomaly_score": prediction.anomaly_score,
        },
        "pod_name": prediction.pod_name,
        "namespace": prediction.namespace,
        "root_cause": "",
        "diagnosis_confidence": 0.0,
        "relevant_context": "",
        "autonomy_tier": "",
        "chosen_action": "",
        "action_params": {},
        "requires_human": False,
        "action_executed": False,
        "action_success": False,
        "action_result": "",
        "execution_time_seconds": 0.0,
        "incident_id": None,
        "similar_incidents_found": 0,
        "past_success_rate": 0.0,
        "events": [],
        "error": None,
    }

    final_state = graph.invoke(initial_state)
    return final_state


# ─────────────────────────────────────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Simulate a prediction result and run the healing pipeline
    fake_prediction = PredictionResult(
        failure_class="memory_leak",
        confidence=0.92,
        time_to_failure_minutes=8.5,
        all_probabilities={
            "memory_leak": 0.92,
            "cpu_throttle": 0.05,
            "cascading_timeout": 0.02,
            "disk_pressure": 0.01,
        },
        is_anomaly=True,
        anomaly_score=0.88,
        pod_name="webapp-pod-7f8b9c",
        namespace="production",
        timestamp=datetime.utcnow().isoformat(),
    )

    print("\n" + "=" * 60)
    print("  NeuralOps Healing Agent — Self-Test")
    print("=" * 60 + "\n")

    result = run_healing_pipeline(fake_prediction)

    for event in result["events"]:
        print(f"  {event['message']}")

    print(f"\n  Autonomy Tier: {result['autonomy_tier']}")
    print(f"  Action:        {result['chosen_action']}")
    print(f"  Executed:      {result['action_executed']}")
    print(f"  Success:       {result['action_success']}")
    print(f"  Result:        {result['action_result']}")
    print("\n" + "=" * 60)
