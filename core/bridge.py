"""
AIRA Bridge — Connects SentinelArena and NeuralOps subsystems.

Integration points:
  1. NeuralOps → SentinelArena:
     - When NeuralOps detects an anomaly, it pushes an alert to the Blue Agent's
       context so Blue can proactively patch before Red exploits it.

  2. SentinelArena → NeuralOps:
     - When Red Agent successfully exploits a pod, NeuralOps flags that pod
       for priority monitoring (higher scan frequency, lower alert thresholds).

  3. Shared Event Stream:
     - Both subsystems emit events through the bridge, which aggregates them
       into a unified timeline for the dashboard.

Usage:
    from core.bridge import AIRABridge

    bridge = AIRABridge()

    # SentinelArena notifies bridge of successful Red attack
    bridge.notify_attack_success("webapp-pod", "default", "cve", "CVE-2019-20372")

    # Blue Agent queries bridge for NeuralOps alerts before acting
    alerts = bridge.get_neuralops_alerts_for_blue()

    # NeuralOps orchestrator notifies bridge of anomaly
    bridge.notify_anomaly_detected("webapp-pod", "default", "memory_leak", 0.92)
"""
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("aira.bridge")


class BridgeEvent:
    """Unified event from either SentinelArena or NeuralOps."""

    def __init__(
        self,
        source: str,           # "sentinel" | "neuralops"
        event_type: str,
        pod_name: str,
        namespace: str,
        data: Dict[str, Any],
        message: str = "",
    ):
        self.timestamp = datetime.utcnow().isoformat()
        self.source = source
        self.event_type = event_type
        self.pod_name = pod_name
        self.namespace = namespace
        self.data = data
        self.message = message

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "source": self.source,
            "event_type": self.event_type,
            "pod_name": self.pod_name,
            "namespace": self.namespace,
            "data": self.data,
            "message": self.message,
        }


class AIRABridge:
    """
    Central integration hub between SentinelArena and NeuralOps.

    Maintains:
    - A unified event stream from both subsystems
    - A list of NeuralOps anomaly alerts for Blue Agent consumption
    - A list of SentinelArena attack notifications for NeuralOps priority flagging
    """

    def __init__(self):
        self.event_stream: List[BridgeEvent] = []

        # NeuralOps → SentinelArena: anomaly alerts for Blue Agent
        self._anomaly_alerts: List[Dict[str, Any]] = []

        # SentinelArena → NeuralOps: pods flagged after successful attacks
        self._flagged_pods: List[Dict[str, Any]] = []

        # Reference to NeuralOps orchestrator (lazy-loaded)
        self._orchestrator = None

        logger.info("AIRABridge initialized")

    # ─── Orchestrator Integration ────────────────────────────────────────────

    def connect_orchestrator(self, orchestrator) -> None:
        """Connect the NeuralOps orchestrator instance for direct communication."""
        self._orchestrator = orchestrator
        logger.info("Bridge connected to NeuralOps orchestrator")

    # ─── SentinelArena → NeuralOps ───────────────────────────────────────────

    def notify_attack_success(
        self,
        pod_name: str,
        namespace: str,
        vuln_type: str,
        vuln_id: str = "",
        blast_radius: float = 0.0,
    ) -> None:
        """
        Called by SentinelArena when Red Agent successfully exploits a pod.
        Flags the pod for priority monitoring in NeuralOps.
        """
        entry = {
            "pod_name": pod_name,
            "namespace": namespace,
            "vuln_type": vuln_type,
            "vuln_id": vuln_id,
            "blast_radius": blast_radius,
            "timestamp": datetime.utcnow().isoformat(),
        }
        self._flagged_pods.append(entry)

        self._emit_event(
            source="sentinel",
            event_type="attack_success_notification",
            pod_name=pod_name,
            namespace=namespace,
            data=entry,
            message=(
                f"🔴→🧠 Red Agent exploited {namespace}/{pod_name} "
                f"({vuln_type}: {vuln_id}) — flagging for priority monitoring"
            ),
        )

        # If orchestrator is connected, flag the pod directly
        if self._orchestrator:
            self._orchestrator.flag_priority_pod(
                pod_name, namespace,
                reason=f"Red Agent exploit: {vuln_type} ({vuln_id})",
            )

    def notify_attack_blocked(
        self,
        pod_name: str,
        namespace: str,
        vuln_type: str,
        block_reason: str,
    ) -> None:
        """
        Called when OPA blocks a Red Agent attack. Informational only —
        no priority flagging needed since the attack didn't succeed.
        """
        self._emit_event(
            source="sentinel",
            event_type="attack_blocked_notification",
            pod_name=pod_name,
            namespace=namespace,
            data={"vuln_type": vuln_type, "block_reason": block_reason},
            message=f"🛡️ OPA blocked attack on {namespace}/{pod_name}: {block_reason}",
        )

    # ─── NeuralOps → SentinelArena ───────────────────────────────────────────

    def notify_anomaly_detected(
        self,
        pod_name: str,
        namespace: str,
        failure_class: str,
        confidence: float,
        ttf_minutes: Optional[float] = None,
    ) -> None:
        """
        Called by NeuralOps when LSTM detects an anomaly.
        Pushes an alert for Blue Agent to consume.
        """
        alert = {
            "pod_name": pod_name,
            "namespace": namespace,
            "failure_class": failure_class,
            "confidence": confidence,
            "ttf_minutes": ttf_minutes,
            "timestamp": datetime.utcnow().isoformat(),
            "consumed": False,
        }
        self._anomaly_alerts.append(alert)

        self._emit_event(
            source="neuralops",
            event_type="anomaly_alert",
            pod_name=pod_name,
            namespace=namespace,
            data=alert,
            message=(
                f"🧠→🔵 Anomaly alert: {failure_class} on {namespace}/{pod_name} "
                f"(confidence: {confidence:.0%}, TTF: {ttf_minutes or '?'}min)"
            ),
        )

    def notify_healing_completed(
        self,
        pod_name: str,
        namespace: str,
        action: str,
        success: bool,
    ) -> None:
        """Called by NeuralOps after a healing action completes."""
        self._emit_event(
            source="neuralops",
            event_type="healing_completed",
            pod_name=pod_name,
            namespace=namespace,
            data={"action": action, "success": success},
            message=(
                f"🧠 Healing {'✅ succeeded' if success else '❌ failed'}: "
                f"{action} on {namespace}/{pod_name}"
            ),
        )

    # ─── Blue Agent Consumption ──────────────────────────────────────────────

    def get_neuralops_alerts_for_blue(self) -> List[Dict[str, Any]]:
        """
        Return unconsumed NeuralOps anomaly alerts for Blue Agent.
        Marks them as consumed after retrieval.
        """
        unconsumed = [a for a in self._anomaly_alerts if not a.get("consumed")]
        for alert in unconsumed:
            alert["consumed"] = True
        return unconsumed

    def format_alerts_for_blue_prompt(self) -> str:
        """
        Format NeuralOps alerts as a text block for insertion into
        the Blue Agent's LLM prompt.
        """
        alerts = self.get_neuralops_alerts_for_blue()
        if not alerts:
            return ""

        lines = ["NEURALOPS ANOMALY ALERTS (from LSTM prediction engine):"]
        for a in alerts:
            ttf = f"{a['ttf_minutes']:.0f}min" if a.get("ttf_minutes") else "unknown"
            lines.append(
                f"  ⚠️ {a['failure_class'].upper()} detected on "
                f"{a['namespace']}/{a['pod_name']} "
                f"(confidence: {a['confidence']:.0%}, TTF: {ttf})"
            )
        lines.append(
            "Consider pre-emptive defense for these pods before Red Agent exploits them."
        )
        return "\n".join(lines)

    # ─── Unified Event Stream ────────────────────────────────────────────────

    def get_event_stream(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Return the unified event stream (most recent first)."""
        return [e.to_dict() for e in self.event_stream[-limit:]]

    def get_stats(self) -> Dict[str, Any]:
        """Return bridge statistics."""
        return {
            "total_events": len(self.event_stream),
            "pending_anomaly_alerts": sum(
                1 for a in self._anomaly_alerts if not a.get("consumed")
            ),
            "total_anomaly_alerts": len(self._anomaly_alerts),
            "flagged_pods": len(self._flagged_pods),
            "orchestrator_connected": self._orchestrator is not None,
        }

    # ─── Internal ────────────────────────────────────────────────────────────

    def _emit_event(
        self,
        source: str,
        event_type: str,
        pod_name: str,
        namespace: str,
        data: Dict[str, Any],
        message: str,
    ) -> None:
        """Create and store a bridge event."""
        event = BridgeEvent(source, event_type, pod_name, namespace, data, message)
        self.event_stream.append(event)
        logger.info("[%s] %s", source.upper(), message)


# ─────────────────────────────────────────────────────────────────────────────
# Global Bridge Instance
# ─────────────────────────────────────────────────────────────────────────────

_global_bridge: Optional[AIRABridge] = None


def get_bridge() -> AIRABridge:
    """Get or create the global bridge instance."""
    global _global_bridge
    if _global_bridge is None:
        _global_bridge = AIRABridge()
    return _global_bridge
