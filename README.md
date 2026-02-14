# RHOAI AnythingLLM Demos

Complete demonstration deployments combining RHOAI, model serving, and AnythingLLM on OpenShift.

## Overview

This repository provides end-to-end demo deployments that showcase:
- GPU infrastructure provisioning
- RHOAI platform deployment
- Model serving with KServe/vLLM
- AnythingLLM application with RAG capabilities

## Prerequisites

- **OpenShift 4.19+** on AWS with cluster-admin access
- **`oc` and `argocd` CLI** installed and configured
- **OpenShift GitOps** (ArgoCD) - See installation below
- **AWS quota** for GPU instances (g4dn, g6e) and CPU instances (m6a)

### Install OpenShift GitOps (if needed)

```bash
# Install OpenShift GitOps operator
./bootstrap.sh
```

## Quick Start

### 1. Deploy MachineSets

First, deploy the required GPU and CPU MachineSets using the deployment script:

```bash
cd anythingllm-generic

# Deploy all machinesets (1 CPU + 2 GPU types)
./scripts/deploy-machinesets.sh

# Or deploy selectively
# ./scripts/deploy-machinesets.sh --cpu-only
# ./scripts/deploy-machinesets.sh --gpu-type g4dn.xlarge
```

The script automatically:
- Discovers your cluster information (name, region, availability zone, AMI ID)
- Creates ArgoCD Applications for MachineSets
- Sets Helm parameters with cluster-specific values
- Syncs applications to deploy MachineSets

### 2. Deploy Application Stack

Once MachineSets are deploying, apply the bootstrap application:

```bash
oc apply -f gitops/anythingllm-bootstrap.yaml
```

**Total deployment time: ~25-30 minutes**

See [anythingllm-generic/README.md](anythingllm-generic/README.md) for detailed documentation.

## Available Demos

### AnythingLLM Generic Demo

Complete deployment with:
- GPU nodes (g6e.2xlarge + g4dn.xlarge)
- CPU nodes (m6a.4xlarge)
- RHOAI platform
- Model serving (Qwen3-VL-8B + embeddings)
- AnythingLLM application

Features:
- Script-based MachineSet deployment
- GitOps-driven platform and application deployment
- App-of-Apps pattern for organized resource management

## Repository Structure

```
rhoai-anythingllm-demos/
├── README.md              # This file
├── bootstrap.sh           # GitOps installer script
├── bootstrap/             # GitOps operator manifests
│   └── gitops-operator/
└── anythingllm-generic/   # Complete demo deployment
    ├── README.md          # Detailed deployment guide
    ├── scripts/
    │   └── deploy-machinesets.sh  # MachineSet deployment script
    └── gitops/
        ├── anythingllm-bootstrap.yaml  # App-of-Apps deployment
        ├── anythingllm-complete.yaml   # Monolithic deployment
        └── app-of-apps/                # ArgoCD Application definitions
```

## Related Repositories

This repository builds on:
- [rhoai-deploy](https://github.com/redhat-ai-americas/rhoai-deploy) - RHOAI platform deployment
- [openshift-infra](https://github.com/redhat-ai-americas/openshift-infra) - GPU infrastructure
- [rhoai-model-serving](https://github.com/redhat-ai-americas/rhoai-model-serving) - Model serving configs
- [anythingllm-on-ocp](https://github.com/redhat-ai-americas/anythingllm-on-ocp) - AnythingLLM deployment

## License

Apache License 2.0
