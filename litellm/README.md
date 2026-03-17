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

## Pre-flight: Create the Master Key Secret

The deployment reads `LITELLM_MASTER_KEY` **and** `POSTGRES_PASSWORD` from a Kubernetes Secret named `litellm-master-key` in the `demo-apps` namespace. **Both values must be present before you run `oc apply`.** If the secret is absent the LiteLLM pod will fail to start with a `CreateContainerConfigError`, blocking the deployment until the secret is in place.

```bash
# Generate a random master key and database password, then create the secret
LITELLM_MASTER_KEY="sk-$(openssl rand -hex 16)"
POSTGRES_PASSWORD="$(openssl rand -hex 16)"

oc create secret generic litellm-master-key \
  --namespace demo-apps \
  --from-literal=LITELLM_MASTER_KEY="${LITELLM_MASTER_KEY}" \
  --from-literal=POSTGRES_PASSWORD="${POSTGRES_PASSWORD}"
```

> **Keep these values private.** `LITELLM_MASTER_KEY` grants full admin access to the LiteLLM dashboard and key-management API. Downstream consumers (e.g. AnythingLLM) **never** receive this key — they get a scoped virtual key instead (see below).

## How Consumer Access Works

After the LiteLLM pod becomes healthy, an ArgoCD **PostSync hook Job** automatically:

1. Calls LiteLLM's `/key/generate` API using the master key
2. Creates a **virtual key** restricted to the two configured models (`qwen3-vl-8b`, `qwen35-27b-fp8`) — no dashboard or admin access
3. Writes the virtual key into a `litellm-consumer` Secret in `demo-apps`

Downstream applications mount `litellm-consumer` to get `LITELLM_API_KEY` and `LITELLM_API_BASE` without ever seeing the master key. If the Job has not yet run (e.g. first deployment is still in progress), downstream pods will fail to start until the secret is available — which is intentional.

> **After a pod restart:** Virtual keys in Postgres survive restarts, so `litellm-consumer` stays valid. If you ever need to rotate the virtual key, delete `litellm-consumer` and re-sync the `litellm-consumer-setup` ArgoCD Application.

## Deployment

1. Create the `litellm-master-key` secret as described above.
2. Apply the bootstrap Application:

```bash
# From the repo root
oc apply -f litellm/gitops/litellm-bootstrap.yaml
```

ArgoCD will sync in waves starting at wave 41, after the existing ESO secrets (wave 35) are ready.

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
│   │           └── litellm-consumer-setup.yaml   # ArgoCD Application → consumer-key-setup/
│   └── consumer-key-setup/
│       ├── rbac.yaml                             # SA, Role, RoleBinding for the key-setup Job
│       └── consumer-key-job.yaml                 # PostSync Job: /key/generate → litellm-consumer Secret
└── README.md
```
