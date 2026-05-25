"""
Demo Service: Memory Leak
Simulates a gradual memory leak leading to OOMKill
"""
from fastapi import FastAPI
from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response
import psutil
import time
import os

app = FastAPI(title="MemoryLeak Service")

# Prometheus metrics
REQUEST_COUNT = Counter('http_requests_total', 'Total HTTP requests')
MEMORY_USAGE = Gauge('memory_usage_bytes', 'Current memory usage in bytes')
MEMORY_PERCENT = Gauge('memory_usage_percent', 'Memory usage percentage')

# Memory leak simulation
memory_hog = []
LEAK_SIZE_MB = int(os.getenv("LEAK_SIZE_MB", "10"))  # MB per request
LEAK_ENABLED = os.getenv("LEAK_ENABLED", "true").lower() == "true"


@app.get("/")
async def root():
    """Health check endpoint"""
    REQUEST_COUNT.inc()
    return {"service": "memory-leak", "status": "running"}


@app.get("/leak")
async def trigger_leak():
    """Endpoint that causes memory leak"""
    REQUEST_COUNT.inc()
    
    if LEAK_ENABLED:
        # Allocate memory and never release it
        chunk = bytearray(LEAK_SIZE_MB * 1024 * 1024)
        memory_hog.append(chunk)
    
    process = psutil.Process()
    mem_info = process.memory_info()
    
    MEMORY_USAGE.set(mem_info.rss)
    MEMORY_PERCENT.set(process.memory_percent())
    
    return {
        "leaked_mb": len(memory_hog) * LEAK_SIZE_MB,
        "current_memory_mb": mem_info.rss / (1024 * 1024),
        "memory_percent": process.memory_percent()
    }


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    process = psutil.Process()
    mem_info = process.memory_info()
    
    MEMORY_USAGE.set(mem_info.rss)
    MEMORY_PERCENT.set(process.memory_percent())
    
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/health")
async def health():
    """Kubernetes health check"""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
