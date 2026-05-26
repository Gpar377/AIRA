"""
NeuralOps Inference Pipeline — Connects LSTM predictions to the healing agent.

Usage:
    from neuralops.prediction.inference import InferencePipeline

    pipeline = InferencePipeline(model_path="neuralops/models/lstm_checkpoint.pt")
    result = pipeline.predict_from_metrics(metrics_window, pod_name, namespace)

    if pipeline.should_heal(result):
        healing_state = pipeline.trigger_healing(result)

    # Phase 2 — pull live Prometheus metrics automatically:
    result = pipeline.predict_from_live(pod_name, namespace)

Phase 1: Accepts raw numpy arrays (from synthetic data or manual test).
Phase 2: Pulls live metrics from Prometheus HTTP API automatically via
         prometheus_fetcher.PrometheusMetricsFetcher.
"""
import logging
import numpy as np
import time
from typing import Optional, Dict, List
from datetime import datetime

from neuralops.prediction.lstm_model import (
    PredictionResult, PredictionEngine, get_prediction_engine,
    FEATURE_NAMES, N_FEATURES,
)
from neuralops.agent.healing_agent import run_healing_pipeline, HealingState
from neuralops.prediction.prometheus_fetcher import PrometheusMetricsFetcher

logger = logging.getLogger(__name__)


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

    # ─────────────────────────────────────────────────────────────────────────
    # Phase 2 — Live Prometheus integration
    # ─────────────────────────────────────────────────────────────────────────

    def predict_from_live(
        self,
        pod_name: str,
        namespace: str = "default",
        prometheus_url: str = "http://localhost:9090",
        window_size: int = 60,
        step_seconds: int = 15,
    ) -> Dict:
        """
        Phase 2 entry point — fetches real Prometheus metrics and runs the
        full predict + heal pipeline.

        Falls back to synthetic data if Prometheus is unreachable.

        Args:
            pod_name:       K8s pod name
            namespace:      K8s namespace
            prometheus_url: Prometheus base URL
            window_size:    Number of timesteps (default: 60)
            step_seconds:   PromQL step resolution (default: 15s)

        Returns:
            Dict with prediction, triggered_healing, healed, healing_state,
            and a 'data_source' key ('prometheus' | 'synthetic').
        """
        fetcher = PrometheusMetricsFetcher(
            prometheus_url=prometheus_url,
        )
        live = fetcher.is_available()
        window = fetcher.fetch_window(
            pod_name, namespace,
            window_size=window_size,
            step_seconds=step_seconds,
        )
        result = self.predict_and_heal(window, pod_name, namespace)
        result["data_source"] = "prometheus" if live else "synthetic"
        logger.info(
            "predict_from_live: pod=%s/%s source=%s anomaly=%s",
            namespace, pod_name, result["data_source"],
            result["prediction"].is_anomaly,
        )
        return result

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
# Re-export PrometheusMetricsFetcher for backward-compat imports
# ─────────────────────────────────────────────────────────────────────────────
# PrometheusMetricsFetcher is now defined in prometheus_fetcher.py.
# It is imported at the top of this file and re-exported here so that any
# existing code that does `from inference import PrometheusMetricsFetcher` still works.
__all__ = ["InferencePipeline", "PrometheusMetricsFetcher"]


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
