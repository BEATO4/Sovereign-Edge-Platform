"""
Edge Auth Sidecar Runner (Envoy ext_authz compatible).
Implements Atlassian Service Authentication Protocol (ASAP) JWT verification,
tenant identification, and context header injection at the edge.
"""
import time
import jwt
from fastapi import FastAPI, Request, Response, Header
from fastapi.responses import JSONResponse
from typing import Optional

app = FastAPI(
    title="ASAP Edge Auth Sidecar",
    description="Validates cryptographically signed ASAP tokens at the Envoy proxy edge",
    version="1.0.0"
)

# Shared secret / test key for fast signing and verification
SECRET_KEY = "atlassian-asap-edge-shared-secret-key-2026"

def create_sample_asap_token(
    issuer: str = "jira-frontend",
    audience: str = "edge-routing-service",
    tenant_id: str = "tenant-prod-apac",
    expires_in_sec: int = 300
) -> str:
    """Helper to generate standard compliant ASAP JWT tokens."""
    now = int(time.time())
    payload = {
        "iss": issuer,
        "sub": f"user-{tenant_id}",
        "aud": [audience],
        "iat": now,
        "exp": now + expires_in_sec,
        "jti": f"jti-{now}",
        "tenant_id": tenant_id
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

@app.get("/health")
def health():
    return {"status": "healthy", "engine": "asap-edge-auth-sidecar"}

@app.api_route("/auth", methods=["GET", "POST"])
async def ext_authz_handler(request: Request):
    """
    Envoy ext_authz HTTP handler.
    Validates Authorization or X-ASAP-Token header.
    Returns HTTP 200 with injected headers or HTTP 401 if unauthorized.
    """
    auth_header = request.headers.get("authorization")
    asap_header = request.headers.get("x-asap-token")

    token = asap_header
    if not token and auth_header:
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
        else:
            token = auth_header.strip()

    if not token:
        return Response(
            content="Missing ASAP Authentication Token",
            status_code=401,
            headers={"x-asap-error": "missing_token"}
        )

    try:
        # Decode and verify ASAP claims
        claims = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=["HS256", "RS256"],
            options={"verify_exp": True, "verify_aud": False}
        )
        issuer = claims.get("iss", "unknown-service")
        tenant = claims.get("tenant_id", "default-tenant")

        # Injected upstream headers passed to downstream microservices by Envoy
        headers = {
            "x-authenticated-caller": issuer,
            "x-tenant-id": tenant,
            "x-asap-token-valid": "true",
            "x-auth-engine": "rust-asap-sidecar"
        }
        return Response(content="Authorized", status_code=200, headers=headers)

    except jwt.ExpiredSignatureError:
        return Response(
            content="ASAP Token Expired",
            status_code=401,
            headers={"x-asap-error": "token_expired"}
        )
    except Exception as e:
        return Response(
            content=f"ASAP Signature Verification Failed: {str(e)}",
            status_code=401,
            headers={"x-asap-error": "invalid_signature"}
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=9001)
