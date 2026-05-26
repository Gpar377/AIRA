"""
NeuralOps Kubernetes + Log Diagnostics Client — Phase 2c
==========================================================
Extends the base K8s client with:
  - Loki log fetcher  (/loki/api/v1/query_range)
  - Jaeger trace fetcher  (/api/traces)

These are used by the LLM healing agent to gather root-cause evidence
around an anomaly window before choosing a remediation action.

Usage:
    from neuralops.k8s_client.client import KubernetesClient

    kc = KubernetesClient(namespace="production")

    # Get container logs around an anomaly window
    logs = kc.get_loki_logs("webapp", "production", lookback_minutes=10)

    # Get Jaeger traces for latency RCA
    traces = kc.get_jaeger_traces("webapp", lookback_minutes=10)
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any

import requests
from requests.exceptions import ConnectionError, Timeout

# Kubernetes SDK (graceful import)
try:
    from kubernetes import client, config
    from kubernetes.client.rest import ApiException
    _K8S_AVAILABLE = True
except ImportError:
    _K8S_AVAILABLE = False

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# KubernetesClient
# ─────────────────────────────────────────────────────────────────────────────

class KubernetesClient:
    """
    Wrapper for Kubernetes API operations, extended with
    Loki log fetching and Jaeger trace fetching for RCA.
    """

    def __init__(
        self,
        in_cluster: bool = False,
        namespace: str = "default",
        loki_url: str = "http://localhost:3100",
        jaeger_url: str = "http://localhost:16686",
    ):
        """
        Initialize Kubernetes client.

        Args:
            in_cluster  : Whether running inside a K8s cluster.
            namespace   : Default namespace for operations.
            loki_url    : Loki base URL (default: http://localhost:3100).
            jaeger_url  : Jaeger query UI URL (default: http://localhost:16686).
        """
        self.namespace = namespace
        self.loki_url = loki_url.rstrip("/")
        self.jaeger_url = jaeger_url.rstrip("/")
        self._http = requests.Session()
        self._http.headers.update({"Accept": "application/json"})

        if _K8S_AVAILABLE:
            try:
                if in_cluster:
                    config.load_incluster_config()
                else:
                    config.load_kube_config()
                self.core_v1 = client.CoreV1Api()
                self.apps_v1 = client.AppsV1Api()
                self._k8s_ready = True
                logger.info("k8s client ready: namespace=%s", namespace)
            except Exception as exc:
                logger.warning("kubeconfig not available: %s", exc)
                self.core_v1 = None
                self.apps_v1 = None
                self._k8s_ready = False
        else:
            self.core_v1 = None
            self.apps_v1 = None
            self._k8s_ready = False

    # ─────────────────────────────────────────────────────────────────────────
    # Kubernetes core operations
    # ─────────────────────────────────────────────────────────────────────────

    async def get_pod_metrics(self, pod_name: str, namespace: Optional[str] = None) -> Dict:
        """Get current status and restart count for a pod."""
        ns = namespace or self.namespace
        if not self._k8s_ready:
            return {"error": "k8s not available", "pod": pod_name, "namespace": ns}
        try:
            pod = self.core_v1.read_namespaced_pod(name=pod_name, namespace=ns)
            return {
                "name": pod.metadata.name,
                "namespace": pod.metadata.namespace,
                "status": pod.status.phase,
                "containers": [
                    {
                        "name": c.name,
                        "ready": c.ready,
                        "restart_count": c.restart_count,
                        "state": str(c.state),
                    }
                    for c in (pod.status.container_statuses or [])
                ],
            }
        except ApiException as exc:
            logger.error("get_pod_metrics failed: pod=%s err=%s", pod_name, exc)
            raise

    async def restart_pod(self, pod_name: str, namespace: Optional[str] = None) -> bool:
        """Restart a pod by deleting it (Deployment controller will recreate)."""
        ns = namespace or self.namespace
        if not self._k8s_ready:
            return False
        try:
            self.core_v1.delete_namespaced_pod(
                name=pod_name,
                namespace=ns,
                body=client.V1DeleteOptions(),
            )
            logger.info("pod_restarted: pod=%s namespace=%s", pod_name, ns)
            return True
        except ApiException as exc:
            logger.error("restart_pod failed: pod=%s err=%s", pod_name, exc)
            return False

    async def scale_deployment(
        self,
        deployment_name: str,
        replicas: int,
        namespace: Optional[str] = None,
    ) -> bool:
        """Scale a Deployment to the specified replica count."""
        ns = namespace or self.namespace
        if not self._k8s_ready:
            return False
        try:
            deployment = self.apps_v1.read_namespaced_deployment(
                name=deployment_name, namespace=ns
            )
            deployment.spec.replicas = replicas
            self.apps_v1.patch_namespaced_deployment(
                name=deployment_name, namespace=ns, body=deployment
            )
            logger.info("deployment_scaled: name=%s replicas=%d", deployment_name, replicas)
            return True
        except ApiException as exc:
            logger.error("scale_deployment failed: name=%s err=%s", deployment_name, exc)
            return False

    async def get_deployment_status(
        self,
        deployment_name: str,
        namespace: Optional[str] = None,
    ) -> Dict:
        """Get current status of a Deployment."""
        ns = namespace or self.namespace
        if not self._k8s_ready:
            return {"error": "k8s not available", "deployment": deployment_name}
        try:
            dep = self.apps_v1.read_namespaced_deployment(
                name=deployment_name, namespace=ns
            )
            return {
                "name": dep.metadata.name,
                "namespace": dep.metadata.namespace,
                "replicas": dep.spec.replicas,
                "ready_replicas": dep.status.ready_replicas or 0,
                "available_replicas": dep.status.available_replicas or 0,
                "conditions": [
                    {"type": c.type, "status": c.status, "reason": c.reason}
                    for c in (dep.status.conditions or [])
                ],
            }
        except ApiException as exc:
            logger.error("get_deployment_status failed: name=%s err=%s", deployment_name, exc)
            raise

    async def list_pods(
        self,
        namespace: Optional[str] = None,
        label_selector: Optional[str] = None,
    ) -> List[Dict]:
        """List all pods in a namespace."""
        ns = namespace or self.namespace
        if not self._k8s_ready:
            return []
        try:
            pods = self.core_v1.list_namespaced_pod(
                namespace=ns, label_selector=label_selector
            )
            return [
                {
                    "name": pod.metadata.name,
                    "namespace": pod.metadata.namespace,
                    "status": pod.status.phase,
                    "labels": pod.metadata.labels,
                }
                for pod in pods.items
            ]
        except ApiException as exc:
            logger.error("list_pods failed: err=%s", exc)
            raise

    # ─────────────────────────────────────────────────────────────────────────
    # Phase 2c — Loki log fetcher
    # ─────────────────────────────────────────────────────────────────────────

    def get_loki_logs(
        self,
        container: str,
        namespace: str,
        lookback_minutes: int = 15,
        limit: int = 200,
        level_filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Fetch recent container logs from Loki via the LogQL API.

        Args:
            container        : Container name (used in LogQL label).
            namespace        : Kubernetes namespace.
            lookback_minutes : How far back to search (default: 15 min).
            limit            : Maximum log lines to return (default: 200).
            level_filter     : Optional log level filter, e.g. "error", "warn".

        Returns:
            Dict with keys:
                - source: "loki" | "unavailable"
                - lines: list of {"timestamp": str, "line": str}
                - error: str (only on failure)
        """
        end_ns   = int(datetime.now(tz=timezone.utc).timestamp() * 1e9)
        start_ns = end_ns - int(lookback_minutes * 60 * 1e9)

        logql = f'{{namespace="{namespace}",container="{container}"}}'
        if level_filter:
            logql += f' |= "{level_filter}"'

        params = {
            "query": logql,
            "start": str(start_ns),
            "end":   str(end_ns),
            "limit": str(limit),
            "direction": "backward",
        }

        try:
            resp = self._http.get(
                f"{self.loki_url}/loki/api/v1/query_range",
                params=params,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

            results = data.get("data", {}).get("result", [])
            lines = []
            for stream in results:
                for ts, line in stream.get("values", []):
                    ts_sec = int(ts) / 1e9
                    dt_str = datetime.fromtimestamp(ts_sec, tz=timezone.utc).isoformat()
                    lines.append({"timestamp": dt_str, "line": line})

            # Sort chronologically
            lines.sort(key=lambda x: x["timestamp"])
            logger.info(
                "Loki logs: container=%s/%s lines=%d", namespace, container, len(lines)
            )
            return {"source": "loki", "lines": lines, "count": len(lines)}

        except (ConnectionError, Timeout):
            logger.warning("Loki not reachable at %s", self.loki_url)
            return {"source": "unavailable", "lines": [], "error": "Loki unreachable"}
        except Exception as exc:
            logger.error("Loki query failed: %s", exc)
            return {"source": "unavailable", "lines": [], "error": str(exc)}

    # ─────────────────────────────────────────────────────────────────────────
    # Phase 2c — Jaeger trace fetcher
    # ─────────────────────────────────────────────────────────────────────────

    def get_jaeger_traces(
        self,
        service: str,
        lookback_minutes: int = 15,
        operation: Optional[str] = None,
        min_duration_ms: int = 0,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """
        Fetch recent Jaeger traces for a service to diagnose latency bottlenecks.

        Args:
            service           : Jaeger service name (typically matches container).
            lookback_minutes  : How far back to search (default: 15 min).
            operation         : Filter by specific operation name (optional).
            min_duration_ms   : Return only traces slower than this (default: 0 = all).
            limit             : Max traces to fetch (default: 20).

        Returns:
            Dict with keys:
                - source: "jaeger" | "unavailable"
                - traces: list of trace summaries (traceID, duration_ms, spans, operations)
                - error: str (only on failure)
        """
        end_us   = int(datetime.now(tz=timezone.utc).timestamp() * 1e6)
        start_us = end_us - int(lookback_minutes * 60 * 1e6)

        params: Dict[str, Any] = {
            "service": service,
            "start": str(start_us),
            "end":   str(end_us),
            "limit": str(limit),
        }
        if operation:
            params["operation"] = operation
        if min_duration_ms > 0:
            params["minDuration"] = f"{min_duration_ms}ms"

        try:
            resp = self._http.get(
                f"{self.jaeger_url}/api/traces",
                params=params,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

            raw_traces = data.get("data", [])
            summaries = []
            for trace in raw_traces:
                spans = trace.get("spans", [])
                if not spans:
                    continue
                # Duration from first span
                root_span = spans[0]
                duration_us = root_span.get("duration", 0)
                operations = list({s.get("operationName", "") for s in spans})
                summaries.append({
                    "traceID": trace.get("traceID", ""),
                    "duration_ms": round(duration_us / 1000, 2),
                    "span_count": len(spans),
                    "operations": operations[:5],  # top 5
                    "start_time": datetime.fromtimestamp(
                        root_span.get("startTime", 0) / 1e6, tz=timezone.utc
                    ).isoformat(),
                })

            # Sort by duration descending (slowest first)
            summaries.sort(key=lambda x: x["duration_ms"], reverse=True)

            logger.info("Jaeger traces: service=%s count=%d", service, len(summaries))
            return {"source": "jaeger", "traces": summaries, "count": len(summaries)}

        except (ConnectionError, Timeout):
            logger.warning("Jaeger not reachable at %s", self.jaeger_url)
            return {"source": "unavailable", "traces": [], "error": "Jaeger unreachable"}
        except Exception as exc:
            logger.error("Jaeger query failed: %s", exc)
            return {"source": "unavailable", "traces": [], "error": str(exc)}

    # ─────────────────────────────────────────────────────────────────────────
    # Aggregated diagnostics helper
    # ─────────────────────────────────────────────────────────────────────────

    def gather_diagnostics(
        self,
        pod_name: str,
        namespace: str,
        lookback_minutes: int = 15,
    ) -> Dict[str, Any]:
        """
        Collect all available diagnostic data for the LLM healing agent:
          - Loki error logs
          - Jaeger slow traces
          - Kubernetes pod events (via core_v1)

        Returns a structured dict the LLM can reason over.
        """
        diag: Dict[str, Any] = {
            "pod": pod_name,
            "namespace": namespace,
            "lookback_minutes": lookback_minutes,
        }

        # Loki error logs
        diag["logs"] = self.get_loki_logs(
            container=pod_name,
            namespace=namespace,
            lookback_minutes=lookback_minutes,
            level_filter="error",
        )

        # Jaeger slow traces (>200ms)
        diag["traces"] = self.get_jaeger_traces(
            service=pod_name,
            lookback_minutes=lookback_minutes,
            min_duration_ms=200,
        )

        # K8s events
        if self._k8s_ready:
            try:
                events = self.core_v1.list_namespaced_event(
                    namespace=namespace,
                    field_selector=f"involvedObject.name={pod_name}",
                )
                diag["k8s_events"] = [
                    {
                        "reason": e.reason,
                        "message": e.message,
                        "type": e.type,
                        "count": e.count,
                        "last_seen": str(e.last_timestamp),
                    }
                    for e in (events.items or [])
                ]
            except Exception as exc:
                diag["k8s_events"] = {"error": str(exc)}
        else:
            diag["k8s_events"] = {"error": "k8s not available"}

        return diag


# ─────────────────────────────────────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("  NeuralOps K8s + Log Diagnostics Client -- Self Test")
    print("=" * 60)

    kc = KubernetesClient(
        namespace="default",
        loki_url="http://localhost:3100",
        jaeger_url="http://localhost:16686",
    )

    print(f"\n  k8s ready:  {kc._k8s_ready}")
    print(f"  Loki URL:   {kc.loki_url}")
    print(f"  Jaeger URL: {kc.jaeger_url}")

    logs = kc.get_loki_logs("webapp", "default", lookback_minutes=5)
    print(f"\n  Loki source:  {logs['source']}")
    print(f"  Log lines:    {logs.get('count', 0)}")

    traces = kc.get_jaeger_traces("webapp", lookback_minutes=5)
    print(f"\n  Jaeger source: {traces['source']}")
    print(f"  Traces found:  {traces.get('count', 0)}")

    print("\n  gather_diagnostics (offline mode):")
    diag = kc.gather_diagnostics("webapp", "default", lookback_minutes=5)
    print(f"    logs.source:   {diag['logs']['source']}")
    print(f"    traces.source: {diag['traces']['source']}")
    print(f"    k8s_events:    {diag['k8s_events']}")
    print("=" * 60)
