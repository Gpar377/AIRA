"""
Demo Service: CPU Throttle
Simulates CPU-intensive operations leading to throttling
"""
from fastapi import FastAPI
from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response
import psutil
import time
import os
import hashlib

app = FastAPI(title="CPUThrottle Service")

REQUEST_COUNT = Counter('http_requests_total', 'Total HTTP requests')
CPU_USAGE = Gauge('cpu_usage_percent', 'CPU usage percentage')
REQUEST_DURATION = Histogram('request_duration_seconds', 'Request duration')

THROTTLE_ENABLED = os.getenv("THROTTLE_ENABLED", "true").lower() == "true"
WORK_ITERATIONS = int(os.getenv("WORK_ITERATIONS", "1000000"))


@app.get("/")
async def root():
    REQUEST_COUNT.inc()
    return {"service": "cpu-throttle", "status": "running"}


@app.get("/compute")
async def trigger_compute():
    """CPU-intensive endpoint"""
    REQUEST_COUNT.inc()
    start_time = time.time()
    
    if THROTTLE_ENABLED:
        # CPU-intensive work
        result = 0
        for i in range(WORK_ITERATIONS):
            result += hashlib.sha256(str(i).encode()).hexdigest().__hash__()
    
    duration = time.time() - start_time
    REQUEST_DURATION.observe(duration)
    
    process = psutil.Process()
    cpu_percent = process.cpu_percent(interval=0.1)
    CPU_USAGE.set(cpu_percent)
    
    return {
        "iterations": WORK_ITERATIONS,
        "duration_seconds": duration,
        "cpu_percent": cpu_percent
    }


@app.get("/metrics")
async def metrics():
    process = psutil.Process()
    CPU_USAGE.set(process.cpu_percent(interval=0.1))
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/health")
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8081)
