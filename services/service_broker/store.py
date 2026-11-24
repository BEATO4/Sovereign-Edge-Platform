"""
DynamoDB-compatible metadata and state store for Open Service Broker.
Persists service instances, bindings, operation states, and audit logs.
"""
import json
import os
import time
from typing import Dict, Any, Optional

DATA_FILE = os.path.join(os.path.dirname(__file__), "osb_store.json")

class OSBStore:
    def __init__(self, storage_path: str = DATA_FILE):
        self.storage_path = storage_path
        self._data: Dict[str, Any] = {
            "instances": {},
            "bindings": {},
            "operations": {},
            "audit_logs": []
        }
        self._load()

    def _load(self):
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except Exception:
                pass

    def _save(self):
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)

    def save_instance(self, instance_id: str, data: Dict[str, Any]):
        self._data["instances"][instance_id] = {
            **data,
            "updated_at": time.time()
        }
        self._save()

    def get_instance(self, instance_id: str) -> Optional[Dict[str, Any]]:
        return self._data["instances"].get(instance_id)

    def delete_instance(self, instance_id: str):
        if instance_id in self._data["instances"]:
            del self._data["instances"][instance_id]
            self._save()

    def list_instances(self) -> Dict[str, Any]:
        return self._data["instances"]

    def save_binding(self, binding_id: str, data: Dict[str, Any]):
        self._data["bindings"][binding_id] = {
            **data,
            "updated_at": time.time()
        }
        self._save()

    def get_binding(self, binding_id: str) -> Optional[Dict[str, Any]]:
        return self._data["bindings"].get(binding_id)

    def delete_binding(self, binding_id: str):
        if binding_id in self._data["bindings"]:
            del self._data["bindings"][binding_id]
            self._save()

    def list_bindings(self) -> Dict[str, Any]:
        return self._data["bindings"]

    def set_operation(self, operation_id: str, state: str, description: str, entity_id: str):
        self._data["operations"][operation_id] = {
            "state": state,
            "description": description,
            "entity_id": entity_id,
            "updated_at": time.time()
        }
        self._save()

    def get_operation(self, operation_id: str) -> Optional[Dict[str, Any]]:
        return self._data["operations"].get(operation_id)

    def log_event(self, action: str, details: Dict[str, Any]):
        log_entry = {
            "timestamp": time.time(),
            "action": action,
            "details": details
        }
        self._data["audit_logs"].append(log_entry)
        if len(self._data["audit_logs"]) > 200:
            self._data["audit_logs"] = self._data["audit_logs"][-200:]
        self._save()

    def get_logs(self):
        return self._data.get("audit_logs", [])
