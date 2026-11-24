"""
Asynchronous Provisioning Worker for Open Service Broker.
Consumes messages from SQS queue, provisions routing topologies,
and notifies Sovereign control plane of updated cluster / route configurations.
"""
import time
import logging
from typing import Dict, Any
from .store import OSBStore
from .queue_client import SQSQueue

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [OSB-Worker] %(message)s")
logger = logging.getLogger("osb_worker")

class ProvisioningWorker:
    def __init__(self, store: OSBStore, queue: SQSQueue):
        self.store = store
        self.queue = queue
        self._running = False

    def process_one_message(self) -> bool:
        messages = self.queue.receive_messages(max_number=1)
        if not messages:
            return False

        msg = messages[0]
        body = msg["Body"]
        action = body.get("action")
        operation_id = body.get("operation_id")
        receipt_handle = msg["ReceiptHandle"]

        logger.info(f"Processing task: action={action}, operation_id={operation_id}")

        try:
            if action == "provision_instance":
                self._handle_provision_instance(body)
            elif action == "deprovision_instance":
                self._handle_deprovision_instance(body)
            elif action == "create_binding":
                self._handle_create_binding(body)
            elif action == "delete_binding":
                self._handle_delete_binding(body)
            else:
                logger.warning(f"Unknown task action: {action}")

            self.store.set_operation(operation_id, "succeeded", f"Operation {action} completed successfully", body.get("entity_id", ""))
            self.store.log_event("operation_success", {"operation_id": operation_id, "action": action})
            self.queue.delete_message(receipt_handle)
            logger.info(f"Completed task: operation_id={operation_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to process task: {e}", exc_info=True)
            self.store.set_operation(operation_id, "failed", str(e), body.get("entity_id", ""))
            self.store.log_event("operation_failure", {"operation_id": operation_id, "error": str(e)})
            self.queue.delete_message(receipt_handle)
            return True

    def _handle_provision_instance(self, body: Dict[str, Any]):
        instance_id = body["instance_id"]
        parameters = body.get("parameters", {})
        plan_id = body.get("plan_id", "standard")

        # Provision virtual host, dedicated VIP, domain mapping
        assigned_domain = parameters.get("domain", f"{instance_id}.atlassian.internal")
        assigned_vip = parameters.get("vip", f"10.240.{hash(instance_id) % 250}.10")

        self.store.save_instance(instance_id, {
            "instance_id": instance_id,
            "service_id": body.get("service_id", "edge-routing-service"),
            "plan_id": plan_id,
            "domain": assigned_domain,
            "vip": assigned_vip,
            "status": "ready",
            "parameters": parameters,
            "created_at": time.time()
        })
        logger.info(f"Instance {instance_id} provisioned with domain {assigned_domain} and VIP {assigned_vip}")

    def _handle_deprovision_instance(self, body: Dict[str, Any]):
        instance_id = body["instance_id"]
        self.store.delete_instance(instance_id)
        logger.info(f"Instance {instance_id} deprovisioned")

    def _handle_create_binding(self, body: Dict[str, Any]):
        binding_id = body["binding_id"]
        instance_id = body["instance_id"]
        parameters = body.get("parameters", {})

        service_name = parameters.get("service_name", binding_id)
        path_prefix = parameters.get("path_prefix", f"/{service_name}")
        upstreams = parameters.get("upstreams", [f"127.0.0.1:8080"])
        health_check_path = parameters.get("health_check_path", "/health")
        asap_required = parameters.get("asap_required", True)
        canary_weight = parameters.get("canary_weight", 0)
        rate_limit_rps = parameters.get("rate_limit_rps", 500)

        self.store.save_binding(binding_id, {
            "binding_id": binding_id,
            "instance_id": instance_id,
            "service_name": service_name,
            "path_prefix": path_prefix,
            "upstreams": upstreams,
            "health_check_path": health_check_path,
            "asap_required": asap_required,
            "canary_weight": canary_weight,
            "rate_limit_rps": rate_limit_rps,
            "status": "active",
            "created_at": time.time()
        })
        logger.info(f"Binding {binding_id} bound to instance {instance_id} (Path: {path_prefix}, Upstreams: {upstreams})")

    def _handle_delete_binding(self, body: Dict[str, Any]):
        binding_id = body["binding_id"]
        self.store.delete_binding(binding_id)
        logger.info(f"Binding {binding_id} deleted")

    def run_loop(self, poll_interval: float = 1.0):
        self._running = True
        logger.info("Provisioning worker loop started...")
        while self._running:
            processed = self.process_one_message()
            if not processed:
                time.sleep(poll_interval)
