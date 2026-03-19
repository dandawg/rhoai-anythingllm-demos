# AnythingLLM Complete Deployment

GitOps deployment of AnythingLLM with RHOAI model serving on OpenShift.

## What This Deploys

- GPU-enabled OpenShift infrastructure (deployed by default):
  - **g6e.2xlarge** GPU node (1x NVIDIA L40S, 48GB VRAM, ~$2.24/hr) — for qwen3-vl-8b LLM and FLUX.2-klein-9B (optional)
  - **g6.2xlarge** GPU node (1x NVIDIA L4, 24GB VRAM, ~$1.10/hr) — spare capacity (MachineSet deployed at scale 0; scale up for FLUX.2 add-on)
  - **m6a.4xlarge** CPU node (16 vCPU, 64GB RAM, ~$0.69/hr) — for RHOAI pod support
- RHOAI platform with dependencies (NFD, NVIDIA GPU Operator, LeaderWorkerSet operator, llm-d inference Gateway)
- Hardware profiles: g6e.2xlarge, g6.2xlarge, and **g6e.12xlarge** (pre-installed via GitOps for llm-d demos)
- vLLM-Omni serving runtime (general-purpose; supports LLMs and diffusion image generation models)
- Model serving: qwen3-vl-8b (LLM) + qwen3-vl-embedding-2b (embeddings)
- External Secrets Operator for automatic token discovery
- AnythingLLM application pre-configured with model endpoints

**Optional (not deployed by default):**
- **g6e.12xlarge** GPU node (4x NVIDIA L40S, 192GB total VRAM, 48 vCPU, 384 GiB RAM, ~$10.49/hr) — deploy when demoing Nemotron / llm-d distributed inference

**Optional add-on:** FLUX.2-klein-9B image generation model (requires HuggingFace token — see [Optional Add-ons](#optional-add-ons))

**Total deployment time: ~25-30 minutes**

## Prerequisites

✅ OpenShift 4.19+ cluster on AWS  
✅ `oc` and `argocd` CLI tools installed  
✅ OpenShift GitOps (ArgoCD) installed - Run `../bootstrap.sh` if not installed  
✅ Cluster admin access  
✅ Available AWS capacity for g6e.2xlarge (GPU) and m6a.4xlarge (CPU) instances  
✅ For llm-d / Nemotron demo: available AWS capacity for g6e.12xlarge (4x L40S, 192GB VRAM, 384 GiB RAM) — optional, deploy only when demoing

### Install OpenShift GitOps (if needed)

```bash
# From repository root
cd ..
./bootstrap.sh
cd anythingllm-generic
```


## Installation

### Step 1: Deploy MachineSets

**Important**: MachineSets must be deployed first using the deployment script:

```bash
# Deploy all machinesets (CPU + default GPU types: g6e.2xlarge + g6.2xlarge)
./scripts/deploy-machinesets.sh

# List available GPU types with specs
./scripts/deploy-machinesets.sh --list

# Deploy selectively
./scripts/deploy-machinesets.sh --cpu-only
./scripts/deploy-machinesets.sh --gpu-type g6e.2xlarge
./scripts/deploy-machinesets.sh --gpu-type g6e.12xlarge   # 4x L40S, ~$10.49/hr

# Override specific values if needed
AVAILABILITY_ZONE=us-east-1b ./scripts/deploy-machinesets.sh
REPLICA_COUNT=2 ./scripts/deploy-machinesets.sh
```

The script will:
1. Auto-discover cluster information (name, region, AZ, AMI ID)
2. Login to ArgoCD
3. Create ArgoCD Applications for MachineSets
4. Set Helm parameters with cluster-specific values
5. Sync applications to deploy MachineSets

**Monitor MachineSet deployment:**

```bash
# Watch MachineSets
oc get machineset -n openshift-machine-api -w

# Wait for GPU nodes (5-10 minutes)
oc wait --for=condition=Ready nodes -l nvidia.com/gpu.present=true --timeout=600s

# Verify nodes are ready
oc get nodes -l nvidia.com/gpu.present=true
```

### Step 2: Deploy Application Stack

Once MachineSets are deploying, apply the bootstrap application:

```bash
oc apply -f gitops/anythingllm-bootstrap.yaml
```

**Benefits:**
- Applications grouped by ArgoCD Projects (infrastructure, platform, models, applications)
- Better UI organization in ArgoCD
- Delete resources by logical groups
- Granular control over components

See [App of Apps README](gitops/app-of-apps/README.md) for detailed documentation.

## Monitoring Deployment

Watch ArgoCD Applications:
```bash
oc get applications -n openshift-gitops -w
```

Access ArgoCD UI:
```bash
# Get ArgoCD web URL
echo "https://$(oc get route openshift-gitops-server -n openshift-gitops -o jsonpath='{.spec.host}')"

# Get ArgoCD admin password
oc get secret -n openshift-gitops openshift-gitops-cluster -o jsonpath='{.data.admin\.password}' | base64 -d

# ArgoCD via CLI (depends on argocd cli)
argocd login $(oc get routes -n openshift-gitops openshift-gitops-server -o jsonpath='{.spec.host}') --username admin --password $(oc get secret -n openshift-gitops openshift-gitops-cluster -o jsonpath='{.data.admin\.password}' | base64 -d) --insecure  --skip-test-tls

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

## Optional Add-ons

### Nemotron-3-Nano-30B-A3B-FP8 with llm-d (Distributed Inference Demo)

Demonstrates [llm-d](https://github.com/llm-d/llm-d) distributed inference on RHOAI using the `g6e.12xlarge` node (4x NVIDIA L40S). The model runs as 2 replicas with tensor parallelism across 2 GPUs each — filling all 4 GPUs and showing llm-d's KV-cache-aware routing between replicas.

**What the standard bootstrap already provides for this demo:**
- `g6e-12xlarge` HardwareProfile (deployed via GitOps in the models layer)
- LeaderWorkerSet (LWS) operator (deployed as part of `rhoai-dependencies`)
- `openshift-ai-inference` Gateway for llm-d inference routing (deployed as part of `rhoai-dependencies`)

The only manual steps before demoing are deploying the optional MachineSet and launching the model from the catalog.

#### Step 1: Deploy the g6e.12xlarge MachineSet

```bash
# Register the MachineSet at 0 replicas (no cost yet)
REPLICA_COUNT=0 ./scripts/deploy-machinesets.sh --gpu-type g6e.12xlarge

# Immediately before the demo, scale up the node (5-10 minutes to provision)
oc get machineset -n openshift-machine-api | grep g6e-12xl
oc scale machineset <machineset-name> -n openshift-machine-api --replicas=1
oc wait --for=condition=Ready nodes -l node.kubernetes.io/instance-type=g6e.12xlarge --timeout=600s
```

> If you want the node live from the start of the demo, skip `REPLICA_COUNT=0` and just run `./scripts/deploy-machinesets.sh --gpu-type g6e.12xlarge` (deploys with 1 replica).

#### Step 2: Deploy Nemotron from the RHOAI Model Catalog

In the RHOAI dashboard, navigate to **Models → Model catalog** and select **NVIDIA-Nemotron-3-Nano-30B-A3B-FP8**. Use these values:

| Field | Value |
|-------|-------|
| Deployment type | Distributed inference with llm-d |
| Hardware Profile | `AWS g6e.12xlarge (4x NVIDIA L40S)` |
| Replicas | `2` |
| GPUs per replica | `2` |
| Tensor parallelism | `2` |

**vLLM arguments** (enter in the "Additional arguments" field, one per line):

```
--trust-remote-code
--kv-cache-dtype=fp8
--async-scheduling
--gpu_memory_utilization=0.95
--max-model-len=262144
--max-num-seqs=8
--tensor-parallel-size=2
```

**Environment variables:**

| Name | Value |
|------|-------|
| `VLLM_USE_FLASHINFER_MOE_FP8` | `1` |
| `VLLM_FLASHINFER_MOE_BACKEND` | `throughput` |
| `VLLM_ALLOW_LONG_MAX_MODEL_LEN` | `1` |

**Resource limits per replica pod:** 8 CPU / 64Gi memory / 2 GPUs (requests); 16 CPU / 128Gi / 2 GPUs (limits).

> For full deployment details and troubleshooting, see the [rhoai-model-serving README](https://github.com/dandawg/rhoai-model-serving/blob/main/README.md#deploying-nemotron-3-nano-30b-a3b-fp8-with-llm-d).

#### After the Demo: Scale Down

```bash
oc scale machineset <machineset-name> -n openshift-machine-api --replicas=0
```

The MachineSet remains in ArgoCD (replica drift is ignored by `ignoreDifferences`) so the next demo only needs `oc scale ... --replicas=1`.

---

### FLUX.2-klein-9B Image Generation Model

Adds the `black-forest-labs/FLUX.2-klein-9B` image generation model (~53 GB, BF16 Diffusers pipeline) served on a g6e.2xlarge node (NVIDIA L40S, 48 GB). Served by the vLLM-Omni runtime (already deployed as part of the main bootstrap). This model is gated on HuggingFace and requires a token to download.

> **Note on AnythingLLM integration:** AnythingLLM's OpenAI-compatible LLM slot is already used by qwen3-vl-8b, so this model cannot be auto-configured via environment variables. After deployment you will need to set up the FLUX.2 connection manually inside AnythingLLM.

#### Prerequisites

You need a [HuggingFace account](https://huggingface.co) with access to the `black-forest-labs/FLUX.2-klein-9b-fp8` model repository and a read token.

1. **Request access** to the model on HuggingFace (if you haven't already):  
   <https://huggingface.co/black-forest-labs/FLUX.2-klein-9b-fp8>

2. **Create a HuggingFace read token** at <https://huggingface.co/settings/tokens>.

#### Step 1: Ensure a g6e.2xlarge Node is Available

FLUX.2-klein-9B requires ~29 GB VRAM and runs on the g6e.2xlarge (NVIDIA L40S, 48 GB) — the same node type used by qwen3-vl-8b. If qwen3-vl-8b is already running on that node, you may need a second g6e.2xlarge node:

```bash
# Check if a g6e.2xlarge node is free / available
oc get nodes -l node.kubernetes.io/instance-type=g6e.2xlarge

# If needed, scale the MachineSet to 2 replicas
oc get machineset -n openshift-machine-api | grep g6e
oc scale machineset <machineset-name> -n openshift-machine-api --replicas=2
oc wait --for=condition=Ready nodes -l node.kubernetes.io/instance-type=g6e.2xlarge --timeout=600s
```

#### Step 2: Create the HuggingFace Token Secret

The `demo` namespace is created during the main bootstrap (wave 8). Create the secret before or immediately after that wave completes — it must exist when the download job runs.

```bash
oc create secret generic huggingface-token \
  --from-literal=token=hf_YOUR_TOKEN_HERE \
  -n demo
```

Verify:

```bash
oc get secret huggingface-token -n demo
```

#### Step 3: Apply the Optional GitOps Applications

```bash
oc apply -f gitops/optional/model-download-flux2-klein-9b.yaml
oc apply -f gitops/optional/model-serving-flux2-klein-9b.yaml
```

ArgoCD will then:

1. Create a 60 Gi PVC and run a download job to pull the model from HuggingFace (~53 GB — expect 20–60 minutes)
2. Deploy the InferenceService once the download completes (uses the `vllm-omni-runtime` already running in the namespace)

#### Step 4: Monitor the Deployment

```bash
# Watch the download job
oc get job download-flux2-klein-9b -n demo -w
oc logs -n demo -l app.kubernetes.io/name=flux2-klein-9b-downloader --follow

# Watch the InferenceService come ready (after download completes)
oc get inferenceservice flux2-klein-9b -n demo -w
```

The download takes 20–60 minutes depending on network speed (~53 GB).

#### Step 5: Connect FLUX.2 in AnythingLLM (Manual)

Once the InferenceService is ready, note the internal service URL:

```
http://flux2-klein-9b-predictor.demo.svc.cluster.local:8080/v1
```

Retrieve the bearer token for the model's service account:

```bash
oc get secret default-name-flux2-klein-9b-sa -n demo \
  -o jsonpath='{.data.token}' | base64 -d
```

Then in AnythingLLM, manually configure a second LLM or agent connection using the endpoint and token above.

#### Removing the FLUX.2 Add-on

```bash
oc delete application model-download-flux2-klein-9b -n openshift-gitops
oc delete application model-serving-flux2-klein-9b -n openshift-gitops
```

---

## Architecture

The deployment uses ArgoCD sync waves to orchestrate installation:

**Prerequisites (run script first):**
- MachineSets (deployed via `./scripts/deploy-machinesets.sh`)
  - **Default:**
    - g6e.2xlarge (1 replica) — qwen3-vl-8b LLM (1x L40S, 48GB, ~$2.24/hr)
    - g6.2xlarge (0 replicas) — spare L4 capacity for FLUX.2 add-on (~$1.10/hr)
    - m6a.4xlarge (1 replica) — RHOAI platform pods (~$0.69/hr)
  - **Available (use `--gpu-type`):**
    - g6e.12xlarge (0 replicas) — large multi-GPU inference (4x L40S, 192GB VRAM, 384 GiB RAM, ~$10.49/hr)

**GitOps Deployment (after MachineSets):**
- **Wave -1**: Cleanup hooks (PreDelete)
- **Wave 0**: Infrastructure operators (NFD, NVIDIA GPU Operator, RHOAI dependencies)
- **Wave 1**: RHOAI operator
- **Wave 2**: RHOAI instance (DataScienceCluster)
- **Wave 8-15**: Model serving (downloads, runtimes, inference services)
- **Wave 30-31**: Token discovery (External Secrets Operator)
- **Wave 40**: AnythingLLM application

### Repository Dependencies

This deployment references the [openshift-infra](https://github.com/dandawg/openshift-infra) repository for:
- GPU machineset Helm charts (g6e.2xlarge for LLM)
- CPU machineset Helm charts (m6a.4xlarge for RHOAI platform pods)

The openshift-infra repo can also be used standalone for infrastructure provisioning.

## Troubleshooting

### MachineSet Deployment Issues

**MachineSets showing `OutOfSync` in ArgoCD after applying the bootstrap**

The machineset Applications require cluster-specific Helm parameters (`infraID`, `clusterName`, `availabilityZone`, `amiId`) that can only be discovered at runtime. These Applications do not auto-sync — they wait for the parameters to be injected by the deployment script.

If you applied the bootstrap before running the machinesets script, simply run the script now:

```bash
./scripts/deploy-machinesets.sh
```

The script will configure the parameters and trigger a sync. The bootstrap app-of-apps manages these Application objects, so you must use the script (not manual ArgoCD syncs) to ensure the parameters are set correctly before syncing.

**Script fails: "Failed to retrieve cluster information"**

Not logged into OpenShift or not running on AWS:

```bash
# Login first
oc login https://api.your-cluster.com:6443

# Verify you're on AWS
oc get infrastructure cluster -o jsonpath='{.status.platform}'
# Should return "AWS"
```

**Script fails: "OpenShift GitOps not found"**

OpenShift GitOps operator not installed:

```bash
# Install from repository root
cd ..
./bootstrap.sh
cd anythingllm-generic
```

**Script fails: "argocd: command not found"**

Install ArgoCD CLI:
- **macOS**: `brew install argocd`
- **Linux**: Download from [ArgoCD releases](https://github.com/argoproj/argo-cd/releases)

**MachineSets created but machines not starting**

Check Machine status for AWS issues:

```bash
oc describe machine <machine-name> -n openshift-machine-api

# Common issues:
# - AWS quota limits: Request increase in AWS console
# - Instance unavailable in AZ: Try different instance type or AZ
# - IAM permissions: Verify cluster IAM roles have EC2 permissions
```

**Wrong AMI ID detected**

Manually specify correct AMI:

```bash
AMI_ID=ami-0abc123def456 ./scripts/deploy-machinesets.sh

# Find correct AMI from existing worker nodes
oc get machines -n openshift-machine-api -o json | \
  jq -r '.items[] | select(.metadata.labels["machine.openshift.io/cluster-api-machine-role"]=="worker") | .spec.providerSpec.value.ami.id' | \
  head -1
```

### Platform and Application Issues

**Nodes not ready?**
```bash
# Check GPU nodes
oc get machines -n openshift-machine-api -l gpu-instance-type=g6e.2xlarge
oc describe machine -n openshift-machine-api | grep -A5 gpu

# Check CPU worker
oc get machines -n openshift-machine-api -l cpu-instance-type=m6a.4xlarge

# Check events
oc get events -n openshift-machine-api --sort-by='.lastTimestamp'
```

**Model not loading?**
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

```bash
oc delete application anythingllm-bootstrap -n openshift-gitops
```

This will cascade delete all child applications and their resources. A PreDelete hook automatically cleans up orphaned API services to prevent hanging deletions.

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
oc patch application anythingllm-bootstrap -n openshift-gitops \
  -p '{"metadata":{"finalizers":null}}' --type=merge
```

**Namespace stuck in Terminating?**
```bash
# Check what's blocking it
oc get namespace <namespace> -o json | jq '.status.conditions'

# Force cleanup if needed
oc patch namespace <namespace> -p '{"metadata":{"finalizers":[]}}' --type=merge
```
