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
- `oc` CLI logged in as cluster admin

### API Key Requirement

The signup app authenticates to AnythingLLM using an admin API key injected via the `anythingllm-admin` secret (`ANYTHINGLLM_API_KEY` key). How you satisfy this depends on your setup:

**If you deployed AnythingLLM using the `litellm` setup in this repo (recommended):**
The `anythingllm-setup` PostSync job handles everything automatically — it enables multi-user mode and generates the API key, saving it directly into the `anythingllm-admin` secret. Just make sure that job has completed successfully before deploying the signup app. No manual steps needed.

```bash
# Verify the key is present before deploying
oc get secret anythingllm-admin -n demo-apps -o jsonpath='{.data.ANYTHINGLLM_API_KEY}' | base64 -d && echo
```

**If you're running a standalone AnythingLLM instance:**
Generate an API key manually in the AnythingLLM UI (**Settings → API Keys → Generate New API Key**), then add it to the `anythingllm-admin` secret:

```bash
oc patch secret anythingllm-admin -n demo-apps \
  --type='json' \
  -p='[{"op":"add","path":"/data/ANYTHINGLLM_API_KEY","value":"'$(echo -n "<your-api-key>" | base64)'"}]'
```

> If the `anythingllm-admin` secret doesn't exist yet in your standalone setup, create it:
> ```bash
> oc create secret generic anythingllm-admin \
>   --from-literal=ANYTHINGLLM_API_KEY=<your-api-key> \
>   -n demo-apps
> ```

---

## Step 1 — Configure the GitOps Application

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

## Step 2 — Deploy (Single Command)

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

The `--upsert` flag creates the Application if it doesn't exist, or updates it in place if it does. `--helm-set` values override `values.yaml` without touching the file. Ensure the `anythingllm-setup` job has run at least once before deploying so that the `ANYTHINGLLM_API_KEY` is present in the `anythingllm-admin` secret.

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

### Presenter pages

The app includes two additional routes intended for the presenter, not attendees.

**QR code page (`/qr`)**

Displays a large QR code that attendees can scan to open the signup page on their own device. The QR code encodes the root signup URL automatically. Pull this up on a projector or share screen at the start of your session.

```bash
echo "https://$(oc get route anythingllm-signup-app -n demo-apps -o jsonpath='{.spec.host}')/qr"
```

**Stats page (`/stats`)**

Shows a live view of how many slots have been used versus the configured quota. Useful for monitoring signup progress during a demo.

```bash
echo "https://$(oc get route anythingllm-signup-app -n demo-apps -o jsonpath='{.spec.host}')/stats"
```

> Both pages are client-side routes served by the same deployment — no extra configuration is needed.

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

The OpenShift BuildConfig clones the app from Git — it does **not** use your local working directory. You must commit and push your changes before triggering a build, otherwise the build will use the previously committed code.

```bash
git add signup-app/backend/main.py   # (or whichever files changed)
git commit -m "your change message"
git push
oc start-build anythingllm-signup-app -n demo-apps --follow
```

The deployment will automatically roll over once the new image is pushed to the ImageStream.

> **First deploy note:** On initial deploy ArgoCD creates the BuildConfig and triggers the first build automatically (sync wave 1–2), then waits for the image before deploying the app (sync wave 3). This can take a few minutes. Monitor progress with:
> ```bash
> oc logs -n demo-apps -l buildconfig=anythingllm-signup-app --follow
> ```

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

# Delete all non-admin users (accounts with role "admin" are always kept)
python cleanup-users.py --exclude ""
```

The script will prompt for confirmation before deleting. **Admin protection:** users with role `admin` are never removed when you use `--exclude` (including `--exclude ""`). To delete an admin account, use `--include` with that username explicitly (for example `python cleanup-users.py --include oldadmin`).

### Workspace cleanup

Same env vars as above. Tokens match a workspace **slug** or **name** exactly (case-insensitive).

```bash
python cleanup-workspaces.py --exclude work,thinking --dry-run
python cleanup-workspaces.py --exclude work,thinking
python cleanup-workspaces.py --include alice-s-workspace,demo-ws
```

### Create per-user workspaces (shared model name)

Creates a workspace for each selected user, grants them access, and sets `chatModel` to the name you provide (same endpoint/token as the rest of the instance). Optional `--chat-provider` if you must set it explicitly (for example `generic-openai`).

```bash
python create-user-workspaces.py --model-name qwen3-vl-8b --exclude admin --dry-run
python create-user-workspaces.py --model-name qwen3-vl-8b --exclude admin
python create-user-workspaces.py --model-name my-model --include alice,bob --chat-provider generic-openai
```

---

## Teardown

To remove the signup app from the cluster:

```bash
oc delete application anythingllm-signup-app -n openshift-gitops
```

This cascades and deletes all associated resources (Deployment, Service, Route, BuildConfig, ConfigMap, ImageStream).

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
    ├── cleanup-users.py          # Post-demo user cleanup
    ├── cleanup-workspaces.py     # Workspace cleanup by slug/name
    └── create-user-workspaces.py # Per-user workspace + model name
```
