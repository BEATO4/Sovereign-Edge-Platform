"""
Sovereign Control Plane API: Envoy Dynamic xDS v3 Management Server.
Inspired by Vasilios Syrakis's architecture at Atlassian.
Serves dynamic configuration (LDS, RDS, CDS, EDS) rendered from Jinja2 templates
to thousands of Envoy proxies across AWS regions with zero downtime.
"""
import threading
import time
from typing import Dict, Any, Optional
from fastapi import FastAPI, Request
from pydantic import BaseModel

from .poller import ConfigPoller

app = FastAPI(
    title="Sovereign Envoy xDS Control Plane",
    description="Dynamic Envoy Control Plane serving template-rendered LDS, RDS, CDS configurations",
    version="3.0.0"
)

poller = ConfigPoller()

def background_poller_loop():
    while True:
        try:
            poller.poll_and_render()
        except Exception:
            pass
        time.sleep(2.0)

poller_thread = threading.Thread(target=background_poller_loop, daemon=True)
poller_thread.start()

# --- Envoy xDS v3 Discovery Endpoints ---

@app.post("/v3/discovery:clusters")
@app.get("/v3/discovery:clusters")
async def discovery_clusters(req: Optional[Dict[str, Any]] = None):
    """Envoy Cluster Discovery Service (CDS) endpoint."""
    poller.poll_and_render()
    return poller.get_snapshot("clusters")

@app.post("/v3/discovery:routes")
@app.get("/v3/discovery:routes")
async def discovery_routes(req: Optional[Dict[str, Any]] = None):
    """Envoy Route Discovery Service (RDS) endpoint."""
    poller.poll_and_render()
    return poller.get_snapshot("routes")

@app.post("/v3/discovery:listeners")
@app.get("/v3/discovery:listeners")
async def discovery_listeners(req: Optional[Dict[str, Any]] = None):
    """Envoy Listener Discovery Service (LDS) endpoint."""
    poller.poll_and_render()
    return poller.get_snapshot("listeners")

@app.post("/v3/discovery:endpoints")
@app.get("/v3/discovery:endpoints")
async def discovery_endpoints(req: Optional[Dict[str, Any]] = None):
    """Envoy Endpoint Discovery Service (EDS) endpoint."""
    return {"version_info": poller.current_version, "resources": []}

# --- Management, Telemetry & Inspection Endpoints ---

@app.get("/config_dump")
def get_config_dump():
    """Provides human-readable inspection of all currently rendered Envoy xDS resources."""
    return {
        "version": poller.current_version,
        "clusters": poller.get_snapshot("clusters"),
        "routes": poller.get_snapshot("routes"),
        "listeners": poller.get_snapshot("listeners"),
        "raw_topology": poller.raw_topology
    }

@app.post("/admin/force_poll")
def force_poll():
    """Manually forces an immediate poll and template re-render."""
    updated = poller.poll_and_render()
    return {
        "updated": updated,
        "current_version": poller.current_version
    }

@app.get("/metrics")
def get_metrics():
    clusters_snapshot = poller.get_snapshot("clusters")
    routes_snapshot = poller.get_snapshot("routes")
    return {
        "sovereign_version": poller.current_version,
        "total_clusters": len(clusters_snapshot.get("resources", [])),
        "total_routes": len(routes_snapshot.get("resources", [{}])[0].get("virtual_hosts", [{}])[0].get("routes", []) if routes_snapshot.get("resources") else 0),
        "active_proxies_connected": 1
    }

@app.get("/healthz")
def healthz():
    return {
        "status": "healthy",
        "service": "sovereign-control-plane",
        "version": poller.current_version
    }
