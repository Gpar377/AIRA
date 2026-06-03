"""
AIRA Unified API Backend — FastAPI REST and WebSocket Server.
Bridges SentinelArena and NeuralOps, providing real-time data streaming
for the React dashboard via WebSockets, and database persistence.
"""
import os
import sys
import asyncio
import threading
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path
import numpy as np

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import structlog

# Allow importing from AIRA root
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.db import init_core_database
from neuralops.config import settings
from neuralops.memory.database import init_database

init_core_database()

try:
    init_database(settings.DATABASE_URL)
except Exception as e:
    fallback_path = Path(__file__).parent.parent / "aira_unified.db"
    sqlite_url = f"sqlite:///{fallback_path.absolute()}".replace("\\", "/")
    init_database(sqlite_url)

from core.unified_memory import UnifiedMemoryStore
from core.events import (
    subscribe_sentinel, unsubscribe_sentinel, publish_sentinel_event,
    subscribe_neuralops, unsubscribe_neuralops, publish_neuralops_event
)
from neuralops.prediction.inference import InferencePipeline, PrometheusMetricsFetcher
from neuralops.memory.store import MemoryStore

# Initialize loggers
logger = structlog.get_logger()

app = FastAPI(
    title="AIRA Unified API Backend",
    description="Autonomous Infrastructure Resilience Architecture API server",
    version="1.0.0"
)

# Enable CORS for the dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared memory stores
db_store = UnifiedMemoryStore()
neuralops_memory = MemoryStore()

# Global state trackers for SentinelArena
active_arena_state: Dict[str, Any] = {}
arena_running: bool = False
arena_thread: Optional[threading.Thread] = None

# Initialize NeuralOps prediction pipeline (uses fallback engine if model not trained)
inference_pipeline = InferencePipeline(
    model_path=str(Path(__file__).parent.parent / "neuralops" / "models" / "lstm_checkpoint.pt")
)
metrics_fetcher = PrometheusMetricsFetcher()


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic Schemas
# ─────────────────────────────────────────────────────────────────────────────

class SentinelStartRequest(BaseModel):
    rounds: int = 5
    reset: bool = False


class PredictRequest(BaseModel):
    pod_name: str
    namespace: str = "default"
    metrics_window: Optional[List[List[float]]] = None  # 60 steps x 12 features


class IncidentHealRequest(BaseModel):
    incident_id: int
    pod_name: str
    namespace: str
    failure_class: str
    confidence: float


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI Lifecycle
# ─────────────────────────────────────────────────────────────────────────────

@app.on_event("startup")
def startup_event():
    print("AIRA_LIVE_SCAN value in startup_event:", os.environ.get("AIRA_LIVE_SCAN"))
    logger.info("api_server_starting")
    # Initialize SQL Database (PostgreSQL or SQLite fallback) and create tables
    init_core_database()
    logger.info("api_server_database_ready")


# ─────────────────────────────────────────────────────────────────────────────
# 1. Health and System Status Endpoint
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health")
def health_check():
    """Get service status and component connectivity info."""
    db_status = "connected"
    try:
        # Check DB by calling statistics query
        neuralops_memory.get_statistics()
    except Exception as e:
        db_status = f"unreachable: {str(e)}"
        
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "components": {
            "api": "operational",
            "database": db_status,
            "lstm_model": "loaded" if inference_pipeline.engine is not None else "stub"
        }
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. SentinelArena Control Endpoints (Autonomous Security)
# ─────────────────────────────────────────────────────────────────────────────

def run_arena_in_background(rounds: int, reset: bool):
    """Background thread function running the full SentinelArena LangGraph execution."""
    global active_arena_state, arena_running
    try:
        from sentinel.memory import empty_memory, load_memory
        from sentinel.graph.arena_graph import build_arena_graph, create_initial_state
        
        logger.info("starting_sentinel_arena_loop", rounds=rounds)
        
        # Load or reset memory
        memory = empty_memory() if reset else load_memory()
        
        # Build LangGraph
        arena = build_arena_graph()
        initial_state = create_initial_state(memory, max_rounds=rounds)
        
        # Update thread state variables
        active_arena_state = dict(initial_state)
        active_arena_state["status"] = "running"
        arena_running = True
        
        displayed_event_count = 0
        
        # Publish start event to WebSockets
        if initial_state["events"]:
            publish_sentinel_event(initial_state["events"][0])
            
        # Stream the graph step-by-step
        for step_output in arena.stream(initial_state, {"recursion_limit": 150}):
            # Check for sudden manual stop
            if active_arena_state.get("kill_switch"):
                logger.info("sentinel_arena_kill_switch_triggered")
                break
                
            for node_name, node_state in step_output.items():
                # Safely merge node outputs into our active state
                for key, val in node_state.items():
                    active_arena_state[key] = val
                    
                # Broadcast any newly appended round events
                events = node_state.get("events", [])
                for event in events[displayed_event_count:]:
                    publish_sentinel_event(event)
                displayed_event_count = max(displayed_event_count, len(events))
                
        active_arena_state["status"] = "completed"
        logger.info("sentinel_arena_loop_finished")
    except Exception as e:
        logger.error("sentinel_arena_thread_failed", error=str(e))
        if active_arena_state:
            active_arena_state["status"] = "stopped"
    finally:
        arena_running = False


@app.post("/sentinel/start")
def start_sentinel(req: SentinelStartRequest):
    """Trigger a multi-round SentinelArena simulation in a background thread."""
    global arena_running, arena_thread
    if arena_running:
        return {
            "status": "already_running",
            "arena_id": active_arena_state.get("memory", {}).get("arena_id", "unknown")
        }
        
    arena_thread = threading.Thread(
        target=run_arena_in_background,
        args=(req.rounds, req.reset),
        daemon=True
    )
    arena_thread.start()
    
    return {
        "status": "started",
        "rounds": req.rounds,
        "message": "SentinelArena security simulation initiated in background."
    }


@app.post("/sentinel/stop")
def stop_sentinel():
    """Trigger the OPA/kill-switch to stop the running simulation immediately."""
    global active_arena_state, arena_running
    if not arena_running:
        return {"status": "not_running", "message": "Arena simulation is not active."}
        
    active_arena_state["kill_switch"] = True
    active_arena_state["status"] = "stopped"
    
    # Broadcast quick interrupt system event
    publish_sentinel_event({
        "timestamp": datetime.now().isoformat(),
        "round": active_arena_state.get("round", 0),
        "agent": "system",
        "event_type": "kill_switch",
        "message": "🚨 Kill Switch Triggered! Stopping security simulation immediately.",
        "data": {}
    })
    
    return {"status": "stopping", "message": "SentinelArena stop signal dispatched."}


@app.get("/sentinel/status")
def get_sentinel_status():
    """Query current SentinelArena telemetry, scores, alerts, and rounds."""
    global active_arena_state, arena_running
    if not active_arena_state:
        # Load the last run from DB if currently uninitialized
        recent = db_store.get_all_arena_runs(limit=1)
        if recent:
            return {
                "running": False,
                "status": "completed",
                "round": len(recent[0].get("score_timeline", [])),
                "attack_surface_score": recent[0].get("score_timeline", [])[-1]["score"] if recent[0].get("score_timeline") else 100.0,
                "score_history": [s["score"] for s in recent[0].get("score_timeline", [])],
                "arena_id": recent[0]["arena_id"]
            }
        return {"running": False, "status": "uninitialized"}
        
    return {
        "running": arena_running,
        "status": active_arena_state.get("status", "unknown"),
        "round": active_arena_state.get("round", 1),
        "attack_surface_score": active_arena_state.get("attack_surface_score", 100.0),
        "score_history": active_arena_state.get("score_history", [100.0]),
        "kill_switch": active_arena_state.get("kill_switch", False),
        "arena_id": active_arena_state.get("memory", {}).get("arena_id")
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. NeuralOps Control Endpoints (Autonomous Reliability & Healing)
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/neuralops/predict")
def predict_reliability(req: PredictRequest):
    """Run failure prediction on pod metrics using the trained LSTM."""
    # Build or fetch metrics window
    if req.metrics_window is not None:
        window_arr = np.array(req.metrics_window, dtype=np.float32)
    else:
        # Fallback to fetching window (stub Prometheus metric fetcher)
        window_arr = metrics_fetcher.fetch_window(req.pod_name, req.namespace)
        
    try:
        # Run inference
        result = inference_pipeline.predict_from_metrics(window_arr, req.pod_name, req.namespace)
        
        # Automatically publish prediction event to websocket listeners
        publish_neuralops_event({
            "timestamp": datetime.utcnow().isoformat(),
            "node": "predict",
            "message": f"[PREDICT] {result.failure_class} detected on {req.namespace}/{req.pod_name} | Confidence: {result.confidence:.0%}",
            "data": {
                "failure_class": result.failure_class,
                "confidence": result.confidence,
                "anomaly_score": result.anomaly_score,
                "time_to_failure_minutes": result.time_to_failure_minutes
            }
        })
        
        return {
            "failure_class": result.failure_class,
            "confidence": result.confidence,
            "is_anomaly": result.is_anomaly,
            "anomaly_score": result.anomaly_score,
            "time_to_failure_minutes": result.time_to_failure_minutes,
            "pod_name": result.pod_name,
            "namespace": result.namespace
        }
    except Exception as e:
        logger.error("neuralops_prediction_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/neuralops/heal")
def heal_reliability(req: IncidentHealRequest, background_tasks: BackgroundTasks):
    """Trigger the LangGraph healing agent pipeline for an active prediction."""
    # Reconstruct prediction result to run pipeline
    from neuralops.prediction.lstm_model import PredictionResult
    pred_res = PredictionResult(
        failure_class=req.failure_class,
        confidence=req.confidence,
        time_to_failure_minutes=8.0,
        all_probabilities={req.failure_class: req.confidence},
        is_anomaly=True,
        anomaly_score=req.confidence,
        pod_name=req.pod_name,
        namespace=req.namespace,
        timestamp=datetime.utcnow().isoformat()
    )
    
    # Store incident record inside SQL memory
    incident = neuralops_memory.create_incident(
        failure_type=req.failure_class,
        confidence_score=req.confidence,
        namespace=req.namespace,
        pod_name=req.pod_name,
        predicted_ttf_minutes=8.0
    )
    
    # Run healing in Uvicorn background tasks to prevent API blocking
    def run_healer_task(inc_id: int):
        try:
            logger.info("healer_pipeline_invoked", incident_id=inc_id)
            
            # Subscribe temporary callback to forward healer node events straight to publish_neuralops_event
            def forward_events(state_events):
                # Simply republish last state events
                if state_events:
                    publish_neuralops_event(state_events[-1])
                    
            # Run pipeline
            final_state = inference_pipeline.trigger_healing(pred_res)
            
            # Record events to websocket stream
            for event in final_state.get("events", []):
                publish_neuralops_event(event)
                
            # Update incident records inside database memory
            neuralops_memory.update_diagnosis(
                incident_id=inc_id,
                root_cause=final_state.get("root_cause", "Auto-diagnosed"),
                relevant_logs=[final_state.get("relevant_context")]
            )
            neuralops_memory.update_remediation(
                incident_id=inc_id,
                action=final_state.get("chosen_action", "none"),
                successful=final_state.get("action_success", False),
                details={"result_summary": final_state.get("action_result")},
                autonomy_level=final_state.get("autonomy_tier", "TIER_2")
            )
            
            logger.info("healer_pipeline_completed", incident_id=inc_id, success=final_state.get("action_success"))
        except Exception as e:
            logger.error("healer_background_task_failed", error=str(e))
            
    background_tasks.add_task(run_healer_task, incident.id)
    
    return {
        "status": "healing_initiated",
        "incident_id": incident.id,
        "message": f"Autonomous healing process dispatched for {req.namespace}/{req.pod_name}."
    }


@app.get("/neuralops/incidents")
def get_incidents(days: int = 7, failure_class: Optional[str] = None):
    """Retrieve historical incidents, diagnostics, and remediation details."""
    incidents = neuralops_memory.get_incident_history(days=days, failure_type=failure_class)
    return [i.to_dict() for i in incidents]


@app.get("/neuralops/stats")
def get_neuralops_stats():
    """Retrieve auto-healing resolution ratios and failure counts."""
    return neuralops_memory.get_statistics()


# ─────────────────────────────────────────────────────────────────────────────
# 4. WebSocket Live Streaming Endpoints (For Dashboard React)
# ─────────────────────────────────────────────────────────────────────────────

@app.websocket("/sentinel/ws/live")
async def sentinel_websocket(websocket: WebSocket):
    """WebSocket endpoint streaming live SentinelArena logs, scans, and OPA checks."""
    await websocket.accept()
    logger.info("sentinel_websocket_connected")
    
    # Event queue for thread-safe cross-loop communication
    queue = asyncio.Queue()
    
    def on_event(event: Dict[str, Any]):
        # Run thread-safe call to put event into async queue
        asyncio.run_coroutine_threadsafe(queue.put(event), asyncio.get_event_loop())
        
    # Subscribe Uvicorn websocket callback to global Sentinel event bus
    subscribe_sentinel(on_event)
    
    try:
        while True:
            # Bounded wait for incoming events in queue
            event = await queue.get()
            await websocket.send_json(event)
            queue.task_done()
    except WebSocketDisconnect:
        logger.info("sentinel_websocket_disconnected")
    finally:
        # Cleanup subscriber
        unsubscribe_sentinel(on_event)


@app.websocket("/neuralops/ws/live")
async def neuralops_websocket(websocket: WebSocket):
    """WebSocket endpoint streaming live NeuralOps anomaly detections and healing events."""
    await websocket.accept()
    logger.info("neuralops_websocket_connected")
    
    queue = asyncio.Queue()
    
    def on_event(event: Dict[str, Any]):
        asyncio.run_coroutine_threadsafe(queue.put(event), asyncio.get_event_loop())
        
    subscribe_neuralops(on_event)
    
    try:
        while True:
            event = await queue.get()
            await websocket.send_json(event)
            queue.task_done()
    except WebSocketDisconnect:
        logger.info("neuralops_websocket_disconnected")
    finally:
        unsubscribe_neuralops(on_event)


# ─────────────────────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("launching_aira_app_server")
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
