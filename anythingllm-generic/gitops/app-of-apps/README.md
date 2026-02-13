# App of Apps Structure

This directory implements the ArgoCD "App of Apps" pattern, providing better organization and control over the AnythingLLM demo deployment.

## Benefits

- **Better UI Organization**: Applications are grouped by ArgoCD Projects (infrastructure, platform, models, applications)
- **Easier Resource Management**: Delete entire groups of resources by removing applications
- **Preserved Building Blocks**: All manifests remain in their original repositories
- **One-Click Deployment**: Deploy everything with a single command

## Directory Structure

```
app-of-apps/
├── projects/                           # ArgoCD Project definitions
│   ├── infrastructure-project.yaml    # Infrastructure layer project
│   ├── platform-project.yaml          # Platform layer project
│   ├── models-project.yaml            # Model serving project
│   └── applications-project.yaml      # Applications layer project
│
└── applications/                       # Child Application definitions
    ├── infrastructure/                 # Infrastructure components
    │   ├── cleanup-hooks.yaml         # PreDelete cleanup hooks
    │   ├── cluster-discovery.yaml     # Cluster discovery job
    │   ├── rhoai-dependencies.yaml    # NFD, Kueue, DCGM
    │   ├── nvidia-gpu-operator.yaml   # NVIDIA GPU Operator
    │   ├── gpu-machineset-g6e-2xlarge.yaml
    │   ├── gpu-machineset-g4dn-xlarge.yaml
    │   └── cpu-machineset-m6a-4xlarge.yaml
    │
    ├── platform/                       # Platform components
    │   ├── rhoai-operator.yaml        # RHOAI Operator
    │   └── rhoai-instance.yaml        # DataScienceCluster
    │
    ├── models/                         # Model serving components
    │   ├── model-base-resources.yaml
    │   ├── hardware-profile-g4dn-xlarge.yaml
    │   ├── hardware-profile-g6e-2xlarge.yaml
    │   ├── model-download-qwen3-vl-8b.yaml
    │   ├── model-download-qwen3-vl-embedding-2b.yaml
    │   ├── model-serving-qwen3-vl-8b.yaml
    │   └── model-serving-qwen3-vl-embedding-2b.yaml
    │
    └── apps/                           # Application components
        ├── external-secrets-operator.yaml
        ├── eso-secrets.yaml
        └── anythingllm.yaml
```

## Deployment

### Quick Start - Fully Automated

Deploy the entire stack:

```bash
oc apply -f anythingllm-generic/gitops/anythingllm-bootstrap.yaml
```

**That's it!** The deployment is fully automated through GitOps:

1. **Wave 0**: Cluster discovery job runs and creates cluster-info ConfigMap
2. **Wave 1**: Parameter updater job patches MachineSet Applications with cluster values  
3. **Wave 2**: MachineSets auto-sync and deploy with valid cluster-specific names
4. **Wave 0-40**: All other components deploy in sequence

**No manual scripts. No intervention required. Everything happens through ArgoCD.**

> **Note**: The MachineSet Applications are automatically configured with cluster-specific parameters by a Kubernetes Job. See [MACHINESET-DEPLOYMENT.md](MACHINESET-DEPLOYMENT.md) for architecture details.

### Monitoring Progress

View all applications in the ArgoCD UI, organized by project:
- Infrastructure applications under `rhoai-infrastructure`
- Platform applications under `rhoai-platform`
- Model serving under `rhoai-models`
- Applications under `rhoai-applications`

Or via CLI:

```bash
# View all applications
oc get applications -n openshift-gitops

# View applications by project
oc get applications -n openshift-gitops -l argocd.argoproj.io/project=rhoai-infrastructure
```

## Sync Wave Order

Applications deploy in the following order:

- **Wave -1**: Cleanup hooks
- **Wave 0**: Cluster discovery, RHOAI dependencies, GPU operators
- **Wave 1**: MachineSets, RHOAI operator
- **Wave 2**: RHOAI instance (DataScienceCluster)
- **Wave 8**: Model base resources
- **Wave 10**: Hardware profiles
- **Wave 11**: Model download jobs
- **Wave 14**: Model serving (InferenceServices)
- **Wave 30**: External Secrets Operator
- **Wave 31**: ESO secrets
- **Wave 40**: AnythingLLM application

## Selective Operations

### Delete Specific Layer

Remove just the model serving layer:

```bash
oc delete application -n openshift-gitops \
  model-base-resources \
  hardware-profile-g4dn-xlarge \
  hardware-profile-g6e-2xlarge \
  model-download-qwen3-vl-8b \
  model-download-qwen3-vl-embedding-2b \
  model-serving-qwen3-vl-8b \
  model-serving-qwen3-vl-embedding-2b
```

### Sync Specific Application

```bash
argocd app sync anythingllm
```

### Refresh Without Syncing

```bash
argocd app get anythingllm --refresh
```

## Cleanup

### Remove Everything

Delete the bootstrap application (this will cascade and remove all child applications):

```bash
oc delete -f anythingllm-generic/gitops/anythingllm-bootstrap.yaml
```

**Note**: The PreDelete hook will automatically clean up orphaned API services to prevent hanging deletions.

### Remove Specific Project

```bash
# Delete all applications in a project
oc delete applications -n openshift-gitops -l argocd.argoproj.io/project=rhoai-models

# Then delete the project itself
oc delete appproject -n openshift-gitops rhoai-models
```

## Building Block Repositories

All actual manifests remain in their original repositories:

- **openshift-infra**: Cluster discovery, MachineSets
- **rhoai-deploy**: RHOAI operators, dependencies, GPU operators
- **rhoai-model-serving**: Models, hardware profiles, serving runtimes
- **anythingllm-on-ocp**: AnythingLLM Helm charts
- **rhoai-anythingllm-demos**: ESO operator/secrets, hooks

The App of Apps structure only contains ArgoCD Application definitions that reference these building blocks.

## Comparison with Previous Approach

### Before (Monolithic)

- Single Application with multiple sources
- All resources shown in one flat view in ArgoCD UI
- Delete all or manually delete individual resources
- Uses `default` ArgoCD project

### After (App of Apps)

- Multiple Applications organized by ArgoCD Projects
- Resources grouped by logical layers in ArgoCD UI
- Delete by application or by entire project
- Granular RBAC and governance per project
- Same building block repositories
- Same sync wave ordering
- Same one-click deployment

## Troubleshooting

### Application Not Syncing

Check the application status:

```bash
oc describe application <app-name> -n openshift-gitops
```

### Sync Wave Issues

Applications will wait for previous waves to complete. Check if earlier waves have issues:

```bash
oc get applications -n openshift-gitops --sort-by=.metadata.annotations.argocd\\.argoproj\\.io/sync-wave
```

### Source Repository Issues

Verify the application can access the source repository:

```bash
argocd app get <app-name> --show-operation
```
