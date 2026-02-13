# AnythingLLM Complete Deployment

One-click GitOps deployment of AnythingLLM with RHOAI model serving on OpenShift.

## What This Deploys

- GPU-enabled OpenShift infrastructure:
  - g6e.2xlarge GPU node (NVIDIA L4, 24GB) - for qwen3-vl-8b LLM
  - g4dn.xlarge GPU node (NVIDIA T4, 16GB) - for qwen3-vl-embedding-2b
  - m6a.4xlarge CPU node (16 vCPU, 64GB RAM) - for RHOAI pod support
- RHOAI platform with dependencies (NFD, NVIDIA GPU Operator)
- Model serving: qwen3-vl-8b (LLM) + qwen3-vl-embedding-2b (embeddings)
- External Secrets Operator for automatic token discovery (supports easy demo experience)
- AnythingLLM application pre-configured with model endpoints

**Total deployment time: ~20-30 minutes**

## Prerequisites

✅ OpenShift 4.19+ cluster on AWS  
✅ OpenShift GitOps (ArgoCD) installed - Run `../bootstrap.sh` if not installed  
✅ Cluster admin access  
✅ Available AWS capacity for g6e.2xlarge, g4dn.xlarge (GPU) and m6a.4xlarge (CPU) instances

### Install OpenShift GitOps (if needed)

```bash
cd ..
./bootstrap.sh
cd anythingllm-generic
```

**Note:** If GitOps is already installed (e.g., from deploying another repository), the bootstrap script will detect it and skip installation.

## Installation

### Option 1: App of Apps Pattern (Recommended)

Deploy using the App of Apps pattern for better organization and control:

```bash
oc apply -f gitops/anythingllm-bootstrap.yaml
```

**Benefits:**
- Applications grouped by ArgoCD Projects (infrastructure, platform, models, applications)
- Better UI organization in ArgoCD
- Delete resources by logical groups
- Same one-click deployment experience

See [App of Apps README](gitops/app-of-apps/README.md) for detailed documentation.

### Option 2: Monolithic Application

Deploy as a single monolithic application:

```bash
oc apply -f gitops/anythingllm-complete.yaml
```

This deploys everything in one ArgoCD Application (original approach).

## Monitoring Deployment

Watch ArgoCD Application:
```bash
oc get application anythingllm-complete -n openshift-gitops -w
```

Access ArgoCD UI:
```bash
# Get ArgoCD web URL
echo "https://$(oc get route openshift-gitops-server -n openshift-gitops -o jsonpath='{.spec.host}')"

# Get ArgoCD admin password
oc get secret -n openshift-gitops openshift-gitops-cluster -o jsonpath='{.data.admin\.password}' | base64 -d

# ArgoCD via CLI (depends on argocd cli)
argocd login $(oc get routes -n openshift-gitops openshift-gitops-server -o jsonpath='{.spec.host}') --username admin --password $(oc get secret -n openshift-gitops openshift-gitops-cluster -o jsonpath='{.data.admin\.password}' | base64 -d) --insecure

argocd app list
```

Monitor GPU node provisioning:
```bash
oc get machines -n openshift-machine-api -w
oc get nodes -l nvidia.com/gpu.present=true
```

Check model serving status:
```bash
oc get inferenceservice -n demo
oc get pods -n demo
```

Wait for AnythingLLM:
```bash
oc get pods -n demo-apps -w
```

## Accessing AnythingLLM

Get the route URL:
```bash
oc get route anythingllm -n demo-apps -o jsonpath='{.spec.host}'
```

Open the URL in your browser and start chatting with your locally-served models!

## Architecture

The deployment uses ArgoCD sync waves to orchestrate installation:
- **Wave 0**: Cluster discovery (from openshift-infra repo)
- **Wave 0-2**: Infrastructure operators (NFD, NVIDIA GPU Operator, RHOAI dependencies)
- **Wave 1**: Node provisioning (g6e.2xlarge + g4dn.xlarge GPU + m6a.4xlarge CPU workers)
- **Wave 8-15**: Model serving (downloads, runtimes, inference services)
- **Wave 30-31**: Token discovery (External Secrets Operator)
- **Wave 40**: AnythingLLM application

### Repository Dependencies

This deployment references the [openshift-infra](https://github.com/dandawg/openshift-infra) repository for:
- Cluster discovery job (automatically gathers AWS cluster information)
- GPU machineset deployment (g6e.2xlarge for LLM, g4dn.xlarge for embedding models)
- CPU machineset deployment (m6a.4xlarge for RHOAI platform pods)

The openshift-infra repo can also be used standalone for infrastructure provisioning.

## Troubleshooting

**Nodes not ready?**
```bash
# Check GPU nodes
oc get machines -n openshift-machine-api -l gpu-instance-type=g6e.2xlarge
oc get machines -n openshift-machine-api -l gpu-instance-type=g4dn.xlarge
oc describe machine -n openshift-machine-api | grep -A5 gpu

# Check CPU worker
oc get machines -n openshift-machine-api -l cpu-instance-type=m6a.4xlarge

# Check events
oc get events -n openshift-machine-api --sort-by='.lastTimestamp'
```

**Models not loading?**
```bash
oc logs -n demo -l app.kubernetes.io/name=qwen3-vl-8b --tail=100
```

**AnythingLLM can't connect?**
```bash
oc get secret model-api-tokens -n demo-apps
oc logs -n demo-apps -l app.kubernetes.io/name=anythingllm --tail=100
```

**Token discovery issues?**
```bash
oc get externalsecret -n demo-apps
oc describe externalsecret model-api-tokens -n demo-apps
```

## Notes

- External Secrets Operator is Technology Preview on OpenShift
- First model download takes 5-10 minutes depending on network speed
- GPU node provisioning typically takes 5-10 minutes
- Models use authentication via bearer tokens (auto-discovered)

## Cleanup

### If using App of Apps pattern:

```bash
oc delete application anythingllm-bootstrap -n openshift-gitops
```

This will cascade delete all child applications and their resources.

### If using monolithic application:

```bash
oc delete application anythingllm-complete -n openshift-gitops
```

Both approaches include a PreDelete hook that automatically cleans up orphaned API services to prevent hanging deletions.

### Troubleshooting Deletion Issues

**Application stuck deleting?**

Check for orphaned API services:
```bash
oc get apiservices | grep False
```

The most common culprit is `v1beta1.visibility.kueue.x-k8s.io` from the Kueue operator. If the PreDelete hook didn't run or failed:

```bash
# Manually delete the failed API service
oc delete apiservice v1beta1.visibility.kueue.x-k8s.io

# Remove ArgoCD finalizer if still stuck
oc patch application anythingllm-complete -n openshift-gitops \
  -p '{"metadata":{"finalizers":null}}' --type=merge
```

**Namespace stuck in Terminating?**
```bash
# Check what's blocking it
oc get namespace <namespace> -o json | jq '.status.conditions'

# Force cleanup if needed
oc patch namespace <namespace> -p '{"metadata":{"finalizers":[]}}' --type=merge
```
