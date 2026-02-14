# MachineSet Deployment - Fully Automated

This directory includes a fully automated solution for deploying MachineSets with cluster-specific parameters.

## Overview

The deployment uses a **zero-manual-intervention** approach where a Kubernetes Job automatically:
1. Waits for the cluster-discovery job to complete
2. Reads cluster information from the ConfigMap
3. Patches the ArgoCD Application manifests with actual values
4. ArgoCD automatically syncs the MachineSets

**No scripts to run. No manual intervention. Everything happens through GitOps.**

## How It Works

```
┌─────────────────────────────────────────────────────────────┐
│ Wave 0: Cluster Discovery                                   │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Job: cluster-info-discovery                             │ │
│ │  - Queries OpenShift cluster                            │ │
│ │  - Creates ConfigMap: cluster-info                      │ │
│ │    * clusterName, region, availabilityZone, etc.        │ │
│ └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ Wave 1: Automated Parameter Update                         │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Job: machineset-params-updater                          │ │
│ │  1. Waits for cluster-info ConfigMap                    │ │
│ │  2. Reads cluster values                                │ │
│ │  3. Patches ArgoCD Application resources directly       │ │
│ │     - cpu-machineset-m6a-4xlarge                        │ │
│ │     - gpu-machineset-g4dn-xlarge                        │ │
│ │     - gpu-machineset-g6e-2xlarge                        │ │
│ └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ Wave 2: MachineSets Deploy Automatically                   │
│ ┌───────────────────┐  ┌───────────────────┐  ┌──────────┐ │
│ │ cpu-machineset    │  │ gpu-machineset    │  │ gpu-     │ │
│ │ m6a-4xlarge       │  │ g4dn-xlarge       │  │ g6e-2xl  │ │
│ │ (auto-sync: true) │  │ (auto-sync: true) │  │ (auto)   │ │
│ └───────────────────┘  └───────────────────┘  └──────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Architecture Components

### 1. Cluster Discovery (Wave 0)
**Application**: `cluster-discovery`  
**Purpose**: Discovers cluster-specific AWS information  
**Output**: ConfigMap `cluster-info` in `openshift-machine-api` namespace

### 2. Parameter Updater Job (Wave 1)
**Application**: `machineset-params-updater`  
**Purpose**: Automatically updates ArgoCD Applications with cluster values  
**Method**: Kubernetes Job with RBAC to patch Application resources

**Key Features**:
- Runs automatically via sync wave ordering
- Uses service account with minimal RBAC (only Application patch permissions)
- No external tools required (uses `oc` CLI from OpenShift image)
- Self-cleaning (TTL after completion)

### 3. MachineSet Applications (Wave 2)
**Applications**: 
- `cpu-machineset-m6a-4xlarge`
- `gpu-machineset-g4dn-xlarge`
- `gpu-machineset-g6e-2xlarge`

**Configuration**:
- Start with `REPLACE_ME` placeholder values
- Auto-sync enabled after parameter update
- Deploy automatically once parameters are patched

### 4. Bootstrap Application Configuration
**Critical**: The `anythingllm-bootstrap` Application includes `ignoreDifferences` for the MachineSet Applications' helm parameters:

```yaml
ignoreDifferences:
  - group: argoproj.io
    kind: Application
    name: cpu-machineset-m6a-4xlarge
    jsonPointers:
      - /spec/source/helm/parameters
```

**Why this is needed**: Without `ignoreDifferences`, ArgoCD's self-heal would detect the Job's patches as drift from Git (since Git has `REPLACE_ME` values) and revert them back to `REPLACE_ME`, breaking the automation.

**How it works**: ArgoCD ignores the helm parameters field when comparing desired state (Git) vs actual state (cluster), allowing the Job's patches to persist.

## Deployment

### One Command Deployment

```bash
oc apply -f anythingllm-generic/gitops/anythingllm-bootstrap.yaml
```

That's it! Everything else happens automatically:
1. Wave 0: Cluster discovery runs
2. Wave 1: Parameter updater patches Applications
3. Wave 2: MachineSets sync and deploy

### Monitor Progress

```bash
# Watch all applications
oc get applications -n openshift-gitops -w

# Check parameter updater job
oc get job machineset-params-updater -n openshift-gitops
oc logs job/machineset-params-updater -n openshift-gitops

# Verify MachineSets are created
oc get machinesets -n openshift-machine-api

# Watch nodes come online
oc get nodes -w
```

## Troubleshooting

### Parameter Updater Job Failed

Check the job logs:
```bash
oc logs job/machineset-params-updater -n openshift-gitops
```

Common issues:
- **Timeout waiting for ConfigMap**: Cluster-discovery job may have failed
- **RBAC error**: Service account permissions issue (should not happen with provided manifests)

### Applications Still Show REPLACE_ME

If the Applications weren't updated:
```bash
# Check if job completed successfully
oc get job machineset-params-updater -n openshift-gitops

# View the Application
oc get application cpu-machineset-m6a-4xlarge -n openshift-gitops -o yaml

# Manually trigger the job to rerun
oc delete job machineset-params-updater -n openshift-gitops
# ArgoCD will recreate it automatically
```

### MachineSet Name Still Invalid

If the error persists after job completion:
1. Verify the Application was actually patched:
   ```bash
   oc get application cpu-machineset-m6a-4xlarge -n openshift-gitops -o yaml | grep -A 5 parameters
   ```
2. Force Application refresh:
   ```bash
   argocd app get cpu-machineset-m6a-4xlarge --refresh
   argocd app sync cpu-machineset-m6a-4xlarge
   ```

## Comparison with openshift-infra

The `openshift-infra` repository uses a deploy script that:
- Runs `argocd app set` to update parameters
- Requires `argocd` CLI installed locally
- Must be executed manually

This repository improves on that by:
- **No local tools required**: Everything runs in Kubernetes
- **Fully automated**: No manual script execution
- **GitOps native**: Uses Kubernetes Jobs and RBAC
- **Repeatable**: Can be redeployed without manual intervention

## Benefits

✅ **Zero Manual Intervention**: No scripts to run after applying bootstrap  
✅ **GitOps Native**: All operations happen through Kubernetes resources  
✅ **Self-Contained**: No external tools or CLI required  
✅ **Auditable**: All actions logged in Job pods  
✅ **Repeatable**: Can redeploy to new clusters without changes  
✅ **RBAC Compliant**: Minimal permissions granted to automation  

## Why This Approach?

**Q: Why not use ArgoCD plugins or variable substitution?**  
A: ArgoCD doesn't natively support reading ConfigMap values into Application parameters. Plugins require cluster-level ArgoCD configuration changes.

**Q: Why a Job instead of an operator?**  
A: A one-time Job is simpler and sufficient. Once parameters are set, they don't change.

**Q: Why patch Applications instead of using the argocd CLI?**  
A: Direct Kubernetes API calls are more reliable and don't require external tool installation or authentication.

**Q: Won't ArgoCD's self-heal revert the patched values back to REPLACE_ME?**  
A: No, because the bootstrap Application includes `ignoreDifferences` for the helm parameters. This tells ArgoCD to ignore those fields when checking for drift, allowing the Job's patches to persist.

**Q: What if I want to change parameters later?**  
A: Edit the Application directly or update the cluster-info ConfigMap and rerun the updater job.

## RBAC Permissions

The updater job uses minimal permissions:

**Namespace-scoped (openshift-gitops)**:
- `applications.argoproj.io`: get, list, patch, update

**Cluster-scoped**:
- `configmaps` (specific name: cluster-info): get

No cluster-admin or elevated permissions required.
