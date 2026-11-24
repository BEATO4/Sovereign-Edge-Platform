"""
Out-of-band Data Poller and Jinja2 Template Engine for Sovereign Control Plane.
Periodically fetches registered service routing topology from Service Broker / DynamoDB store,
evaluates dynamic changes, and re-renders Envoy xDS resource snapshots without downtime.
"""
import os
import json
import hashlib
import time
import logging
from typing import Dict, Any, Optional
from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger("sovereign_poller")

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")

class ConfigPoller:
    def __init__(self, templates_dir: str = TEMPLATES_DIR, broker_store_path: Optional[str] = None):
        self.templates_dir = templates_dir
        self.jinja_env = Environment(
            loader=FileSystemLoader(templates_dir),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True
        )
        self.broker_store_path = broker_store_path or os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "service_broker", "osb_store.json"
        )
        self.current_version: str = "v0"
        self.version_count: int = 0
        self.last_hash: str = ""
        self.snapshots: Dict[str, Any] = {
            "clusters": {"version_info": "v0", "resources": []},
            "routes": {"version_info": "v0", "resources": []},
            "listeners": {"version_info": "v0", "resources": []}
        }
        self.raw_topology: Dict[str, Any] = {}
        # Initial render
        self.poll_and_render()

    def _fetch_topology_from_store(self) -> Dict[str, Any]:
        """Reads service instances and route bindings from OSB state store."""
        if os.path.exists(self.broker_store_path):
            try:
                with open(self.broker_store_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error reading broker store: {e}")
        return {"instances": {}, "bindings": {}}

    def poll_and_render(self) -> bool:
        """
        Polls store, checks for data changes, and updates xDS snapshots.
        Returns True if a new configuration version was rendered.
        """
        topology = self._fetch_topology_from_store()
        raw_repr = json.dumps(topology, sort_keys=True)
        content_hash = hashlib.sha256(raw_repr.encode("utf-8")).hexdigest()[:16]

        if content_hash == self.last_hash and self.version_count > 0:
            return False

        self.last_hash = content_hash
        self.version_count += 1
        self.current_version = f"v{self.version_count}-{content_hash[:8]}"
        self.raw_topology = topology

        instances = topology.get("instances", {})
        bindings = topology.get("bindings", {})

        # 1. Transform bindings into Envoy clusters
        clusters = []
        routes = []

        # Always include the ext_authz Rust cluster
        clusters.append({
            "name": "edge_auth_rust_cluster",
            "endpoints": [{"host": "127.0.0.1", "port": 9001}],
            "health_check_path": "/health"
        })

        # Process each binding created via Open Service Broker
        for binding_id, binding in bindings.items():
            service_name = binding.get("service_name", binding_id)
            cluster_name = f"cluster_{service_name}"
            upstreams = binding.get("upstreams", ["127.0.0.1:8080"])

            endpoints = []
            for u in upstreams:
                if ":" in u:
                    host, port_str = u.split(":", 1)
                    endpoints.append({"host": host, "port": int(port_str)})
                else:
                    endpoints.append({"host": u, "port": 80})

            clusters.append({
                "name": cluster_name,
                "endpoints": endpoints,
                "health_check_path": binding.get("health_check_path", "/health")
            })

            canary_weight = binding.get("canary_weight", 0)
            route_def = {
                "prefix": binding.get("path_prefix", f"/{service_name}"),
                "cluster_name": cluster_name,
                "asap_required": binding.get("asap_required", True)
            }

            if canary_weight > 0 and canary_weight < 100:
                canary_cluster_name = f"{cluster_name}_canary"
                clusters.append({
                    "name": canary_cluster_name,
                    "endpoints": endpoints, # In real deployment points to canary instances
                    "health_check_path": binding.get("health_check_path", "/health")
                })
                route_def["weighted_clusters"] = [
                    {"name": cluster_name, "weight": 100 - canary_weight},
                    {"name": canary_cluster_name, "weight": canary_weight}
                ]

            routes.append(route_def)

        # Build virtual hosts (Default '*' and specific instance domains)
        domains = ["*"]
        for inst_id, inst in instances.items():
            if inst.get("domain"):
                domains.append(inst["domain"])

        virtual_hosts = [
            {
                "name": "default_vhost",
                "domains": domains,
                "routes": routes
            }
        ]

        # 2. Render templates
        template_context = {
            "version_info": self.current_version,
            "clusters": clusters,
            "virtual_hosts": virtual_hosts,
            "listener_port": 10000,
            "ext_authz_enabled": True,
            "ext_authz_host": "127.0.0.1:9001",
            "region": "us-east-1"
        }

        try:
            clusters_template = self.jinja_env.get_template("clusters.j2")
            rendered_clusters = json.loads(clusters_template.render(**template_context))
            self.snapshots["clusters"] = rendered_clusters

            routes_template = self.jinja_env.get_template("routes.j2")
            rendered_routes = json.loads(routes_template.render(**template_context))
            self.snapshots["routes"] = rendered_routes

            listeners_template = self.jinja_env.get_template("listeners.j2")
            rendered_listeners = json.loads(listeners_template.render(**template_context))
            self.snapshots["listeners"] = rendered_listeners

            logger.info(f"Rendered dynamic xDS snapshot version {self.current_version} ({len(clusters)} clusters, {len(routes)} routes)")
            return True

        except Exception as e:
            logger.error(f"Error rendering templates: {e}", exc_info=True)
            return False

    def get_snapshot(self, resource_type: str) -> Dict[str, Any]:
        return self.snapshots.get(resource_type, {"version_info": self.current_version, "resources": []})
