"""
NeuralOps Orchestrator — Main prediction→heal monitoring loop.

Continuously monitors Kubernetes pods by:
1. Discovering target pods (from config or K8s API)
2. Pulling metrics for each pod (Prometheus or synthetic fallback)
3. Running LSTM inference to detect anomalies
4. Dispatching the healing agent when anomalies are found
5. Logging all predictions and healing actions

Modes:
  - `run_once()`:  Single-pass scan of all pods (for integration testing)
  - `run_loop()`:  Continuous monitoring with configurable interval
  - `run_for_pods()`: Scan a specific list of pods (for bridge integration)
"""
import logging
import time
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

from neuralops.prediction.inference import InferencePipeline
from neuralops.config import settings

logger = logging.getLogger("neuralops.orchestrator")


# ─────────────────────────────────────────────────────────────────────────────
# Pod Discovery
# ─────────────────────────────────────────────────────────────────────────────

# Default pods to monitor (matching the infra/demo-services deployments)
DEFAULT_MONITORED_PODS = [
    ("memory-leak-pod", "default"),
    ("cpu-throttle-pod", "default"),
    ("disk-pressure-pod", "default"),
    ("cascading-timeout-pod", "default"),
]


def discover_pods(
    namespace: str = "default",
    use_k8s_api: bool = False,
) -> List[Tuple[str, str]]:
    """
    Discover pods to monitor.

    Phase 1: Returns default demo-service pods.
    Phase 2: Queries K8s API for all running pods in namespace.

    Returns:
        List of (pod_name, namespace) tuples
    """
    if use_k8s_api:
        try:
            from neuralops.k8s_client.client import K8sClient
            client = K8sClient()
            pods = client.list_pods(namespace=namespace)
            if pods:
                return [(p["name"], p.get("namespace", namespace)) for p in pods]
            logger.warning("K8s API returned no pods, falling back to defaults")
        except Exception as e:
            logger.warning("K8s API unavailable (%s), falling back to defaults", e)

    return DEFAULT_MONITORED_PODS


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrator Event Log
# ─────────────────────────────────────────────────────────────────────────────

class OrchestratorEvent:
    """Structured event from the orchestrator for logging and bridge integration."""

    def __init__(
        self,
        event_type: str,
        pod_name: str,
        namespace: str,
        data: Dict[str, Any],
        message: str = "",
    ):
        self.timestamp = datetime.utcnow().isoformat()
        self.event_type = event_type
        self.pod_name = pod_name
        self.namespace = namespace
        self.data = data
        self.message = message

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "pod_name": self.pod_name,
            "namespace": self.namespace,
            "data": self.data,
            "message": self.message,
        }


# ─────────────────────────────────────────────────────────────────────────────
# NeuralOps Orchestrator
# ─────────────────────────────────────────────────────────────────────────────

class NeuralOpsOrchestrator:
    """
    Main orchestration engine for the NeuralOps self-healing subsystem.

    Manages the lifecycle of:
    - Pod discovery
    - Metric ingestion
    - LSTM anomaly prediction
    - Healing agent dispatch
    - Event logging
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        prometheus_url: Optional[str] = None,
        poll_interval: Optional[int] = None,
    ):
        self.pipeline = InferencePipeline(model_path=model_path)
        self.prometheus_url = prometheus_url or settings.PROMETHEUS_URL
        self.poll_interval = poll_interval or settings.PREDICTION_INTERVAL_SECONDS

        self.event_log: List[OrchestratorEvent] = []
        self.scan_count = 0
        self._running = False

        # Priority boost list — pods flagged by SentinelArena for closer monitoring
        self._priority_pods: List[Tuple[str, str]] = []

        logger.info(
            "NeuralOpsOrchestrator initialized | prometheus=%s | interval=%ds",
            self.prometheus_url, self.poll_interval,
        )

    # ── External Interface (for Bridge) ──────────────────────────────────────

    def flag_priority_pod(self, pod_name: str, namespace: str, reason: str = "") -> None:
        """
        Flag a pod for priority monitoring (called by SentinelArena bridge
        when Red Agent successfully attacks a pod).
        """
        entry = (pod_name, namespace)
        if entry not in self._priority_pods:
            self._priority_pods.append(entry)
            self._emit_event(
                "priority_flagged", pod_name, namespace,
                {"reason": reason},
                f"⚠️ Pod {namespace}/{pod_name} flagged for priority monitoring: {reason}",
            )

    def get_active_alerts(self) -> List[Dict[str, Any]]:
        """
        Return recent anomaly alerts (for Blue Agent consumption via bridge).
        Returns alerts from the last scan cycle only.
        """
        return [
            e.to_dict() for e in self.event_log
            if e.event_type in ("anomaly_detected", "healing_triggered")
        ]

    def get_stats(self) -> Dict[str, Any]:
        """Return orchestrator statistics."""
        pipeline_stats = self.pipeline.get_stats()
        return {
            "scan_count": self.scan_count,
            "total_events": len(self.event_log),
            "priority_pods": len(self._priority_pods),
            "running": self._running,
            **pipeline_stats,
        }

    # ── Core Scan Logic ──────────────────────────────────────────────────────

    def run_once(
        self,
        pods: Optional[List[Tuple[str, str]]] = None,
        use_k8s_api: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Single-pass scan: discover pods → predict → heal.

        Args:
            pods: Optional explicit pod list. If None, auto-discovers.
            use_k8s_api: Whether to use K8s API for pod discovery.

        Returns:
            List of result dicts for each pod scanned.
        """
        self.scan_count += 1
        scan_id = f"scan-{self.scan_count}"

        # Discover pods (merge priority pods with discovered pods)
        if pods is None:
            pods = discover_pods(use_k8s_api=use_k8s_api)

        all_pods = list(set(pods + self._priority_pods))

        self._emit_event(
            "scan_started", "orchestrator", "system",
            {"scan_id": scan_id, "pod_count": len(all_pods)},
            f"🔍 Scan #{self.scan_count}: monitoring {len(all_pods)} pods",
        )

        results = []
        for pod_name, namespace in all_pods:
            result = self._scan_pod(pod_name, namespace, scan_id)
            results.append(result)

        # Summary
        anomalies = sum(1 for r in results if r.get("is_anomaly"))
        healings = sum(1 for r in results if r.get("triggered_healing"))

        self._emit_event(
            "scan_completed", "orchestrator", "system",
            {
                "scan_id": scan_id,
                "pods_scanned": len(results),
                "anomalies_detected": anomalies,
                "healings_triggered": healings,
            },
            f"✅ Scan #{self.scan_count} complete: {len(results)} pods, "
            f"{anomalies} anomalies, {healings} healings",
        )

        return results

    def run_for_pods(self, pods: List[Tuple[str, str]]) -> List[Dict[str, Any]]:
        """Convenience: scan a specific list of pods (used by bridge)."""
        return self.run_once(pods=pods)

    def run_loop(self, max_iterations: Optional[int] = None) -> None:
        """
        Continuous monitoring loop.

        Args:
            max_iterations: If set, stop after N scan cycles. None = run forever.
        """
        self._running = True
        iteration = 0

        print("\n" + "=" * 60)
        print("  🧠 NeuralOps Orchestrator — Continuous Monitoring")
        print(f"  Poll interval: {self.poll_interval}s")
        print(f"  Max iterations: {max_iterations or '∞'}")
        print("=" * 60 + "\n")

        try:
            while self._running:
                iteration += 1

                if max_iterations and iteration > max_iterations:
                    logger.info("Max iterations (%d) reached, stopping", max_iterations)
                    break

                results = self.run_once()

                # Print summary
                anomalies = sum(1 for r in results if r.get("is_anomaly"))
                if anomalies > 0:
                    print(f"  ⚠️  Scan #{self.scan_count}: {anomalies} anomalies detected")
                else:
                    print(f"  ✅ Scan #{self.scan_count}: all pods healthy")

                if self._running and (not max_iterations or iteration < max_iterations):
                    time.sleep(self.poll_interval)

        except KeyboardInterrupt:
            print("\n  ⏹️  Orchestrator stopped by user")
        finally:
            self._running = False
            print(f"\n  📊 Final stats: {self.get_stats()}")

    def stop(self) -> None:
        """Gracefully stop the monitoring loop."""
        self._running = False

    # ── Internal Helpers ─────────────────────────────────────────────────────

    def _scan_pod(self, pod_name: str, namespace: str, scan_id: str) -> Dict[str, Any]:
        """Run prediction + optional healing for a single pod."""
        try:
            result = self.pipeline.predict_from_live(
                pod_name=pod_name,
                namespace=namespace,
                prometheus_url=self.prometheus_url,
            )

            prediction = result["prediction"]
            is_anomaly = prediction.is_anomaly
            is_priority = (pod_name, namespace) in self._priority_pods

            if is_anomaly:
                self._emit_event(
                    "anomaly_detected", pod_name, namespace,
                    {
                        "failure_class": prediction.failure_class,
                        "confidence": prediction.confidence,
                        "anomaly_score": prediction.anomaly_score,
                        "ttf_minutes": prediction.time_to_failure_minutes,
                        "is_priority": is_priority,
                        "data_source": result.get("data_source", "unknown"),
                    },
                    f"🚨 Anomaly: {prediction.failure_class} on {namespace}/{pod_name} "
                    f"(confidence: {prediction.confidence:.0%}, "
                    f"TTF: {prediction.time_to_failure_minutes or '?'}min)"
                    f"{' [PRIORITY]' if is_priority else ''}",
                )

            if result.get("triggered_healing"):
                healing = result.get("healing_state", {})
                self._emit_event(
                    "healing_triggered", pod_name, namespace,
                    {
                        "action": healing.get("chosen_action", "unknown"),
                        "tier": healing.get("autonomy_tier", "unknown"),
                        "success": healing.get("action_success", False),
                    },
                    f"🔧 Healing: {healing.get('chosen_action', '?')} "
                    f"({healing.get('autonomy_tier', '?')}) → "
                    f"{'✅ Success' if healing.get('action_success') else '❌ Failed'}",
                )

            return {
                "pod_name": pod_name,
                "namespace": namespace,
                "scan_id": scan_id,
                "is_anomaly": is_anomaly,
                "failure_class": prediction.failure_class if is_anomaly else "healthy",
                "confidence": prediction.confidence,
                "triggered_healing": result.get("triggered_healing", False),
                "healed": result.get("healed", False),
                "data_source": result.get("data_source", "unknown"),
            }

        except Exception as e:
            logger.error("Error scanning pod %s/%s: %s", namespace, pod_name, e)
            self._emit_event(
                "scan_error", pod_name, namespace,
                {"error": str(e)},
                f"❌ Error scanning {namespace}/{pod_name}: {e}",
            )
            return {
                "pod_name": pod_name,
                "namespace": namespace,
                "scan_id": scan_id,
                "is_anomaly": False,
                "error": str(e),
            }

    def _emit_event(
        self,
        event_type: str,
        pod_name: str,
        namespace: str,
        data: Dict[str, Any],
        message: str,
    ) -> None:
        """Create and store an orchestrator event."""
        event = OrchestratorEvent(event_type, pod_name, namespace, data, message)
        self.event_log.append(event)
        logger.info(message)


# ─────────────────────────────────────────────────────────────────────────────
# Module-level convenience
# ─────────────────────────────────────────────────────────────────────────────

_global_orchestrator: Optional[NeuralOpsOrchestrator] = None


def get_orchestrator(**kwargs) -> NeuralOpsOrchestrator:
    """Get or create the global orchestrator instance."""
    global _global_orchestrator
    if _global_orchestrator is None:
        _global_orchestrator = NeuralOpsOrchestrator(**kwargs)
    return _global_orchestrator


# ─────────────────────────────────────────────────────────────────────────────
# CLI Entry Point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="NeuralOps Orchestrator")
    parser.add_argument("--once", action="store_true", help="Run a single scan pass")
    parser.add_argument("--interval", type=int, default=30, help="Poll interval in seconds")
    parser.add_argument("--max-iterations", type=int, default=None, help="Max scan cycles")
    parser.add_argument("--prometheus", type=str, default="http://localhost:9090")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

    orch = NeuralOpsOrchestrator(
        prometheus_url=args.prometheus,
        poll_interval=args.interval,
    )

    if args.once:
        results = orch.run_once()
        print(f"\n  Results: {len(results)} pods scanned")
        for r in results:
            status = "🚨 ANOMALY" if r.get("is_anomaly") else "✅ healthy"
            print(f"    {r['namespace']}/{r['pod_name']}: {status}")
    else:
        orch.run_loop(max_iterations=args.max_iterations)
