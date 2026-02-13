# ArgoCD App of Apps Structure Visualization

```
┌─────────────────────────────────────────────────────────────────┐
│                   anythingllm-bootstrap                         │
│                  (Parent Application)                           │
│                                                                 │
│  One-click deployment entry point                              │
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
│ - platform    │     │ - cluster-... │  │ - rhoai-in..│  │ - hardware-p...│
│ - models      │     │ - rhoai-dep..│  │              │  │ - model-down...│
│ - applications│     │ - nvidia-gp..│  │              │  │ - model-serv...│
│               │     │ - machinesets│  │              │  │                │
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
│   ├─ cluster-discovery           [Synced] [Healthy]            │
│   ├─ rhoai-dependencies          [Synced] [Healthy]            │
│   ├─ nvidia-gpu-operator         [Synced] [Healthy]            │
│   ├─ gpu-machineset-g6e-2xlarge  [Synced] [Healthy]            │
│   ├─ gpu-machineset-g4dn-xlarge  [Synced] [Healthy]            │
│   └─ cpu-machineset-m6a-4xlarge  [Synced] [Healthy]            │
│                                                                 │
│ ▶ rhoai-platform                                                │
│   ├─ rhoai-operator              [Synced] [Healthy]            │
│   └─ rhoai-instance              [Synced] [Healthy]            │
│                                                                 │
│ ▶ rhoai-models                                                  │
│   ├─ model-base-resources        [Synced] [Healthy]            │
│   ├─ hardware-profile-g4dn-...   [Synced] [Healthy]            │
│   ├─ hardware-profile-g6e-2...   [Synced] [Healthy]            │
│   ├─ model-download-qwen3-vl-8b  [Syncing] [Progressing]       │
│   ├─ model-download-qwen3-vl-... [Syncing] [Progressing]       │
│   ├─ model-serving-qwen3-vl-8b   [OutOfSync]                   │
│   └─ model-serving-qwen3-vl-...  [OutOfSync]                   │
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
T+0s    -1      cleanup-hooks          Deploy PreDelete hooks
T+5s     0      cluster-discovery      Gather cluster info
T+5s     0      rhoai-dependencies     Deploy NFD, Kueue, DCGM
T+5s     0      nvidia-gpu-operator    Deploy GPU operator
T+2m     1      machinesets           Provision GPU/CPU nodes
T+2m     1      rhoai-operator        Deploy RHOAI operator
T+5m     2      rhoai-instance        Create DataScienceCluster
T+10m    8      model-base-resources  Create namespace, RBAC
T+10m   10      hardware-profiles     Define GPU profiles
T+11m   11      model-downloads       Download models (5-10min)
T+20m   14      model-serving         Deploy InferenceServices
T+20m   30      eso-operator          Deploy ESO
T+21m   31      eso-secrets           Discover tokens
T+22m   40      anythingllm           Deploy application
```

## Repository Structure

```
Building Block Repositories (unchanged):
  ├─ openshift-infra/
  │  └─ infra/
  │     ├─ cluster-discovery/
  │     ├─ gpu-machineset/
  │     └─ cpu-machineset/
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

GitOps Control Plane (new):
  rhoai-anythingllm-demos/
  └─ anythingllm-generic/
     └─ gitops/
        ├─ anythingllm-bootstrap.yaml      ← Deploy this!
        ├─ anythingllm-complete.yaml       (original monolithic)
        └─ app-of-apps/
           ├─ README.md
           ├─ projects/                     (AppProject definitions)
           └─ applications/                 (Application definitions)
              ├─ infrastructure/
              ├─ platform/
              ├─ models/
              └─ apps/
```
