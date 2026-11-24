"""
Mock Atlassian Microservices: Jira, Confluence, Bitbucket.
Verifies that downstream services receive injected ASAP context headers (X-Authenticated-Caller, X-Tenant-Id)
from the Envoy edge proxy without implementing their own auth or ingress logic.
"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

def create_mock_service(name: str, port: int):
    app = FastAPI(title=f"Atlassian {name.capitalize()} Microservice")

    @app.get("/health")
    def health():
        return {"status": "healthy", "service": name, "port": port}

    @app.get(f"/api/v1/{name}/ping")
    @app.get(f"/api/{name}")
    @app.get(f"/{name}")
    def service_endpoint(request: Request):
        # Extract headers injected by Envoy & Rust ASAP Auth sidecar
        authenticated_caller = request.headers.get("x-authenticated-caller", "anonymous")
        tenant_id = request.headers.get("x-tenant-id", "unknown-tenant")
        forwarded_by = request.headers.get("x-forwarded-by", "unknown-proxy")
        edge_region = request.headers.get("x-edge-region", "unknown-region")

        return {
            "service": name,
            "status": "success",
            "message": f"Hello from {name.capitalize()} microservice!",
            "edge_context": {
                "authenticated_caller": authenticated_caller,
                "tenant_id": tenant_id,
                "forwarded_by": forwarded_by,
                "edge_region": edge_region
            }
        }

    return app

jira_app = create_mock_service("jira", 8081)
confluence_app = create_mock_service("confluence", 8082)
bitbucket_app = create_mock_service("bitbucket", 8083)
