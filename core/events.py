"""
AIRA Event Manager — Shared Pub/Sub event bridge for WebSockets and live dashboard updates.
Enables background LangGraph nodes and predicting agents to stream events to Uvicorn.
"""
from typing import Callable, Dict, Any, List
import structlog

logger = structlog.get_logger()

# Global subscribers
_sentinel_subscribers: List[Callable[[Dict[str, Any]], None]] = []
_neuralops_subscribers: List[Callable[[Dict[str, Any]], None]] = []


# ── SentinelArena Event Bus ───────────────────────────────────────────

def subscribe_sentinel(callback: Callable[[Dict[str, Any]], None]) -> None:
    """Subscribe a callback to all SentinelArena events."""
    if callback not in _sentinel_subscribers:
        _sentinel_subscribers.append(callback)
        logger.debug("sentinel_event_subscribed", callback=callback.__name__ if hasattr(callback, '__name__') else str(callback))


def unsubscribe_sentinel(callback: Callable[[Dict[str, Any]], None]) -> None:
    """Unsubscribe a callback from SentinelArena events."""
    if callback in _sentinel_subscribers:
        _sentinel_subscribers.remove(callback)
        logger.debug("sentinel_event_unsubscribed", callback=callback.__name__ if hasattr(callback, '__name__') else str(callback))


def publish_sentinel_event(event: Dict[str, Any]) -> None:
    """Publish a SentinelArena event to all active subscribers."""
    logger.debug("publishing_sentinel_event", type=event.get("event_type"), round=event.get("round"))
    for sub in list(_sentinel_subscribers):
        try:
            sub(event)
        except Exception as e:
            logger.error("sentinel_subscriber_error", error=str(e))


# ── NeuralOps Healing Event Bus ──────────────────────────────────────

def subscribe_neuralops(callback: Callable[[Dict[str, Any]], None]) -> None:
    """Subscribe a callback to all NeuralOps failure predictions and healing events."""
    if callback not in _neuralops_subscribers:
        _neuralops_subscribers.append(callback)
        logger.debug("neuralops_event_subscribed", callback=callback.__name__ if hasattr(callback, '__name__') else str(callback))


def unsubscribe_neuralops(callback: Callable[[Dict[str, Any]], None]) -> None:
    """Unsubscribe a callback from NeuralOps events."""
    if callback in _neuralops_subscribers:
        _neuralops_subscribers.remove(callback)
        logger.debug("neuralops_event_unsubscribed", callback=callback.__name__ if hasattr(callback, '__name__') else str(callback))


def publish_neuralops_event(event: Dict[str, Any]) -> None:
    """Publish a NeuralOps event to all active subscribers."""
    logger.debug("publishing_neuralops_event", node=event.get("node"), action=event.get("chosen_action"))
    for sub in list(_neuralops_subscribers):
        try:
            sub(event)
        except Exception as e:
            logger.error("neuralops_subscriber_error", error=str(e))
