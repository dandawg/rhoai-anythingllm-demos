# LiteLLM Demo

GitOps deployment of [LiteLLM](https://docs.litellm.ai/) as an OpenAI-compatible proxy over the two RHOAI-hosted models in this demo (`qwen3-vl-8b` and `qwen35-27b-fp8`).

This folder contains only the demo-specific GitOps wiring. The generic LiteLLM Helm chart lives in [litellm-on-ocp](https://github.com/dandawg/litellm-on-ocp).

## What This Deploys

- LiteLLM proxy pre-configured with both RHOAI models via `model_list`
- Bundled PostgreSQL backend — required for the admin UI, virtual key management, and spend tracking
- Model API keys resolved at runtime from the existing `model-api-tokens` ESO secret
- `litellm-consumer` Secret in `demo-apps` auto-created by a PostSync hook; holds a **scoped virtual key** (`LITELLM_API_KEY`) and `LITELLM_API_BASE` for downstream consumers — does not contain the master key
- OpenShift Route with edge TLS

## Prerequisites

This demo add-on assumes the main `anythingllm-generic` demo is already deployed and healthy:

- OpenShift GitOps (ArgoCD) running
- `rhoai-applications` AppProject exists
- ESO is deployed and the `model-api-tokens` Secret exists in `demo-apps`
- Both RHOAI InferenceServices (`qwen3-vl-8b`, `qwen35-27b-fp8`) are ready in the `demo` namespace

## Pre-flight: Create Required Secrets

Two secrets must exist in `demo-apps` before running `oc apply`. Both are managed outside of GitOps (like cluster credentials) and should never be committed to the repo.

### 1. LiteLLM Master Key (`litellm-master-key`)

The deployment reads `LITELLM_MASTER_KEY` **and** `POSTGRES_PASSWORD` from this secret. If absent the LiteLLM pod will fail to start with a `CreateContainerConfigError`.

```bash
LITELLM_MASTER_KEY="sk-$(openssl rand -hex 16)"
POSTGRES_PASSWORD="$(openssl rand -hex 16)"

oc create secret generic litellm-master-key \
  --namespace demo-apps \
  --from-literal=LITELLM_MASTER_KEY="${LITELLM_MASTER_KEY}" \
  --from-literal=POSTGRES_PASSWORD="${POSTGRES_PASSWORD}"
```

> **Keep these values private.** `LITELLM_MASTER_KEY` grants full admin access to the LiteLLM dashboard and key-management API. Downstream consumers (e.g. AnythingLLM) **never** receive this key — they get a scoped virtual key instead (see below).

### 2. AnythingLLM Admin Credentials (`anythingllm-admin`)

The `anythingllm-setup` PostSync Job uses these credentials to create the first admin user, enable multi-user mode, and create the demo workspaces. If absent the Job pod will fail to start.

`JWT_SECRET` is also required here. AnythingLLM writes it to an ephemeral `.env` file on first setup, which is lost on pod restarts. Mounting it from this secret ensures session tokens keep working across restarts.

```bash
ANYTHINGLLM_ADMIN_USER="admin"
ANYTHINGLLM_ADMIN_PASSWORD="$(openssl rand -hex 16)"
ANYTHINGLLM_JWT_SECRET="$(openssl rand -hex 32)"

oc create secret generic anythingllm-admin \
  --namespace demo-apps \
  --from-literal=ANYTHINGLLM_ADMIN_USER="${ANYTHINGLLM_ADMIN_USER}" \
  --from-literal=ANYTHINGLLM_ADMIN_PASSWORD="${ANYTHINGLLM_ADMIN_PASSWORD}" \
  --from-literal=JWT_SECRET="${ANYTHINGLLM_JWT_SECRET}"

# Save the password — you will need it to log in to the AnythingLLM UI
echo "AnythingLLM admin password: ${ANYTHINGLLM_ADMIN_PASSWORD}"
```

> The job is idempotent: on re-syncs it detects that the admin already exists, logs in with the stored credentials, and skips creation steps that have already been completed.

## How Consumer Access Works

After the LiteLLM pod becomes healthy, an ArgoCD **PostSync hook Job** automatically:

1. Calls LiteLLM's `/key/generate` API using the master key
2. Creates a **virtual key** restricted to the two configured models (`qwen3-vl-8b`, `qwen35-27b-fp8`) — no dashboard or admin access
3. Writes the virtual key into a `litellm-consumer` Secret in `demo-apps`

Downstream applications mount `litellm-consumer` to get `LITELLM_API_KEY` and `LITELLM_API_BASE` without ever seeing the master key. If the Job has not yet run (e.g. first deployment is still in progress), downstream pods will fail to start until the secret is available — which is intentional.

> **After a pod restart:** Virtual keys in Postgres survive restarts, so `litellm-consumer` stays valid. If you ever need to rotate the virtual key, delete `litellm-consumer` and re-sync the `litellm-consumer-setup` ArgoCD Application.

## Deployment

1. Create the `litellm-master-key` and `anythingllm-admin` secrets as described above.
2. Apply the bootstrap Application:

```bash
# From the repo root
oc apply -f litellm/gitops/litellm-bootstrap.yaml
```

ArgoCD will sync in waves starting at wave 41, after the existing ESO secrets (wave 35) are ready. AnythingLLM deploys at wave 46, after the `litellm-consumer` Secret is written at wave 45, so the pod always starts with its LiteLLM API key present.

## How It Works

1. The `litellm-bootstrap` ArgoCD Application discovers `litellm.yaml` in `litellm/gitops/app-of-apps/`.
2. `litellm.yaml` renders the `litellm-on-ocp` Helm chart with demo-specific values:
   - `model_list` pointing at both RHOAI InferenceService cluster-internal URLs
   - `api_key: "os.environ/QWEN3_VL_8B_API_KEY"` and `os.environ/QWEN35_27B_FP8_API_KEY` for runtime key injection
   - `envFrom` mounting `model-api-tokens` (managed by ESO) into the LiteLLM pod
3. At startup, LiteLLM reads `config.yaml`, loads both models into Postgres, and resolves the `os.environ/` references from the mounted secret.
4. Once healthy, a PostSync hook Job calls `/key/generate` to create a virtual key scoped to both models and writes it into the `litellm-consumer` Secret in `demo-apps`.

## Downstream Consumption

Other applications in `demo-apps` can point at LiteLLM using the consumer Secret:

```yaml
envFrom:
  - secretRef:
      name: litellm-consumer
# Provides: LITELLM_API_BASE, LITELLM_API_KEY
```

Or reference the keys directly:

```yaml
env:
  - name: OPENAI_API_BASE
    valueFrom:
      secretKeyRef:
        name: litellm-consumer
        key: LITELLM_API_BASE
  - name: OPENAI_API_KEY
    valueFrom:
      secretKeyRef:
        name: litellm-consumer
        key: LITELLM_API_KEY
```

## Directory Structure

```
litellm/
├── gitops/
│   ├── litellm-bootstrap.yaml                    # Applied once manually (oc apply -f)
│   ├── app-of-apps/
│   │   └── applications/
│   │       └── apps/
│   │           ├── litellm.yaml                  # ArgoCD Application → litellm-on-ocp Helm chart
│   │           ├── litellm-consumer-setup.yaml   # ArgoCD Application → consumer-key-setup/ (wave 45)
│   │           └── litellm-anythingllm-setup.yaml # ArgoCD Application → anythingllm-setup/ (wave 50)
│   ├── consumer-key-setup/
│   │   ├── rbac.yaml                             # SA, Role, RoleBinding for the key-setup Job
│   │   └── consumer-key-job.yaml                 # PostSync Job: /key/generate → litellm-consumer Secret
│   └── anythingllm-setup/
│       ├── rbac.yaml                             # SA, Role, RoleBinding for the setup Job
│       └── anythingllm-setup-job.yaml            # PostSync Job: admin setup, multi-user mode, workspaces
└── README.md
```
