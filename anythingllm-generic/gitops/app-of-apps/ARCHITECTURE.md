# ArgoCD App of Apps Structure Visualization

```
┌─────────────────────────────────────────────────────────────────┐
│                   anythingllm-bootstrap                         │
│                  (Parent Application)                           │
│                                                                 │
│  Prerequisites: Deploy MachineSets first using script          │
│  ./anythingllm-generic/scripts/deploy-machinesets.sh           │
│                                                                 │
│  Then apply bootstrap:                                         │
│  oc apply -f gitops/anythingllm-bootstrap.yaml                 │
└────────────────────┬───────────────────────────────────────────┘
                     │
                     │ Creates
                     │
        ┌────────────┴────────────┬───────────────┬──────────────┐
        │                         │               │              │
        ▼                         ▼               ▼              ▼
┌───────────────┐     ┌───────────────┐  ┌──────────────┐  ┌────────────────┐
│   Projects    │     │Infrastructure │  │   Platform   │  │     Models     │
│               │     │               │  │              │  │                │
│ - infrastr... │     │ - cleanup-... │  │ - rhoai-op..│  │ - model-base...│
│ - platform    │     │ - rhoai-dep..│  │ - rhoai-in..│  │ - hardware-p...│
│ - models      │     │ - nvidia-gp..│  │              │  │ - model-down...│
│ - applications│     │ - machinesets│  │              │  │ - model-serv...│
│               │     │   (deployed  │  │              │  │                │
│               │     │   by script) │  │              │  │                │
└───────────────┘     └───────┬───────┘  └──────┬───────┘  └───────┬────────┘
                              │                 │                  │
                              │                 │                  │
                              ▼                 ▼                  ▼
                      ┌───────────────┐  ┌──────────────┐  ┌────────────────┐
                      │openshift-infra│  │ rhoai-deploy │  │rhoai-model-... │
                      │    (repo)     │  │    (repo)    │  │    (repo)      │
                      └───────────────┘  └──────────────┘  └────────────────┘
                              
        ┌─────────────────────┘
        │
        ▼
┌──────────────────┐
│  Applications    │
│                  │
│ - eso-operator   │
│ - eso-secrets    │
│ - anythingllm    │
└─────────┬────────┘
          │
          ▼
┌──────────────────────┐
│  rhoai-anythingllm-  │
│  demos (repo)        │
│  anythingllm-on-ocp  │
│  (repo)              │
└──────────────────────┘
```

## ArgoCD Projects View

```
┌─────────────────────────────────────────────────────────────────┐
│ ArgoCD UI - Projects                                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ ▶ rhoai-infrastructure                                          │
│   ├─ cleanup-hooks               [Synced] [Healthy]            │
│   ├─ rhoai-dependencies          [Synced] [Healthy]            │
│   ├─ nvidia-gpu-operator         [Synced] [Healthy]            │
│   ├─ gpu-machineset-g6e-2xlarge  [Synced] [Healthy]            │
│   └─ cpu-machineset-m6a-4xlarge  [Synced] [Healthy]            │
│                                                                 │
│ ▶ rhoai-platform                                                │
│   ├─ rhoai-operator              [Synced] [Healthy]            │
│   └─ rhoai-instance              [Synced] [Healthy]            │
│                                                                 │
│ ▶ rhoai-models                                                  │
│   ├─ model-base-resources        [Synced] [Healthy]            │
│   ├─ hardware-profile-g6e-2...   [Synced] [Healthy]            │
│   ├─ model-download-qwen3-vl-8b  [Syncing] [Progressing]       │
│   └─ model-serving-qwen3-vl-8b   [OutOfSync]                   │
│                                                                 │
│ ▶ rhoai-applications                                            │
│   ├─ external-secrets-operator   [Synced] [Healthy]            │
│   ├─ eso-secrets                 [Synced] [Healthy]            │
│   └─ anythingllm                 [OutOfSync]                   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Deployment Flow

```
Time    Wave    Component               Action
──────────────────────────────────────────────────────────────
T-5m    N/A     Script Deployment      Run deploy-machinesets.sh
                                       - Auto-discover cluster info
                                       - Create ArgoCD Applications
                                       - Set Helm parameters
                                       - Sync MachineSets
T+0s    -1      cleanup-hooks          Deploy PreDelete hooks
T+0s     0      machinesets            Provisioning nodes (deployed by script)
T+0s     0      rhoai-dependencies     Deploy NFD, Kueue, DCGM
T+0s     0      nvidia-gpu-operator    Deploy GPU operator
T+5m     1      rhoai-operator         Deploy RHOAI operator
T+10m    2      rhoai-instance         Create DataScienceCluster
T+15m    8      model-base-resources   Create namespace, RBAC
T+15m   10      hardware-profiles      Define GPU profiles
T+16m   11      model-downloads        Download models (5-10min)
T+25m   14      model-serving          Deploy InferenceServices
T+25m   30      eso-operator           Deploy ESO
T+26m   31      eso-secrets            Discover tokens
T+27m   40      anythingllm            Deploy application
```

## Repository Structure

```
Building Block Repositories (unchanged):
  ├─ openshift-infra/
  │  └─ infra/
  │     ├─ gpu-machineset/
  │     │  └─ aws/
  │     │     ├─ deploy.sh           ← GPU deployment script
  │     │     └─ helm/
  │     └─ cpu-machineset/
  │        └─ aws/
  │           ├─ deploy.sh           ← CPU deployment script
  │           └─ helm/
  │
  ├─ rhoai-deploy/
  │  └─ platform/
  │     ├─ rhoai-operator/
  │     └─ nvidia-gpu-operator/
  │
  ├─ rhoai-model-serving/
  │  └─ platform/
  │     ├─ models/
  │     └─ hardware-profiles/
  │
  └─ anythingllm-on-ocp/
     └─ helm/

GitOps Control Plane:
  rhoai-anythingllm-demos/
  └─ anythingllm-generic/
     ├─ scripts/
     │  ├─ deploy-machinesets.sh     ← Run this FIRST!
     │  └─ README.md
     └─ gitops/
        ├─ anythingllm-bootstrap.yaml ← Then deploy this!
        ├─ anythingllm-complete.yaml   (original monolithic)
        └─ app-of-apps/
           ├─ README.md
           ├─ projects/                (AppProject definitions)
           └─ applications/            (Application definitions)
              ├─ infrastructure/
              ├─ platform/
              ├─ models/
              └─ apps/
```
