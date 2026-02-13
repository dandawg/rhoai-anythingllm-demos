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
- **`oc` CLI** installed and configured
- **OpenShift GitOps** (ArgoCD) - See installation below
- **AWS quota** for GPU instances (g4dn, g6, g6e) and CPU instances (m6a)

### Install OpenShift GitOps (if needed)

```bash
./bootstrap.sh
```

**Note:** If GitOps is already installed (e.g., from deploying another repository), the bootstrap script will detect it and skip installation.

## Available Demos

### AnythingLLM Generic Demo

Complete deployment with:
- GPU nodes (g6e.2xlarge + g4dn.xlarge)
- CPU nodes (m6a.4xlarge)
- RHOAI platform
- Model serving (Qwen3-VL-8B + embeddings)
- AnythingLLM application

See [anythingllm-generic/README.md](anythingllm-generic/README.md) for details.

## Repository Structure

```
rhoai-anythingllm-demos/
├── README.md              # This file
├── bootstrap.sh           # GitOps installer script
├── bootstrap/             # GitOps operator manifests
│   └── gitops-operator/
└── anythingllm-generic/   # Complete demo deployment
    ├── README.md
    └── gitops/
        └── anythingllm-complete.yaml
```

## Related Repositories

This repository builds on:
- [rhoai-deploy](https://github.com/redhat-ai-americas/rhoai-deploy) - RHOAI platform deployment
- [openshift-infra](https://github.com/redhat-ai-americas/openshift-infra) - GPU infrastructure
- [rhoai-model-serving](https://github.com/redhat-ai-americas/rhoai-model-serving) - Model serving configs
- [anythingllm-on-ocp](https://github.com/redhat-ai-americas/anythingllm-on-ocp) - AnythingLLM deployment

## License

Apache License 2.0
