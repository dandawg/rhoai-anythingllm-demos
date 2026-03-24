import os
import re
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, field_validator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ANYTHINGLLM_URL = os.getenv("ANYTHINGLLM_URL", "http://anythingllm:3001")
ANYTHINGLLM_API_KEY = os.getenv("ANYTHINGLLM_API_KEY", "")
ANYTHINGLLM_EXTERNAL_URL = os.getenv("ANYTHINGLLM_EXTERNAL_URL", "")
ANYTHINGLLM_ROUTE_NAME = os.getenv("ANYTHINGLLM_ROUTE_NAME", "anythingllm")
USER_QUOTA = int(os.getenv("USER_QUOTA", "30"))

# LiteLLM / OpenAI-compatible model ids per signup workspace (same API base + key, different model name)
SIGNUP_QWEN_CHAT_MODEL = os.getenv("SIGNUP_QWEN_CHAT_MODEL", "qwen3-vl-8b").strip()
SIGNUP_NEMO_CHAT_MODEL = os.getenv("SIGNUP_NEMO_CHAT_MODEL", "nemotron-3-30b-a3b-fp8").strip()
_cp = os.getenv("SIGNUP_CHAT_PROVIDER", "").strip()
SIGNUP_CHAT_PROVIDER: str | None = _cp if _cp else None

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_-]{3,32}$")

# Resolved at startup — either from env var or K8s API discovery
_anythingllm_external_url: str = ""


def _discover_route_url() -> str:
    """
    Query the OpenShift Route for AnythingLLM via the in-cluster Kubernetes API.
    Requires the pod's service account to have 'get' on routes/<name>.
    Returns an empty string if discovery fails or we're not running in-cluster.
    """
    token_file = "/var/run/secrets/kubernetes.io/serviceaccount/token"
    ns_file = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"
    ca_file = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"

    if not os.path.exists(token_file):
        logger.debug("Not running in-cluster; skipping route discovery.")
        return ""

    try:
        token = open(token_file).read().strip()
        namespace = open(ns_file).read().strip()
        url = (
            f"https://kubernetes.default.svc"
            f"/apis/route.openshift.io/v1/namespaces/{namespace}/routes/{ANYTHINGLLM_ROUTE_NAME}"
        )
        resp = httpx.get(url, headers={"Authorization": f"Bearer {token}"}, verify=ca_file, timeout=5.0)
        if resp.status_code == 200:
            host = resp.json().get("spec", {}).get("host", "")
            if host:
                discovered = f"https://{host}"
                logger.info("Discovered AnythingLLM URL from route: %s", discovered)
                return discovered
        logger.warning("Route lookup returned %d; AnythingLLM URL will not be shown.", resp.status_code)
    except Exception as exc:
        logger.warning("Route discovery failed: %s", exc)

    return ""


def allm_headers() -> dict:
    return {
        "Authorization": f"Bearer {ANYTHINGLLM_API_KEY}",
        "Content-Type": "application/json",
    }


async def _provision_user_workspace(
    client: httpx.AsyncClient,
    user_id: int,
    workspace_name: str,
    chat_model: str,
) -> None:
    """Create a workspace, assign the user, and set workspace chatModel (optional chatProvider)."""
    ws_resp = await client.post(
        f"{ANYTHINGLLM_URL}/api/v1/workspace/new",
        headers=allm_headers(),
        json={"name": workspace_name},
    )
    if ws_resp.status_code != 200 or not ws_resp.json().get("workspace"):
        logger.error("Workspace creation failed for %r: %s", workspace_name, ws_resp.text)
        raise HTTPException(
            status_code=500,
            detail="User created but workspace creation failed. Please contact the presenter.",
        )

    workspace = ws_resp.json()["workspace"]
    workspace_slug = workspace["slug"]
    logger.info("Created workspace '%s' (slug=%s)", workspace_name, workspace_slug)

    assign_resp = await client.post(
        f"{ANYTHINGLLM_URL}/api/v1/admin/workspaces/{workspace_slug}/manage-users",
        headers=allm_headers(),
        json={"userIds": [user_id], "reset": False},
    )
    if assign_resp.status_code != 200:
        logger.warning(
            "Workspace assignment returned %d for workspace %r (user id=%d)",
            assign_resp.status_code,
            workspace_name,
            user_id,
        )

    body: dict = {"chatModel": chat_model}
    if SIGNUP_CHAT_PROVIDER:
        body["chatProvider"] = SIGNUP_CHAT_PROVIDER
    safe_slug = quote(workspace_slug, safe="")
    upd = await client.post(
        f"{ANYTHINGLLM_URL}/api/v1/workspace/{safe_slug}/update",
        headers=allm_headers(),
        json=body,
    )
    if upd.status_code != 200:
        logger.error("Workspace model update failed for %r: %s", workspace_name, upd.text)
        raise HTTPException(
            status_code=500,
            detail="Workspace was created but model configuration failed. Please contact the presenter.",
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _anythingllm_external_url
    # Prefer explicit env var; fall back to live route discovery
    _anythingllm_external_url = ANYTHINGLLM_EXTERNAL_URL or _discover_route_url()
    logger.info(
        "Startup: ANYTHINGLLM_URL=%s  USER_QUOTA=%d  qwen_model=%s  nemo_model=%s  external_url=%s",
        ANYTHINGLLM_URL,
        USER_QUOTA,
        SIGNUP_QWEN_CHAT_MODEL,
        SIGNUP_NEMO_CHAT_MODEL,
        _anythingllm_external_url or "(not set — link will not be shown)",
    )
    yield


app = FastAPI(title="AnythingLLM Signup", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class SignupRequest(BaseModel):
    username: str
    password: str

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        v = v.strip().lower()
        if not USERNAME_RE.match(v):
            raise ValueError(
                "Username must be 3–32 characters and contain only letters, numbers, underscores, or hyphens."
            )
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters.")
        return v


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/config")
async def get_config():
    """Return public frontend configuration, including the AnythingLLM external URL."""
    return {"anythingllmUrl": _anythingllm_external_url}


@app.get("/api/quota")
async def get_quota():
    """Return current user count vs configured quota."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                f"{ANYTHINGLLM_URL}/api/v1/admin/users",
                headers=allm_headers(),
            )
        except httpx.RequestError as exc:
            logger.error("Could not reach AnythingLLM: %s", exc)
            raise HTTPException(status_code=502, detail="Could not reach AnythingLLM instance.")

        if resp.status_code != 200:
            logger.error("AnythingLLM returned %d for user list", resp.status_code)
            raise HTTPException(status_code=502, detail="AnythingLLM returned an unexpected response.")

        users = resp.json().get("users", [])
        used = len(users)
        return {
            "used": used,
            "quota": USER_QUOTA,
            "available": max(0, USER_QUOTA - used),
        }


@app.post("/api/signup")
async def signup(req: SignupRequest):
    """
    Provision a new AnythingLLM user and a personal workspace.

    Checks (in order):
      1. Quota not exceeded
      2. Username not already taken
    Then:
      3. Creates user
      4. Creates <username>-qwen3 workspace (Qwen chat model)
      5. Creates <username>-nemo3 workspace (Nemotron chat model)
    """
    async with httpx.AsyncClient(timeout=15.0) as client:
        # --- Step 1 & 2: fetch user list for quota + username checks ---
        try:
            users_resp = await client.get(
                f"{ANYTHINGLLM_URL}/api/v1/admin/users",
                headers=allm_headers(),
            )
        except httpx.RequestError as exc:
            logger.error("Could not reach AnythingLLM: %s", exc)
            raise HTTPException(status_code=502, detail="Could not reach AnythingLLM instance.")

        if users_resp.status_code != 200:
            raise HTTPException(status_code=502, detail="AnythingLLM returned an unexpected response.")

        users = users_resp.json().get("users", [])

        if len(users) >= USER_QUOTA:
            raise HTTPException(
                status_code=429,
                detail="All signup slots are full. Please contact the presenter.",
            )

        existing = {u["username"].lower() for u in users}
        if req.username in existing:
            raise HTTPException(
                status_code=409,
                detail=f"Username '{req.username}' is already taken. Please choose another.",
            )

        # --- Step 3: Create user ---
        create_resp = await client.post(
            f"{ANYTHINGLLM_URL}/api/v1/admin/users/new",
            headers=allm_headers(),
            json={"username": req.username, "password": req.password, "role": "default"},
        )
        if create_resp.status_code != 200 or create_resp.json().get("error"):
            err = create_resp.json().get("error", "Unknown error")
            logger.error("User creation failed: %s", err)
            raise HTTPException(status_code=500, detail=f"Failed to create user: {err}")

        user_id = create_resp.json()["user"]["id"]
        logger.info("Created user '%s' (id=%d)", req.username, user_id)

        # --- Step 4 & 5: Two workspaces (same LLM endpoint/key; different chatModel) ---
        w_qwen = f"{req.username}-qwen3"
        w_nemo = f"{req.username}-nemo3"
        await _provision_user_workspace(client, user_id, w_qwen, SIGNUP_QWEN_CHAT_MODEL)
        await _provision_user_workspace(client, user_id, w_nemo, SIGNUP_NEMO_CHAT_MODEL)

        return {
            "success": True,
            "username": req.username,
            "workspaceNames": [w_qwen, w_nemo],
            "anythingllmUrl": _anythingllm_external_url,
        }


# ---------------------------------------------------------------------------
# Serve React SPA (must come after all API routes)
# ---------------------------------------------------------------------------
_static_dir = Path("static")

if _static_dir.is_dir():
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # Serve real static assets (JS/CSS/images) by exact path.
        # Guard against path traversal before resolving.
        candidate = (_static_dir / full_path).resolve()
        if not str(candidate).startswith(str(_static_dir.resolve())):
            raise HTTPException(status_code=400, detail="Invalid path")
        if candidate.is_file():
            return FileResponse(candidate)
        # Fall back to index.html so React Router handles the route.
        index = _static_dir / "index.html"
        if index.is_file():
            return FileResponse(index)
        raise HTTPException(status_code=404, detail="Not found")
