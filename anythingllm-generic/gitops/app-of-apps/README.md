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
    │   └── cpu-machineset-m6a-4xlarge.yaml
    │
    ├── platform/                       # Platform components
    │   ├── rhoai-operator.yaml        # RHOAI Operator
    │   └── rhoai-instance.yaml        # DataScienceCluster
    │
    ├── models/                         # Model serving components
    │   ├── model-base-resources.yaml
    │   ├── hardware-profile-g6e-2xlarge.yaml
    │   ├── model-download-qwen3-vl-8b.yaml
    │   └── model-serving-qwen3-vl-8b.yaml
    │
    └── apps/                           # Application components
        ├── external-secrets-operator.yaml
        ├── eso-secrets.yaml
        └── anythingllm.yaml
```

## Deployment

### Prerequisites

Before deploying, ensure you have:

1. **OpenShift Cluster**: OpenShift 4.19+ on AWS with cluster-admin access
2. **OpenShift GitOps**: Installed and running (see bootstrap section below)
3. **CLI Tools**: Both `oc` and `argocd` CLI installed
4. **Logged In**: Authenticated to your OpenShift cluster via `oc login`

### Quick Start

**Step 1: Install OpenShift GitOps (if needed)**

```bash
# Clone the openshift-infra repository
git clone https://github.com/dandawg/openshift-infra.git
cd openshift-infra

# Install OpenShift GitOps
./bootstrap.sh
```

**Step 2: Deploy MachineSets**

Deploy CPU and GPU MachineSets using the deployment script:

```bash
# Deploy all machinesets (1 CPU + 1 GPU type)
./anythingllm-generic/scripts/deploy-machinesets.sh

# Or deploy selectively
./anythingllm-generic/scripts/deploy-machinesets.sh --cpu-only
./anythingllm-generic/scripts/deploy-machinesets.sh --gpu-type g6e.2xlarge
```

The script will:
- Auto-discover your cluster information (name, region, availability zone, AMI ID)
- Create ArgoCD Applications for the MachineSets
- Set Helm parameters with cluster-specific values
- Sync the applications to deploy MachineSets

See [scripts/README.md](../../scripts/README.md) for detailed script documentation and troubleshooting.

**Step 3: Deploy Application Stack**

Once MachineSets are deploying, apply the bootstrap application:

```bash
oc apply -f anythingllm-generic/gitops/anythingllm-bootstrap.yaml
```

**That's it!** The rest of the deployment happens automatically through GitOps sync waves.

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
- **Wave 0**: MachineSets, RHOAI dependencies, GPU operators
- **Wave 1**: RHOAI operator
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
  hardware-profile-g6e-2xlarge \
  model-download-qwen3-vl-8b \
  model-serving-qwen3-vl-8b
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

- **openshift-infra**: MachineSets
- **rhoai-deploy**: RHOAI operators, dependencies, GPU operators
- **rhoai-model-serving**: Models, hardware profiles, serving runtimes
- **anythingllm-on-ocp**: AnythingLLM Helm charts
- **rhoai-anythingllm-demos**: ESO operator/secrets, hooks, deployment scripts

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
- MachineSet deployment via local script before bootstrap

## MachineSet Deployment

MachineSets are deployed using a local deployment script **before** applying the bootstrap application. This approach:

- Provides dynamic cluster value discovery
- Avoids in-cluster automation complexity
- Gives clear feedback during deployment
- Works reliably across different cluster configurations

See [scripts/README.md](../../scripts/README.md) for detailed documentation on MachineSet deployment.

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
