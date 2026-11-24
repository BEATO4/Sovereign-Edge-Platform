"""
Open Service Broker (OSB) API Implementation for Enterprise Edge Routing.
Built with FastAPI, decoupled with Amazon SQS and DynamoDB store.
Enables internal engineering teams to self-service provision edge routes and Envoy proxies.
"""
import uuid
import threading
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks, Header
from pydantic import BaseModel, Field

from .store import OSBStore
from .queue_client import SQSQueue
from .worker import ProvisioningWorker

app = FastAPI(
    title="Atlassian Edge Open Service Broker API",
    description="Self-service API for internal developers to provision Envoy edge load balancers and route rules",
    version="2.16.0"
)

store = OSBStore()
queue = SQSQueue()
worker = ProvisioningWorker(store, queue)

# Background worker thread
worker_thread = threading.Thread(target=worker.run_loop, daemon=True)
worker_thread.start()

# --- Models ---
class ProvisionInstanceRequest(BaseModel):
    service_id: str = Field(default="edge-routing-service")
    plan_id: str = Field(default="standard")
    organization_guid: str = Field(default="org-atlassian-core")
    space_guid: str = Field(default="space-production")
    parameters: Dict[str, Any] = Field(default_factory=dict)

class CreateBindingRequest(BaseModel):
    service_id: str = Field(default="edge-routing-service")
    plan_id: str = Field(default="standard")
    bind_resource: Optional[Dict[str, Any]] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)

# --- OSB API Specification Endpoints ---

@app.get("/v2/catalog")
def get_catalog():
    """
    Returns the service offerings and plans available for internal teams.
    """
    return {
        "services": [
            {
                "id": "edge-routing-service",
                "name": "edge-routing",
                "description": "Enterprise Envoy Edge Routing and Dynamic Load Balancer Service",
                "bindable": True,
                "instances_retrievable": True,
                "bindings_retrievable": True,
                "plans": [
                    {
                        "id": "standard",
                        "name": "Standard Edge Route",
                        "description": "Dynamic Envoy ingress with health checking and ASAP token validation",
                        "free": True
                    },
                    {
                        "id": "canary",
                        "name": "Canary Edge Route",
                        "description": "Traffic splitting, canary headers, and automated rollback",
                        "free": True
                    },
                    {
                        "id": "enterprise-multi-region",
                        "name": "Global 13-Region Edge",
                        "description": "Multi-region replicated edge deployment with latency-based anycast routing",
                        "free": True
                    }
                ]
            }
        ]
    }

@app.put("/v2/service_instances/{instance_id}")
def provision_service_instance(
    instance_id: str,
    req: ProvisionInstanceRequest,
    accepts_incomplete: bool = Query(False)
):
    """
    Provisions a new edge load balancing instance.
    Decoupled via asynchronous SQS task queue.
    """
    existing = store.get_instance(instance_id)
    if existing:
        return {"description": "Instance already exists", "dashboard_url": f"https://edge.atlassian.net/instances/{instance_id}"}

    op_id = f"op-prov-{uuid.uuid4().hex[:8]}"
    store.set_operation(op_id, "in progress", "Provisioning edge load balancer via worker queue", instance_id)

    # Queue message to SQS
    msg_id = queue.send_message({
        "action": "provision_instance",
        "operation_id": op_id,
        "instance_id": instance_id,
        "service_id": req.service_id,
        "plan_id": req.plan_id,
        "parameters": req.parameters,
        "entity_id": instance_id
    })

    store.log_event("provision_requested", {"instance_id": instance_id, "operation_id": op_id, "sqs_msg_id": msg_id})

    # Return 202 Accepted for asynchronous provisioning
    return {
        "operation": op_id,
        "dashboard_url": f"http://localhost:8080/dashboard?instance={instance_id}",
        "status": "in progress"
    }

@app.get("/v2/service_instances/{instance_id}/last_operation")
def get_instance_last_operation(instance_id: str, operation: Optional[str] = Query(None)):
    """
    Allows developers or CLI to poll the state of an asynchronous provisioning operation.
    """
    if not operation:
        raise HTTPException(status_code=400, detail="operation parameter required")
    op = store.get_operation(operation)
    if not op:
        raise HTTPException(status_code=404, detail="Operation not found")
    return {
        "state": op["state"],
        "description": op["description"]
    }

@app.get("/v2/service_instances/{instance_id}")
def get_service_instance(instance_id: str):
    instance = store.get_instance(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Service instance not found")
    return instance

@app.delete("/v2/service_instances/{instance_id}")
def deprovision_service_instance(instance_id: str, accepts_incomplete: bool = Query(False)):
    existing = store.get_instance(instance_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Service instance not found")

    op_id = f"op-deprov-{uuid.uuid4().hex[:8]}"
    store.set_operation(op_id, "in progress", "Deprovisioning instance", instance_id)
    queue.send_message({
        "action": "deprovision_instance",
        "operation_id": op_id,
        "instance_id": instance_id,
        "entity_id": instance_id
    })
    return {"operation": op_id}

@app.put("/v2/service_instances/{instance_id}/service_bindings/{binding_id}")
def create_service_binding(
    instance_id: str,
    binding_id: str,
    req: CreateBindingRequest,
    accepts_incomplete: bool = Query(False)
):
    """
    Binds a microservice route (e.g. Jira, Confluence) to an edge instance.
    Configures upstreams, path prefix, canary weights, and ASAP auth requirements.
    """
    instance = store.get_instance(instance_id)
    if not instance and not accepts_incomplete:
        # If instance not found yet, we allow creating if queue is processing
        pass

    op_id = f"op-bind-{uuid.uuid4().hex[:8]}"
    store.set_operation(op_id, "in progress", "Configuring routing rules and cluster upstreams", binding_id)

    queue.send_message({
        "action": "create_binding",
        "operation_id": op_id,
        "instance_id": instance_id,
        "binding_id": binding_id,
        "parameters": req.parameters,
        "entity_id": binding_id
    })

    return {
        "operation": op_id,
        "credentials": {
            "edge_ingress_url": f"http://localhost:10000{req.parameters.get('path_prefix', '/' + binding_id)}",
            "asap_audience": f"edge-{instance_id}",
            "route_id": binding_id
        }
    }

@app.get("/v2/service_instances/{instance_id}/service_bindings/{binding_id}")
def get_service_binding(instance_id: str, binding_id: str):
    binding = store.get_binding(binding_id)
    if not binding:
        raise HTTPException(status_code=404, detail="Binding not found")
    return binding

@app.delete("/v2/service_instances/{instance_id}/service_bindings/{binding_id}")
def delete_service_binding(instance_id: str, binding_id: str):
    op_id = f"op-unbind-{uuid.uuid4().hex[:8]}"
    store.set_operation(op_id, "in progress", "Removing route binding from Envoy control plane", binding_id)
    queue.send_message({
        "action": "delete_binding",
        "operation_id": op_id,
        "instance_id": instance_id,
        "binding_id": binding_id,
        "entity_id": binding_id
    })
    return {"operation": op_id}

# --- Management & Telemetry Endpoints ---

@app.get("/api/v1/topology")
def get_full_topology():
    """
    Used by Sovereign Control Plane and Admin Dashboard to fetch current routing topology.
    """
    return {
        "instances": store.list_instances(),
        "bindings": store.list_bindings(),
        "queue_stats": queue.get_stats(),
        "audit_logs": store.get_logs()[-30:]
    }

@app.get("/healthz")
def healthcheck():
    return {"status": "ok", "service": "open-service-broker", "queue": queue.get_stats()}
