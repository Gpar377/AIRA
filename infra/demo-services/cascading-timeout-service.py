"""
Demo Service: Cascading Timeout
Simulates service mesh timeout cascades
"""
from fastapi import FastAPI, HTTPException
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response
import asyncio
import os
import random

app = FastAPI(title="CascadingTimeout Service")

REQUEST_COUNT = Counter('http_requests_total', 'Total HTTP requests')
TIMEOUT_COUNT = Counter('timeout_errors_total', 'Total timeout errors')
REQUEST_DURATION = Histogram('request_duration_seconds', 'Request duration')

CASCADE_ENABLED = os.getenv("CASCADE_ENABLED", "true").lower() == "true"
BASE_DELAY = float(os.getenv("BASE_DELAY", "2.0"))
TIMEOUT_PROBABILITY = float(os.getenv("TIMEOUT_PROBABILITY", "0.3"))


@app.get("/")
async def root():
    REQUEST_COUNT.inc()
    return {"service": "cascading-timeout", "status": "running"}


@app.get("/call")
async def trigger_call():
    """Endpoint that may timeout"""
    REQUEST_COUNT.inc()
    
    if CASCADE_ENABLED and random.random() < TIMEOUT_PROBABILITY:
        TIMEOUT_COUNT.inc()
        # Simulate timeout
        delay = BASE_DELAY * random.uniform(2, 5)
        await asyncio.sleep(delay)
        raise HTTPException(status_code=504, detail="Gateway Timeout")
    
    # Normal response
    delay = BASE_DELAY * random.uniform(0.1, 0.5)
    await asyncio.sleep(delay)
    
    REQUEST_DURATION.observe(delay)
    
    return {
        "status": "success",
        "delay_seconds": delay
    }


@app.get("/chain")
async def trigger_chain():
    """Simulates cascading calls"""
    REQUEST_COUNT.inc()
    
    results = []
    for i in range(3):
        try:
            if CASCADE_ENABLED and random.random() < TIMEOUT_PROBABILITY:
                TIMEOUT_COUNT.inc()
                raise HTTPException(status_code=504, detail=f"Timeout at level {i}")
            
            delay = BASE_DELAY * random.uniform(0.1, 0.3)
            await asyncio.sleep(delay)
            results.append({"level": i, "status": "success", "delay": delay})
        except HTTPException:
            results.append({"level": i, "status": "timeout"})
            raise
    
    return {"chain_results": results}


@app.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/health")
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8082)
