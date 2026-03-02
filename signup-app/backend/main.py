import os
import re
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ANYTHINGLLM_URL = os.getenv("ANYTHINGLLM_URL", "http://anythingllm:3001")
ANYTHINGLLM_API_KEY = os.getenv("ANYTHINGLLM_API_KEY", "")
ANYTHINGLLM_EXTERNAL_URL = os.getenv("ANYTHINGLLM_EXTERNAL_URL", "")
USER_QUOTA = int(os.getenv("USER_QUOTA", "30"))

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_-]{3,32}$")


def allm_headers() -> dict:
    return {
        "Authorization": f"Bearer {ANYTHINGLLM_API_KEY}",
        "Content-Type": "application/json",
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "Startup: ANYTHINGLLM_URL=%s  USER_QUOTA=%d  external_url=%s",
        ANYTHINGLLM_URL,
        USER_QUOTA,
        ANYTHINGLLM_EXTERNAL_URL or "(not set)",
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
      4. Creates personal workspace
      5. Assigns user to workspace
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

        # --- Step 4: Create personal workspace ---
        workspace_name = f"{req.username}'s Workspace"
        ws_resp = await client.post(
            f"{ANYTHINGLLM_URL}/api/v1/workspace/new",
            headers=allm_headers(),
            json={"name": workspace_name},
        )
        if ws_resp.status_code != 200 or not ws_resp.json().get("workspace"):
            logger.error("Workspace creation failed: %s", ws_resp.text)
            raise HTTPException(
                status_code=500,
                detail="User created but workspace creation failed. Please contact the presenter.",
            )

        workspace = ws_resp.json()["workspace"]
        workspace_slug = workspace["slug"]
        logger.info("Created workspace '%s' (slug=%s)", workspace_name, workspace_slug)

        # --- Step 5: Assign user to workspace ---
        assign_resp = await client.post(
            f"{ANYTHINGLLM_URL}/api/v1/admin/workspaces/{workspace_slug}/manage-users",
            headers=allm_headers(),
            json={"userIds": [user_id], "reset": False},
        )
        if assign_resp.status_code != 200:
            logger.warning(
                "Workspace assignment returned %d for user %s", assign_resp.status_code, req.username
            )

        return {
            "success": True,
            "username": req.username,
            "workspaceName": workspace_name,
            "anythingllmUrl": ANYTHINGLLM_EXTERNAL_URL,
        }


# ---------------------------------------------------------------------------
# Serve React SPA (must come after all API routes)
# ---------------------------------------------------------------------------
if os.path.isdir("static"):
    app.mount("/", StaticFiles(directory="static", html=True), name="static")
