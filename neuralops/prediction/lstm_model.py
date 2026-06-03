"""
LSTM Prediction Engine — Core of NeuralOps.

Architecture:
  Input:  sliding window of Prometheus metrics (window_size=60 steps, ~5min at 5s interval)
  Model:  2-layer LSTM → Linear → Sigmoid
  Output: failure probability per class (OOMKill, CrashLoop, NodePressure, DiskPressure)

The model predicts: "Will this pod fail in the next N minutes?"
with a confidence score and estimated time-to-failure.

Phase 1: Trained on synthetic data (generator.py)
Phase 2: Fine-tuned on real Prometheus time series
"""
import torch
import torch.nn as nn
import numpy as np
from typing import Dict, Tuple, List, Optional
from dataclasses import dataclass


# ─────────────────────────────────────────────────────────────────────────────
# Data Structures
# ─────────────────────────────────────────────────────────────────────────────

FAILURE_CLASSES = ["memory_leak", "cpu_throttle", "cascading_timeout", "disk_pressure"]
N_CLASSES = len(FAILURE_CLASSES)

# Input features per timestep (from Prometheus metrics)
FEATURE_NAMES = [
    "memory_usage_bytes",      # Container memory usage
    "memory_limit_bytes",      # Container memory limit
    "memory_usage_pct",        # Derived: usage/limit
    "cpu_usage_cores",         # CPU cores used
    "cpu_limit_cores",         # CPU limit
    "cpu_usage_pct",           # Derived: usage/limit
    "restart_count",           # Pod restart counter
    "network_rx_bytes",        # Network received
    "network_tx_bytes",        # Network transmitted
    "disk_usage_bytes",        # Disk usage
    "http_error_rate",         # HTTP 5xx rate
    "http_latency_p99",        # P99 latency (ms)
]
N_FEATURES = len(FEATURE_NAMES)


@dataclass
class PredictionResult:
    """Output of a single inference run."""
    failure_class: str          # Most likely failure type
    confidence: float           # 0.0 – 1.0
    time_to_failure_minutes: Optional[float]  # Estimated TTF, None if low confidence
    all_probabilities: Dict[str, float]       # Probability per class
    is_anomaly: bool            # True if anomaly detected regardless of class
    anomaly_score: float        # 0.0 – 1.0
    pod_name: str
    namespace: str
    timestamp: str


# ─────────────────────────────────────────────────────────────────────────────
# Model Architecture
# ─────────────────────────────────────────────────────────────────────────────

class NeuralOpsLSTM(nn.Module):
    """
    Multi-class failure prediction LSTM.

    Input shape:  (batch_size, window_size, n_features)
    Output shape: (batch_size, n_classes)  — probabilities via Sigmoid
    """

    def __init__(
        self,
        n_features: int = N_FEATURES,
        n_classes: int = N_CLASSES,
        hidden_size: int = 128,
        n_layers: int = 2,
        dropout: float = 0.2,
        window_size: int = 60,
    ):
        super().__init__()

        self.n_features = n_features
        self.n_classes = n_classes
        self.hidden_size = hidden_size
        self.n_layers = n_layers
        self.window_size = window_size

        # Input normalization
        self.input_norm = nn.LayerNorm(n_features)

        # LSTM layers
        self.lstm = nn.LSTM(
            input_size=n_features,
            hidden_size=hidden_size,
            num_layers=n_layers,
            dropout=dropout if n_layers > 1 else 0.0,
            batch_first=True,
        )

        # Attention over time steps
        self.attention = nn.Sequential(
            nn.Linear(hidden_size, 64),
            nn.Tanh(),
            nn.Linear(64, 1),
            nn.Softmax(dim=1),
        )

        # Classification head
        self.classifier = nn.Sequential(
            nn.Linear(hidden_size, 64),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(64, n_classes),
            nn.Sigmoid(),
        )

        # Anomaly score head (separate output)
        self.anomaly_head = nn.Sequential(
            nn.Linear(hidden_size, 32),
            nn.ReLU(),
            nn.Linear(32, 1),
            nn.Sigmoid(),
        )

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Forward pass.

        Args:
            x: (batch, window_size, n_features)

        Returns:
            class_probs: (batch, n_classes)
            anomaly_score: (batch, 1)
        """
        # Normalize inputs
        x = self.input_norm(x)

        # LSTM
        lstm_out, _ = self.lstm(x)  # (batch, window, hidden)

        # Attention-weighted pooling over time
        attn_weights = self.attention(lstm_out)       # (batch, window, 1)
        context = (attn_weights * lstm_out).sum(dim=1)  # (batch, hidden)

        # Classify
        class_probs = self.classifier(context)    # (batch, n_classes)
        anomaly_score = self.anomaly_head(context) # (batch, 1)

        return class_probs, anomaly_score


# ─────────────────────────────────────────────────────────────────────────────
# Model Manager
# ─────────────────────────────────────────────────────────────────────────────

class PredictionEngine:
    """
    Wraps the LSTM model for inference.
    Handles: loading, preprocessing, inference, thresholding.
    """

    CONFIDENCE_THRESHOLD = 0.65    # Below this = no prediction
    ANOMALY_THRESHOLD = 0.55       # Above this = anomaly flagged
    TTF_COEFFICIENTS = {           # Rough TTF estimation from confidence
        "memory_leak":         {"slope": -8.0,  "intercept": 15.0},
        "cpu_throttle":        {"slope": -5.0,  "intercept": 10.0},
        "cascading_timeout":   {"slope": -3.0,  "intercept": 6.0},
        "disk_pressure":       {"slope": -12.0, "intercept": 20.0},
    }

    def __init__(self, model_path: Optional[str] = None, device: str = "cpu"):
        self.device = torch.device(device)
        self.model = NeuralOpsLSTM().to(self.device)
        self.model.eval()

        # Feature normalization stats (updated during training)
        self.feature_means = np.zeros(N_FEATURES)
        self.feature_stds  = np.ones(N_FEATURES)

        if model_path:
            self.load(model_path)

    def load(self, path: str):
        checkpoint = torch.load(path, map_location=self.device, weights_only=False)
        self.model.load_state_dict(checkpoint["model_state"])
        self.feature_means = checkpoint.get("feature_means", self.feature_means)
        self.feature_stds  = checkpoint.get("feature_stds",  self.feature_stds)
        print(f"[PredictionEngine] Loaded model from {path}")

    def save(self, path: str):
        """Save model checkpoint."""
        torch.save({
            "model_state":   self.model.state_dict(),
            "feature_means": self.feature_means,
            "feature_stds":  self.feature_stds,
        }, path)
        print(f"[PredictionEngine] Saved model to {path}")

    def preprocess(self, metrics_window: np.ndarray) -> torch.Tensor:
        """
        Normalize and convert a metrics window to tensor.

        Args:
            metrics_window: (window_size, n_features) numpy array

        Returns:
            Tensor ready for model input
        """
        # Z-score normalization using training stats
        normalized = (metrics_window - self.feature_means) / (self.feature_stds + 1e-8)

        # Clip outliers
        normalized = np.clip(normalized, -5.0, 5.0)

        # Convert to tensor: (1, window_size, n_features)
        tensor = torch.FloatTensor(normalized).unsqueeze(0).to(self.device)
        return tensor

    def predict(
        self,
        metrics_window: np.ndarray,
        pod_name: str = "unknown",
        namespace: str = "default",
    ) -> PredictionResult:
        """
        Run inference on a metrics window.

        Args:
            metrics_window: (window_size, n_features) — recent metric history
            pod_name: Pod being monitored
            namespace: K8s namespace

        Returns:
            PredictionResult with failure class, confidence, and TTF estimate
        """
        from datetime import datetime

        with torch.no_grad():
            x = self.preprocess(metrics_window)
            class_probs, anomaly_score = self.model(x)

        probs = class_probs.squeeze().cpu().numpy()   # (n_classes,)
        anom  = float(anomaly_score.squeeze().cpu().numpy())

        # Build probability dict
        all_probs = {cls: float(p) for cls, p in zip(FAILURE_CLASSES, probs)}

        # Highest probability class
        top_idx   = int(np.argmax(probs))
        top_class = FAILURE_CLASSES[top_idx]
        top_conf  = float(probs[top_idx])

        # Time-to-failure estimate
        ttf = None
        if top_conf >= self.CONFIDENCE_THRESHOLD:
            coef = self.TTF_COEFFICIENTS[top_class]
            ttf  = max(1.0, coef["slope"] * top_conf + coef["intercept"])

        return PredictionResult(
            failure_class=top_class,
            confidence=top_conf,
            time_to_failure_minutes=ttf,
            all_probabilities=all_probs,
            is_anomaly=anom >= self.ANOMALY_THRESHOLD,
            anomaly_score=anom,
            pod_name=pod_name,
            namespace=namespace,
            timestamp=datetime.utcnow().isoformat(),
        )

    def should_alert(self, result: PredictionResult) -> bool:
        """Returns True if result warrants sending to healing agent."""
        return (
            result.confidence >= self.CONFIDENCE_THRESHOLD
            or result.is_anomaly
        )


# ─────────────────────────────────────────────────────────────────────────────
# Singleton
# ─────────────────────────────────────────────────────────────────────────────

_engine: Optional[PredictionEngine] = None

def get_prediction_engine(model_path: Optional[str] = None) -> PredictionEngine:
    """Get or create the global prediction engine instance."""
    global _engine
    if _engine is None:
        _engine = PredictionEngine(model_path=model_path)
    return _engine
