# ⚡ Sovereign Edge Platform

[![Architecture](https://img.shields.io/badge/Architecture-Atlassian%20Edge%20Infrastructure-0052CC?logo=atlassian)](ARCHITECTURE.md)
[![Envoy](https://img.shields.io/badge/Proxy-Envoy%20xDS%20v3-red?logo=envoyproxy)](https://www.envoyproxy.io/)
[![Rust](https://img.shields.io/badge/Security-Rust%20ASAP%20Sidecar-orange?logo=rust)](services/edge_auth_rust/)
[![FastAPI](https://img.shields.io/badge/Framework-FastAPI-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![AWS](https://img.shields.io/badge/Cloud-13%20AWS%20Regions-232F3E?logo=amazon-aws)](infra/ami_pipeline/)

> **A production-grade implementation of the distributed edge infrastructure, system design, and institutional knowledge shared by Vasilios Syrakis in his viral documentary *"I was laid off by Atlassian"* ([YouTube 55pTFVoclvE](https://www.youtube.com/watch?v=55pTFVoclvE&t=1115s)).**

---

## 🌟 Highlights of the Implemented Architecture

1. **Self-Service Open Service Broker (OSB):**
   - Built on FastAPI with standard OSB v2.16 API endpoints (`/v2/catalog`, `/v2/service_instances`, `/v2/service_bindings`).
   - Decoupled via Amazon SQS task queue and DynamoDB metadata store for asynchronous, non-blocking provisioning.
2. **Sovereign Envoy xDS Control Plane:**
   - Dynamic configuration management server inspired by Syrakis's open-source control plane (`sovereign`).
   - Uses Jinja2 templates to render Envoy LDS, RDS, and CDS JSON definitions.
   - Out-of-band data poller detects service updates and pushes dynamic xDS version snapshots without proxy reloads or downtime.
3. **Rust ASAP Edge Auth Sidecar (`ext_authz`):**
   - High-performance Rust service validating Atlassian Service Authentication Protocol (ASAP) cryptographic JWTs at the proxy edge.
   - Validates signatures, prevents unauthorized requests from touching backends, and injects verified tenant context headers (`X-Authenticated-Caller`, `X-Tenant-Id`).
4. **Declarative AMI Pipeline & Live EC2 Test Harness (Video @ 1115s):**
   - Automated Packer + SaltStack golden image baking recipe with kernel network tuning (`somaxconn=65535`, `file-max=2097152`).
   - Automated 7-point live EC2 test harness that validates the running candidate image before tagging it as `BLESSED`.
   - Multi-region replication and canary rollout orchestrator across Atlassian's 13 global AWS regions.
5. **Interactive Web Portal:**
   - Real-time visual dashboard at `http://localhost:3000` with live metrics, topology maps, xDS inspector, and simulation controls.

---

## 🚀 Quick Start

### 1. Run the End-to-End Simulation

Run the automated CLI demo script that exercises all 5 pillars of the architecture:

```bash
py demo.py
```

### 2. Launch the Interactive Web Dashboard

Launch the unified portal server:

```bash
py web-ui/dashboard_server.py
```

Open your browser to:
👉 **[http://localhost:3000](http://localhost:3000)**

### 3. Run with Docker Compose (Full Stack)

```bash
docker-compose up --build
```

---

## 📁 Repository Structure

```
.
├── ARCHITECTURE.md                  # Detailed timestamp-by-timestamp technical retrospective
├── demo.py                          # 1-click end-to-end interactive simulation script
├── docker-compose.yml               # Multi-container orchestration topology
├── services/
│   ├── service_broker/              # Open Service Broker (FastAPI + SQS worker + DynamoDB store)
│   ├── sovereign_control_plane/     # Dynamic Envoy xDS Control Plane with Jinja2 templates
│   ├── edge_auth_rust/              # Rust ASAP Token Auth Filter & ext_authz sidecar
│   ├── edge_proxy/                  # Envoy Proxy dynamic bootstrap configuration
│   └── mock_workloads/              # Mock Atlassian microservices (Jira, Confluence, Bitbucket)
├── infra/
│   └── ami_pipeline/                # Packer, SaltStack, and Live EC2 Test Harness (Video @ 1115s)
└── web-ui/                          # Interactive visual dashboard and telemetry portal
```

---

## 📖 Deep Dive & Knowledge Reference

For a complete breakdown mapping every architectural concept and timestamp in the video to the source code, see:
👉 **[ARCHITECTURE.md](ARCHITECTURE.md)**
