"""
NeuralOps Prometheus Metrics Fetcher — Phase 2a
================================================
Queries a live Prometheus instance via the HTTP API to build the
(window_size, n_features=12) NumPy array expected by the LSTM model.

Gracefully falls back to synthetic data if Prometheus is unreachable.

Usage:
    from neuralops.prediction.prometheus_fetcher import PrometheusMetricsFetcher

    fetcher = PrometheusMetricsFetcher("http://localhost:9090")
    window = fetcher.fetch_window("my-pod", "default", window_size=60, step_seconds=15)
    # window.shape == (60, 12)
"""
import sys
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any, Tuple

import numpy as np
import requests
from requests.exceptions import ConnectionError, Timeout, RequestException

logger = logging.getLogger(__name__)

# ── Feature index mapping (must match lstm_model.FEATURE_NAMES) ───────────────
FEATURE_INDEX = {
    "memory_usage_bytes":  0,
    "memory_limit_bytes":  1,
    "memory_usage_pct":    2,
    "cpu_usage_cores":     3,
    "cpu_limit_cores":     4,
    "cpu_usage_pct":       5,
    "restart_count":       6,
    "network_rx_bytes":    7,
    "network_tx_bytes":    8,
    "disk_usage_bytes":    9,
    "http_error_rate":     10,
    "http_latency_p99":    11,
}
N_FEATURES = 12


class PrometheusConnectionError(Exception):
    """Raised when Prometheus cannot be reached."""


class PrometheusMetricsFetcher:
    """
    Queries Prometheus range API to build the LSTM input feature matrix.

    Parameters
    ----------
    prometheus_url : str
        Base URL of the Prometheus server (default: http://localhost:9090).
    timeout_seconds : int
        HTTP request timeout (default: 10s).
    """

    QUERY_RANGE_PATH = "/api/v1/query_range"
    HEALTH_PATH = "/api/v1/query"

    def __init__(
        self,
        prometheus_url: str = "http://localhost:9090",
        timeout_seconds: int = 10,
    ):
        self.url = prometheus_url.rstrip("/")
        self.timeout = timeout_seconds
        self._session = requests.Session()
        self._session.headers.update({"Accept": "application/json"})
        self._available: Optional[bool] = None   # cached connectivity state

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    def is_available(self) -> bool:
        """Quick health-check ping to Prometheus."""
        try:
            resp = self._session.get(
                self.url + self.HEALTH_PATH,
                params={"query": "1"},
                timeout=5,
            )
            self._available = resp.status_code == 200
        except (ConnectionError, Timeout):
            self._available = False
        return self._available

    def fetch_window(
        self,
        pod_name: str,
        namespace: str,
        window_size: int = 60,
        step_seconds: int = 15,
        end_time: Optional[datetime] = None,
    ) -> np.ndarray:
        """
        Fetch a metrics window from Prometheus and return a
        (window_size, N_FEATURES) NumPy float32 array.

        Falls back to synthetic data if Prometheus is unreachable.

        Parameters
        ----------
        pod_name      : K8s pod name (supports regex via PromQL =~).
        namespace     : K8s namespace.
        window_size   : Number of timesteps in the returned window.
        step_seconds  : PromQL step size (seconds). Governs data resolution.
        end_time      : Window end time (default: now UTC).

        Returns
        -------
        np.ndarray of shape (window_size, 12), dtype=float32
        """
        if not self.is_available():
            logger.warning(
                "Prometheus not reachable at %s — using synthetic fallback", self.url
            )
            return self._synthetic_window(pod_name, namespace, window_size)

        end_time = end_time or datetime.now(tz=timezone.utc)
        start_time = end_time - timedelta(seconds=window_size * step_seconds)

        matrix = np.zeros((window_size, N_FEATURES), dtype=np.float32)
        timestamps_ref: Optional[List[float]] = None

        for feature_name, col_idx in FEATURE_INDEX.items():
            query = self._build_query(feature_name, pod_name, namespace)
            if query is None:
                continue  # derived feature — computed later

            try:
                values, ts = self._query_range(query, start_time, end_time, step_seconds)
                if timestamps_ref is None and ts:
                    timestamps_ref = ts
                aligned = self._align_series(values, ts, window_size)
                matrix[:, col_idx] = aligned
            except Exception as exc:
                logger.error("Failed to fetch %s: %s", feature_name, exc)
                # Leave column as zeros; will be filled by forward-fill below

        # Derived features
        self._compute_derived(matrix)

        # Forward-fill any remaining zeros (from failed queries)
        matrix = self._forward_fill(matrix)

        logger.info(
            "Fetched Prometheus window: pod=%s/%s shape=%s",
            namespace, pod_name, matrix.shape,
        )
        return matrix

    # ─────────────────────────────────────────────────────────────────────────
    # PromQL query builders
    # ─────────────────────────────────────────────────────────────────────────

    def _build_query(self, feature: str, pod: str, ns: str) -> Optional[str]:
        """Return the PromQL expression for a given feature name."""
        # Derived features are computed locally — no direct query
        if feature in ("memory_usage_pct", "cpu_usage_pct",
                       "http_error_rate", "http_latency_p99"):
            return None

        queries: Dict[str, str] = {
            "memory_usage_bytes": (
                f'sum(container_memory_usage_bytes'
                f'{{pod=~"{pod}.*",namespace="{ns}",container!=""}})'
            ),
            "memory_limit_bytes": (
                f'sum(container_spec_memory_limit_bytes'
                f'{{pod=~"{pod}.*",namespace="{ns}",container!=""}})'
            ),
            "cpu_usage_cores": (
                f'sum(rate(container_cpu_usage_seconds_total'
                f'{{pod=~"{pod}.*",namespace="{ns}",container!=""}}[1m]))'
            ),
            "cpu_limit_cores": (
                f'sum(container_spec_cpu_quota'
                f'{{pod=~"{pod}.*",namespace="{ns}",container!=""}} / '
                f'container_spec_cpu_period'
                f'{{pod=~"{pod}.*",namespace="{ns}",container!=""}})'
            ),
            "restart_count": (
                f'sum(kube_pod_container_status_restarts_total'
                f'{{pod=~"{pod}.*",namespace="{ns}"}})'
            ),
            "network_rx_bytes": (
                f'sum(rate(container_network_receive_bytes_total'
                f'{{pod=~"{pod}.*",namespace="{ns}"}}[1m]))'
            ),
            "network_tx_bytes": (
                f'sum(rate(container_network_transmit_bytes_total'
                f'{{pod=~"{pod}.*",namespace="{ns}"}}[1m]))'
            ),
            "disk_usage_bytes": (
                f'sum(container_fs_usage_bytes'
                f'{{pod=~"{pod}.*",namespace="{ns}",container!=""}})'
            ),
        }
        return queries.get(feature)

    # ─────────────────────────────────────────────────────────────────────────
    # HTTP helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _query_range(
        self,
        query: str,
        start: datetime,
        end: datetime,
        step: int,
    ) -> Tuple[List[float], List[float]]:
        """
        Execute a PromQL range query.

        Returns (values, timestamps) as parallel lists.
        Raises RequestException on HTTP errors.
        """
        params = {
            "query": query,
            "start": start.timestamp(),
            "end":   end.timestamp(),
            "step":  f"{step}s",
        }
        resp = self._session.get(
            self.url + self.QUERY_RANGE_PATH,
            params=params,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != "success":
            raise RequestException(f"Prometheus error: {data.get('error', 'unknown')}")

        result = data.get("data", {}).get("result", [])
        if not result:
            return [], []

        # Flatten the first time series (we aggregate with sum() already)
        raw_pairs = result[0].get("values", [])
        timestamps = [float(p[0]) for p in raw_pairs]
        values     = [float(p[1]) if p[1] != "NaN" else 0.0 for p in raw_pairs]
        return values, timestamps

    # ─────────────────────────────────────────────────────────────────────────
    # Signal processing helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _align_series(
        self,
        values: List[float],
        timestamps: List[float],
        window_size: int,
    ) -> np.ndarray:
        """
        Align a variable-length raw series to exactly `window_size` points.
        - If longer: take the most recent `window_size` samples.
        - If shorter: left-pad with the first value (or zero).
        """
        arr = np.array(values, dtype=np.float32)
        if len(arr) == 0:
            return np.zeros(window_size, dtype=np.float32)
        if len(arr) >= window_size:
            return arr[-window_size:]
        # Pad left
        pad_len = window_size - len(arr)
        pad_val = arr[0] if len(arr) > 0 else 0.0
        return np.concatenate([np.full(pad_len, pad_val, dtype=np.float32), arr])

    def _compute_derived(self, matrix: np.ndarray) -> None:
        """Compute ratio features in-place."""
        # memory_usage_pct = usage / limit (avoid div-by-zero)
        mem_limit = np.where(matrix[:, 1] > 0, matrix[:, 1], 1.0)
        matrix[:, 2] = np.clip(matrix[:, 0] / mem_limit, 0.0, 1.0)

        # cpu_usage_pct = usage / limit
        cpu_limit = np.where(matrix[:, 4] > 0, matrix[:, 4], 1.0)
        matrix[:, 5] = np.clip(matrix[:, 3] / cpu_limit, 0.0, 1.0)

        # http_error_rate — default to 0.01 (1% baseline) if unavailable
        if np.all(matrix[:, 10] == 0):
            matrix[:, 10] = 0.01

        # http_latency_p99 — default to 50ms baseline if unavailable
        if np.all(matrix[:, 11] == 0):
            matrix[:, 11] = 50.0

    def _forward_fill(self, matrix: np.ndarray) -> np.ndarray:
        """
        Forward-fill zero columns to avoid NaN/zero artifacts from
        temporarily unavailable Prometheus series.
        """
        for col in range(matrix.shape[1]):
            series = matrix[:, col]
            if np.any(series != 0):
                # Forward fill within the series
                last_valid = series[0]
                for i in range(len(series)):
                    if series[i] == 0 and i > 0:
                        series[i] = last_valid
                    else:
                        last_valid = series[i]
                matrix[:, col] = series
        return matrix

    # ─────────────────────────────────────────────────────────────────────────
    # Synthetic fallback (identical to Phase 1 generator)
    # ─────────────────────────────────────────────────────────────────────────

    def _synthetic_window(
        self,
        pod_name: str,
        namespace: str,
        window_size: int,
    ) -> np.ndarray:
        """Generate a synthetic metrics window for offline / demo use."""
        rng = np.random.default_rng(seed=abs(hash(f"{namespace}/{pod_name}")) % (2**31))
        t = np.arange(window_size, dtype=np.float32)

        mem_usage  = 200e6 + t * 1.5e6 + rng.standard_normal(window_size) * 5e6
        mem_limit  = np.full(window_size, 512e6, dtype=np.float32)
        mem_pct    = mem_usage / mem_limit

        cpu_usage  = (0.1 + rng.standard_normal(window_size) * 0.03).astype(np.float32)
        cpu_limit  = np.full(window_size, 0.5, dtype=np.float32)
        cpu_pct    = (cpu_usage / cpu_limit).astype(np.float32)

        restarts   = np.cumsum(rng.poisson(0.01, window_size)).astype(np.float32)
        net_rx     = np.abs(rng.standard_normal(window_size) * 1e6).astype(np.float32)
        net_tx     = np.abs(rng.standard_normal(window_size) * 5e5).astype(np.float32)
        disk       = (t * 5000 + rng.standard_normal(window_size) * 1000).astype(np.float32)
        http_err   = (0.01 + rng.standard_normal(window_size) * 0.005).astype(np.float32)
        http_lat   = (50.0 + rng.standard_normal(window_size) * 10).astype(np.float32)

        return np.column_stack([
            mem_usage, mem_limit, mem_pct,
            cpu_usage, cpu_limit, cpu_pct,
            restarts, net_rx, net_tx, disk,
            http_err, http_lat,
        ]).astype(np.float32)


# ─────────────────────────────────────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("=" * 60)
    print("  PrometheusMetricsFetcher -- Self Test")
    print("=" * 60)

    fetcher = PrometheusMetricsFetcher("http://localhost:9090")

    print(f"\n  Prometheus available: {fetcher.is_available()}")
    print("  (Will fall back to synthetic data if not reachable)")

    window = fetcher.fetch_window("test-pod", "default", window_size=60, step_seconds=15)
    print(f"\n  Window shape:  {window.shape}   (expected: (60, 12))")
    print(f"  dtype:         {window.dtype}")
    print(f"  memory_usage   first/last: {window[0,0]:.0f} / {window[-1,0]:.0f}")
    print(f"  cpu_usage      first/last: {window[0,3]:.4f} / {window[-1,3]:.4f}")
    print(f"  memory_pct     first/last: {window[0,2]:.3f} / {window[-1,2]:.3f}")
    print(f"  restart_count  first/last: {window[0,6]:.0f} / {window[-1,6]:.0f}")
    print(f"\n  Feature mins:  {window.min(axis=0).round(2)}")
    print(f"  Feature maxes: {window.max(axis=0).round(2)}")
    print("\n" + "=" * 60)
