"""
NeuralOps Inference Pipeline — Connects LSTM predictions to the healing agent.

Usage:
    from neuralops.prediction.inference import InferencePipeline

    pipeline = InferencePipeline(model_path="neuralops/models/lstm_checkpoint.pt")
    result = pipeline.predict_from_metrics(metrics_window, pod_name, namespace)

    if pipeline.should_heal(result):
        healing_state = pipeline.trigger_healing(result)

Phase 1: Accepts raw numpy arrays (from synthetic data or manual test).
Phase 2: Pulls live metrics from Prometheus HTTP API automatically.
"""
import numpy as np
import time
from typing import Optional, Dict, List
from datetime import datetime

from neuralops.prediction.lstm_model import (
    PredictionResult, PredictionEngine, get_prediction_engine,
    FEATURE_NAMES, N_FEATURES,
)
from neuralops.agent.healing_agent import run_healing_pipeline, HealingState


class InferencePipeline:
    """
    End-to-end inference: metrics → LSTM → healing agent.

    Holds model state, normalization stats, and provides
    a clean API for both manual and automated usage.
    """

    def __init__(self, model_path: Optional[str] = None):
        self.engine = get_prediction_engine(model_path)
        self.prediction_history: List[PredictionResult] = []
        self.healing_history: List[HealingState] = []
        self._alert_count = 0

    def predict_from_metrics(
        self,
        metrics_window: np.ndarray,
        pod_name: str = "unknown",
        namespace: str = "default",
    ) -> PredictionResult:
        """
        Run LSTM inference on a metrics window.

        Args:
            metrics_window: (window_size, n_features) numpy array
            pod_name: K8s pod name
            namespace: K8s namespace

        Returns:
            PredictionResult with class, confidence, TTF, anomaly score
        """
        result = self.engine.predict(metrics_window, pod_name, namespace)
        self.prediction_history.append(result)
        return result

    def should_heal(self, result: PredictionResult) -> bool:
        """Check if a prediction should trigger the healing pipeline."""
        return self.engine.should_alert(result)

    def trigger_healing(self, result: PredictionResult) -> HealingState:
        """
        Run the full healing agent on a prediction.

        Returns:
            Final HealingState with events, action taken, and outcome
        """
        self._alert_count += 1
        state = run_healing_pipeline(result)
        self.healing_history.append(state)
        return state

    def predict_and_heal(
        self,
        metrics_window: np.ndarray,
        pod_name: str = "unknown",
        namespace: str = "default",
    ) -> Dict:
        """
        Full pipeline: predict + auto-heal if needed.

        Returns:
            Dict with prediction, healed (bool), and healing state
        """
        prediction = self.predict_from_metrics(metrics_window, pod_name, namespace)

        healing_state = None
        healed = False

        if self.should_heal(prediction):
            healing_state = self.trigger_healing(prediction)
            healed = healing_state.get("action_success", False)

        return {
            "prediction": prediction,
            "triggered_healing": healing_state is not None,
            "healed": healed,
            "healing_state": healing_state,
        }

    def get_stats(self) -> Dict:
        """Pipeline stats for monitoring."""
        total_predictions = len(self.prediction_history)
        total_healings = len(self.healing_history)
        successful_healings = sum(
            1 for h in self.healing_history if h.get("action_success")
        )

        return {
            "total_predictions": total_predictions,
            "total_healings": total_healings,
            "successful_healings": successful_healings,
            "success_rate": successful_healings / total_healings if total_healings > 0 else 0.0,
            "alert_count": self._alert_count,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Prometheus Metrics Fetcher (Phase 2 stub)
# ─────────────────────────────────────────────────────────────────────────────

class PrometheusMetricsFetcher:
    """
    Phase 2: Fetches real-time metrics from Prometheus and formats them
    into the (window_size, n_features) array the LSTM expects.

    Phase 1: Generates synthetic windows for testing.
    """

    def __init__(self, prometheus_url: str = "http://localhost:9090"):
        self.url = prometheus_url

    def fetch_window(
        self,
        pod_name: str,
        namespace: str,
        window_size: int = 60,
        step_seconds: int = 5,
    ) -> np.ndarray:
        """
        Phase 2 will query:
            container_memory_usage_bytes{pod="X", namespace="Y"}[5m]
            container_cpu_usage_seconds_total{...}
            ...etc for all 12 features

        Phase 1: Returns synthetic data for testing.
        """
        # Phase 1 — synthetic test data
        t = np.arange(window_size)
        return np.column_stack([
            200e6 + t * 1.5e6 + np.random.randn(window_size) * 5e6,    # memory_usage_bytes
            np.full(window_size, 512e6),                                  # memory_limit_bytes
            (200e6 + t * 1.5e6) / 512e6,                                # memory_usage_pct
            0.1 + np.random.randn(window_size) * 0.03,                  # cpu_usage_cores
            np.full(window_size, 0.5),                                   # cpu_limit_cores
            0.2 + np.random.randn(window_size) * 0.06,                  # cpu_usage_pct
            np.cumsum(np.random.poisson(0.01, window_size)),             # restart_count
            np.abs(np.random.randn(window_size) * 1e6),                 # network_rx_bytes
            np.abs(np.random.randn(window_size) * 5e5),                 # network_tx_bytes
            t * 5000 + np.random.randn(window_size) * 1000,             # disk_usage_bytes
            0.01 + np.random.randn(window_size) * 0.005,                # http_error_rate
            50 + np.random.randn(window_size) * 10,                     # http_latency_p99
        ])


# ─────────────────────────────────────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  NeuralOps Inference Pipeline — Self-Test")
    print("=" * 60 + "\n")

    # Test with untrained model (random predictions)
    pipeline = InferencePipeline()
    fetcher = PrometheusMetricsFetcher()

    # Simulate 3 pods
    test_pods = [
        ("webapp-pod-7f8b9c", "production"),
        ("db-pod-3a4f21", "production"),
        ("cache-pod-9e1b3d", "staging"),
    ]

    for pod, ns in test_pods:
        window = fetcher.fetch_window(pod, ns)
        result = pipeline.predict_and_heal(window, pod, ns)

        pred = result["prediction"]
        print(f"  Pod: {ns}/{pod}")
        print(f"    Prediction:  {pred.failure_class} ({pred.confidence:.0%})")
        print(f"    Anomaly:     {'YES' if pred.is_anomaly else 'no'} ({pred.anomaly_score:.0%})")
        print(f"    TTF:         {pred.time_to_failure_minutes or 'N/A'} min")
        print(f"    Triggered:   {result['triggered_healing']}")

        if result["healing_state"]:
            hs = result["healing_state"]
            print(f"    Tier:        {hs['autonomy_tier']}")
            print(f"    Action:      {hs['chosen_action']}")
            print(f"    Success:     {hs['action_success']}")
        print()

    stats = pipeline.get_stats()
    print(f"  Pipeline stats: {stats}")
    print("\n" + "=" * 60)
