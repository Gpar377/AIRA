"""
Demo Service: Disk Pressure
Simulates disk space exhaustion
"""
from fastapi import FastAPI
from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response
import psutil
import os
import tempfile

app = FastAPI(title="DiskPressure Service")

REQUEST_COUNT = Counter('http_requests_total', 'Total HTTP requests')
DISK_USAGE = Gauge('disk_usage_percent', 'Disk usage percentage')
DISK_AVAILABLE = Gauge('disk_available_bytes', 'Available disk space in bytes')

PRESSURE_ENABLED = os.getenv("PRESSURE_ENABLED", "true").lower() == "true"
WRITE_SIZE_MB = int(os.getenv("WRITE_SIZE_MB", "50"))

temp_files = []


@app.get("/")
async def root():
    REQUEST_COUNT.inc()
    return {"service": "disk-pressure", "status": "running"}


@app.get("/write")
async def trigger_write():
    """Endpoint that writes to disk"""
    REQUEST_COUNT.inc()
    
    if PRESSURE_ENABLED:
        # Write temporary file
        temp_file = tempfile.NamedTemporaryFile(delete=False)
        data = bytearray(WRITE_SIZE_MB * 1024 * 1024)
        temp_file.write(data)
        temp_file.close()
        temp_files.append(temp_file.name)
    
    disk = psutil.disk_usage('/')
    DISK_USAGE.set(disk.percent)
    DISK_AVAILABLE.set(disk.free)
    
    return {
        "files_written": len(temp_files),
        "total_mb_written": len(temp_files) * WRITE_SIZE_MB,
        "disk_usage_percent": disk.percent,
        "disk_available_gb": disk.free / (1024**3)
    }


@app.get("/cleanup")
async def cleanup():
    """Clean up temporary files"""
    for file_path in temp_files:
        try:
            os.remove(file_path)
        except:
            pass
    
    count = len(temp_files)
    temp_files.clear()
    
    disk = psutil.disk_usage('/')
    DISK_USAGE.set(disk.percent)
    DISK_AVAILABLE.set(disk.free)
    
    return {
        "files_removed": count,
        "disk_usage_percent": disk.percent
    }


@app.get("/metrics")
async def metrics():
    disk = psutil.disk_usage('/')
    DISK_USAGE.set(disk.percent)
    DISK_AVAILABLE.set(disk.free)
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/health")
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8083)
