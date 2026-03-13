# AnythingLLM Signup App

A self-service signup app for demo presentations. Attendees open this app, enter a username and password, and immediately get a personal AnythingLLM user account and workspace — ready to use with the already-configured LLM.

**Features:**
- Mobile-friendly UI with real-time slot availability indicator
- Checks username availability before provisioning
- Enforces a configurable user quota (counts all users, including externally created ones)
- Deploys to OpenShift alongside AnythingLLM via a single `oc apply` command
- Built in-cluster from source using OpenShift BuildConfig (no external registry needed)

---

## Architecture

```
Browser → React UI (static) ─┐
                              ├─ FastAPI (port 8080) ── AnythingLLM API /v1/*
                              │
               OpenShift BuildConfig builds image from this Git repo
               Image stored in in-cluster ImageStream
               ArgoCD manages all resources via Helm chart
```

---

## Prerequisites

- OpenShift 4.x cluster with OpenShift GitOps (ArgoCD) installed
- AnythingLLM deployed and running in the `demo-apps` namespace
- **Multi-user mode enabled** in AnythingLLM (`Settings → Security → Enable multi-user mode`)
- An AnythingLLM admin API key (see below)
- `oc` CLI logged in as cluster admin

---

## Step 1 — Enable Multi-User Mode & Create an API Key

> These steps are performed once in the AnythingLLM UI.

1. Open AnythingLLM and go to **Settings → Security**.
2. Enable **Multi-User Mode** and set an admin password if prompted.
3. Go to **Settings → API Keys** and click **Generate New API Key**.
4. Copy the key — you will need it in the next step.

See the [AnythingLLM API docs](https://docs.useanything.com/features/api) for more detail.

---

## Step 2 — Create the Secret

Create the secret in the `demo-apps` namespace **before** deploying:

```bash
oc create secret generic anythingllm-signup-secret \
  --from-literal=ANYTHINGLLM_API_KEY=<your-api-key> \
  -n demo-apps
```

---

## Step 3 — Configure the GitOps Application

Edit [`gitops/signup-app.yaml`](gitops/signup-app.yaml) and set the following values under `spec.source.helm.values`:

| Value | Description |
|-------|-------------|
| `userQuota` | Maximum number of users allowed to sign up (default: `30`) |
| `anythingllmUrl` | Internal cluster URL for AnythingLLM (default points to `anythingllm.demo-apps.svc.cluster.local:3001`) |
| `anythingllmRouteName` | Name of the AnythingLLM OpenShift Route to auto-discover the public URL from (default: `anythingllm`) |
| `anythingllmExternalUrl` | *(Optional)* Overrides the auto-discovered URL. Leave blank to let the Helm chart look up the Route automatically. |
| `git.repoURL` | Git repo URL (update if you've forked this repo) |

Example snippet:
```yaml
helm:
  values: |
    namespace: demo-apps
    userQuota: 25
    anythingllmUrl: "http://anythingllm.demo-apps.svc.cluster.local:3001"
    anythingllmExternalUrl: "https://anythingllm-demo-apps.apps.your-cluster.example.com"
    git:
      repoURL: "https://github.com/your-org/rhoai-anythingllm-demos.git"
      ref: main
      contextDir: signup-app
```

---

## Step 4 — Deploy (Single Command)

```bash
oc apply -f signup-app/gitops/signup-app.yaml
```

### Alternative: Deploy with inline overrides (no file edits)

Use `argocd app create --upsert` with `--helm-set` flags to deploy without modifying any files — useful for quick testing:

```bash
argocd app create anythingllm-signup-app \
  --repo https://github.com/dandawg/rhoai-anythingllm-demos.git \
  --revision signup-app \
  --path signup-app/helm \
  --dest-server https://kubernetes.default.svc \
  --project default \
  --helm-set userQuota=25 \
  --helm-set anythingllmUrl=http://anythingllm.demo-apps.svc.cluster.local:3001 \
  --helm-set anythingllmExternalUrl=https://anythingllm-demo-apps.apps.your-cluster.example.com \
  --helm-set git.repoURL=https://github.com/dandawg/rhoai-anythingllm-demos.git \
  --helm-set git.ref=signup-app \
  --sync-policy automated \
  --upsert
```

The `--upsert` flag creates the Application if it doesn't exist, or updates it in place if it does. `--helm-set` values override `values.yaml` without touching the file. Note that the `anythingllm-signup-secret` must still be created manually before deploying (see [Step 2](#step-2--create-the-secret)).

ArgoCD will:
1. Create the ImageStream and BuildConfig (sync wave 1–2)
2. Trigger an in-cluster Docker build from this Git repo
3. Deploy the app once the build completes (sync wave 3)
4. Expose it via an HTTPS Route

### Monitor the build

```bash
# Watch build progress
oc logs -n demo-apps -l buildconfig=anythingllm-signup-app --follow

# Or list builds
oc get builds -n demo-apps
```

### Get the signup app URL

```bash
echo "https://$(oc get route anythingllm-signup-app -n demo-apps -o jsonpath='{.spec.host}')"
```

Share this URL with your audience.

---

## Updating the Quota

The quota is stored in a ConfigMap (not the secret), so it can be updated without touching credentials.

1. Edit the `userQuota` value in `gitops/signup-app.yaml`
2. Commit and push to Git
3. ArgoCD will update the ConfigMap on the next sync
4. Restart the pod to pick up the change:

```bash
oc rollout restart deployment/anythingllm-signup-app -n demo-apps
```

Or, for an immediate update without editing Git:

```bash
oc set env deployment/anythingllm-signup-app USER_QUOTA=40 -n demo-apps
```

---

## Rebuilding After Code Changes

If you update the app source code, trigger a new build:

```bash
oc start-build anythingllm-signup-app -n demo-apps --follow
```

The deployment will automatically roll over once the new image is pushed to the ImageStream.

---

## Cleanup — Deleting Demo Users

Use the included utility script to delete users after your demo session.

### Setup

```bash
cd signup-app/scripts
pip install requests python-dotenv   # python-dotenv is optional

# Create a .env file for convenience
cat > .env <<EOF
ANYTHINGLLM_URL=https://anythingllm-demo-apps.apps.your-cluster.example.com
ANYTHINGLLM_API_KEY=your-api-key
EOF
```

### Usage

```bash
# Preview what would be deleted (safe — no changes made)
python cleanup-users.py --exclude admin --dry-run

# Delete all users except your admin/presenter accounts
python cleanup-users.py --exclude admin,presenter

# Delete specific users only
python cleanup-users.py --include alice,bob,charlie

# Delete ALL users (no exclusions)
python cleanup-users.py --exclude ""
```

The script will prompt for confirmation before deleting.

---

## Teardown

To remove the signup app from the cluster:

```bash
oc delete application anythingllm-signup-app -n openshift-gitops
```

This cascades and deletes all associated resources (Deployment, Service, Route, BuildConfig, ConfigMap, ImageStream). The `anythingllm-signup-secret` is not managed by ArgoCD and must be deleted separately if desired:

```bash
oc delete secret anythingllm-signup-secret -n demo-apps
```

> **Note:** Due to OpenShift build lifecycle, the `BuildConfig`, `ImageStream`, and `Build` objects may be left behind if a build is in progress or recently failed when the application is deleted. Clean them up manually if needed:
>
> ```bash
> oc delete buildconfig,imagestream,build -l app=anythingllm-signup-app -n demo-apps
> ```

---

## Local Development

You can run the backend and frontend separately for local development.

### Backend

```bash
cd backend
pip install -r requirements.txt

export ANYTHINGLLM_URL=https://your-anythingllm-instance.example.com
export ANYTHINGLLM_API_KEY=your-api-key
export USER_QUOTA=30

uvicorn main:app --reload --port 8080
```

### Frontend

```bash
cd frontend
npm install
npm run dev   # proxies /api/* to http://localhost:8080
```

Open http://localhost:5173.

---

## Project Structure

```
signup-app/
├── Dockerfile               # Multi-stage: Node (React build) → Python (FastAPI + static)
├── backend/
│   ├── main.py              # FastAPI: /api/health, /api/quota, /api/signup
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.tsx          # Signup form, quota bar, success view
│   │   └── App.css          # Dark theme, mobile-first styles
│   ├── package.json
│   ├── vite.config.ts
│   └── index.html
├── helm/
│   ├── Chart.yaml
│   ├── values.yaml
│   └── templates/
│       ├── buildconfig.yaml
│       ├── configmap.yaml
│       ├── deployment.yaml
│       ├── imagestream.yaml
│       ├── route.yaml
│       └── service.yaml
├── gitops/
│   └── signup-app.yaml      # ArgoCD Application — the single deploy command target
└── scripts/
    └── cleanup-users.py     # Post-demo user cleanup utility
```
