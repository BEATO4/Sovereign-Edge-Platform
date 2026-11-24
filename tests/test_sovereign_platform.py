"""
Automated Test Suite for Sovereign Edge Platform.
Validates all subsystems against the architectural principles from Vasilios Syrakis's video.
"""
import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from services.service_broker.main import store as osb_store, queue as osb_queue, worker as osb_worker, app as osb_app
from services.sovereign_control_plane.poller import ConfigPoller
from services.edge_auth_rust.auth_sidecar_runner import create_sample_asap_token, app as auth_app
from infra.ami_pipeline.live_ec2_test_harness import LiveEC2ImageTestHarness
from infra.ami_pipeline.multi_region_dist import MultiRegionRollout, ATLASSIAN_13_REGIONS
from starlette.testclient import TestClient

class TestSovereignEdgePlatform(unittest.TestCase):

    def setUp(self):
        self.osb_client = TestClient(osb_app)
        self.auth_client = TestClient(auth_app)

    def test_01_osb_catalog(self):
        """Validates Open Service Broker API catalog offering."""
        resp = self.osb_client.get("/v2/catalog")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("services", data)
        service = data["services"][0]
        self.assertEqual(service["id"], "edge-routing-service")
        self.assertTrue(len(service["plans"]) >= 3)

    def test_02_osb_async_queue_provisioning(self):
        """Validates decoupled asynchronous route provisioning via SQS."""
        # Enqueue provisioning task
        msg_id = osb_queue.send_message({
            "action": "create_binding",
            "operation_id": "test-op-jira",
            "instance_id": "test-inst-jira",
            "binding_id": "test-bind-jira",
            "parameters": {
                "service_name": "jira-test",
                "path_prefix": "/jira-test",
                "upstreams": ["127.0.0.1:8081"],
                "canary_weight": 20
            },
            "entity_id": "test-bind-jira"
        })
        self.assertTrue(msg_id.startswith("msg-"))

        # Process message with worker
        processed = osb_worker.process_one_message()
        self.assertTrue(processed)

        # Verify saved binding
        binding = osb_store.get_binding("test-bind-jira")
        self.assertIsNotNone(binding)
        self.assertEqual(binding["service_name"], "jira-test")
        self.assertEqual(binding["canary_weight"], 20)

    def test_03_sovereign_dynamic_xds_templates(self):
        """Validates Jinja2 template rendering for Envoy LDS, RDS, CDS."""
        poller = ConfigPoller()
        poller.poll_and_render()

        self.assertTrue(poller.current_version.startswith("v"))
        clusters = poller.get_snapshot("clusters")
        routes = poller.get_snapshot("routes")
        listeners = poller.get_snapshot("listeners")

        # Verify CDS
        self.assertIn("resources", clusters)
        cluster_names = [c["name"] for c in clusters["resources"]]
        self.assertIn("edge_auth_rust_cluster", cluster_names)

        # Verify RDS
        self.assertIn("resources", routes)
        vhosts = routes["resources"][0]["virtual_hosts"]
        self.assertTrue(len(vhosts) > 0)

        # Verify LDS
        self.assertIn("resources", listeners)
        self.assertEqual(listeners["resources"][0]["name"], "edge_ingress_listener")

    def test_04_asap_edge_auth_valid_token(self):
        """Validates that valid ASAP tokens receive HTTP 200 with injected context headers."""
        token = create_sample_asap_token(issuer="jira-client-auth", tenant_id="tenant-apac-1")
        resp = self.auth_client.get("/auth", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("x-authenticated-caller"), "jira-client-auth")
        self.assertEqual(resp.headers.get("x-tenant-id"), "tenant-apac-1")
        self.assertEqual(resp.headers.get("x-asap-token-valid"), "true")

    def test_05_asap_edge_auth_rejected_tokens(self):
        """Validates that expired or missing tokens are blocked with HTTP 401 at the edge."""
        # Missing token
        resp_missing = self.auth_client.get("/auth")
        self.assertEqual(resp_missing.status_code, 401)

        # Expired token
        expired_token = create_sample_asap_token(issuer="rogue-service", expires_in_sec=-200)
        resp_expired = self.auth_client.get("/auth", headers={"Authorization": f"Bearer {expired_token}"})
        self.assertEqual(resp_expired.status_code, 401)
        self.assertIn("Expired", resp_expired.text)

    def test_06_live_ec2_test_harness(self):
        """Validates the 7-point live EC2 test harness (Video timestamp 1115s)."""
        harness = LiveEC2ImageTestHarness(ami_id="ami-test-01")
        harness.boot_test_instance()
        receipt = harness.run_suite()
        harness.terminate_test_instance()

        self.assertEqual(receipt["overall_status"], "BLESSED")
        self.assertEqual(receipt["passed_tests"], 7)
        self.assertEqual(receipt["total_tests"], 7)

    def test_07_multi_region_rollout(self):
        """Validates distribution to 13 AWS regions and phased canary rollout."""
        self.assertEqual(len(ATLASSIAN_13_REGIONS), 13)
        rollout = MultiRegionRollout(blessed_ami_id="ami-test-blessed")
        regional_amis = rollout.copy_ami_to_all_regions()
        self.assertEqual(len(regional_amis), 13)

        stages = rollout.execute_canary_rollout(stages=[5, 25, 100])
        self.assertEqual(len(stages), 3)
        self.assertEqual(stages[-1]["stage_percent"], 100)
        self.assertEqual(stages[-1]["health_check_status"], "ALL_GREEN")

if __name__ == "__main__":
    unittest.main()
