"""
Unified Sovereign Edge Platform Dashboard Server.
Serves the web dashboard, coordinates OSB provisioning, Sovereign xDS inspection,
ASAP token generation, and live AMI verification test harness.
"""
import os
import sys
import time
import json
import asyncio
from typing import Dict, Any, Optional
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# Ensure parent path is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from services.service_broker.main import app as osb_app, store as osb_store, queue as osb_queue
from services.sovereign_control_plane.main import app as sovereign_app, poller as sovereign_poller
from services.edge_auth_rust.auth_sidecar_runner import create_sample_asap_token, app as auth_app
from infra.ami_pipeline.live_ec2_test_harness import LiveEC2ImageTestHarness
from infra.ami_pipeline.multi_region_dist import MultiRegionRollout, ATLASSIAN_13_REGIONS

app = FastAPI(title="Sovereign Edge Platform Portal")

HTML_FILE = os.path.join(os.path.dirname(__file__), "index.html")

@app.get("/", response_class=HTMLResponse)
def index():
    if os.path.exists(HTML_FILE):
        with open(HTML_FILE, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Sovereign Edge Platform</h1><p>Dashboard HTML loading...</p>"

@app.get("/api/state")
def get_state():
    """Returns aggregated real-time state of the entire platform."""
    sovereign_poller.poll_and_render()
    clusters = sovereign_poller.get_snapshot("clusters")
    routes = sovereign_poller.get_snapshot("routes")
    listeners = sovereign_poller.get_snapshot("listeners")

    return {
        "osb": {
            "instances": osb_store.list_instances(),
            "bindings": osb_store.list_bindings(),
            "queue_stats": osb_queue.get_stats(),
            "audit_logs": osb_store.get_logs()[-20:]
        },
        "sovereign": {
            "version": sovereign_poller.current_version,
            "clusters_count": len(clusters.get("resources", [])),
            "clusters": clusters.get("resources", []),
            "routes": routes.get("resources", []),
            "listeners": listeners.get("resources", [])
        },
        "fleet": {
            "total_proxies": 2000,
            "regions_count": 13,
            "regions": ATLASSIAN_13_REGIONS
        }
    }

@app.post("/api/simulate/provision")
async def simulate_provision(req: Request):
    """Triggers self-service provisioning through OSB SQS task queue."""
    data = await req.json()
    service_name = data.get("service_name", "jira").lower()
    path_prefix = data.get("path_prefix", f"/{service_name}")
    port = data.get("port", 8081)
    asap_required = data.get("asap_required", True)
    canary_weight = int(data.get("canary_weight", 0))

    instance_id = f"inst-{service_name}-edge"
    binding_id = f"bind-{service_name}-prod"

    # Step 1: Provision instance
    osb_store.save_instance(instance_id, {
        "instance_id": instance_id,
        "service_id": "edge-routing-service",
        "plan_id": "standard" if canary_weight == 0 else "canary",
        "domain": f"{service_name}.atlassian.net",
        "vip": f"10.240.{hash(service_name) % 250}.10",
        "status": "ready",
        "created_at": time.time()
    })

    # Step 2: Queue binding creation through SQS
    op_id = f"op-bind-{int(time.time()*1000)}"
    osb_queue.send_message({
        "action": "create_binding",
        "operation_id": op_id,
        "instance_id": instance_id,
        "binding_id": binding_id,
        "parameters": {
            "service_name": service_name,
            "path_prefix": path_prefix,
            "upstreams": [f"127.0.0.1:{port}"],
            "health_check_path": "/health",
            "asap_required": asap_required,
            "canary_weight": canary_weight
        },
        "entity_id": binding_id
    })
    osb_store.log_event("self_service_provision", {
        "service": service_name,
        "binding_id": binding_id,
        "path_prefix": path_prefix
    })

    # Allow worker to pick up message
    await asyncio.sleep(0.5)
    sovereign_poller.poll_and_render()

    return {
        "status": "success",
        "instance_id": instance_id,
        "binding_id": binding_id,
        "sovereign_version": sovereign_poller.current_version
    }

@app.post("/api/simulate/asap-test")
async def simulate_asap_test(req: Request):
    """Simulates Edge Proxy receiving request and verifying ASAP token via ext_authz."""
    data = await req.json()
    token_type = data.get("token_type", "valid")
    target_service = data.get("target_service", "jira")

    if token_type == "valid":
        token = create_sample_asap_token(
            issuer=f"{target_service}-client",
            tenant_id="tenant-prod-apac"
        )
        return {
            "token": token,
            "status_code": 200,
            "authenticated": True,
            "injected_headers": {
                "x-authenticated-caller": f"{target_service}-client",
                "x-tenant-id": "tenant-prod-apac",
                "x-asap-token-valid": "true",
                "x-auth-engine": "rust-asap-sidecar"
            },
            "upstream_response": {
                "service": target_service,
                "status": "HTTP 200 OK",
                "payload": f"Welcome to {target_service.capitalize()} API! Request successfully routed by Envoy."
            }
        }
    elif token_type == "expired":
        token = create_sample_asap_token(
            issuer="rogue-service",
            expires_in_sec=-100 # expired
        )
        return {
            "token": token,
            "status_code": 401,
            "authenticated": False,
            "error": "ASAP Token Expired",
            "edge_decision": "BLOCKED_AT_EDGE (ext_authz rejected request, backend untouched)"
        }
    else: # missing or invalid
        return {
            "token": None,
            "status_code": 401,
            "authenticated": False,
            "error": "Missing Authorization / X-ASAP-Token header",
            "edge_decision": "BLOCKED_AT_EDGE (ext_authz rejected request, backend untouched)"
        }

@app.post("/api/simulate/ami-pipeline")
def simulate_ami_pipeline():
    """Runs the 7-point live EC2 test harness (Video timestamp 1115s) and multi-region rollout."""
    harness = LiveEC2ImageTestHarness(ami_id="ami-091a48c12b7d90e21")
    instance = harness.boot_test_instance()
    receipt = harness.run_suite()
    harness.terminate_test_instance()

    rollout = MultiRegionRollout(receipt["ami_id"])
    regional_amis = rollout.copy_ami_to_all_regions()
    rollout_stages = rollout.execute_canary_rollout()

    return {
        "test_instance": instance,
        "receipt": receipt,
        "regional_distribution": regional_amis,
        "rollout_stages": rollout_stages
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=3000)
