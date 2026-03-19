#!/bin/bash
set -e

# MachineSet Deployment Script for AnythingLLM Demo
# This script deploys CPU and/or GPU machinesets via ArgoCD with proper Helm parameter configuration
#
# For detailed documentation, see: ../README.md
# Quick usage:
#   ./deploy-machinesets.sh                       # Deploy all machinesets
#   ./deploy-machinesets.sh --cpu-only            # Deploy only CPU
#   ./deploy-machinesets.sh --gpu-only            # Deploy only GPU
#   ./deploy-machinesets.sh --gpu-type g6e.12xlarge  # Deploy 4x L40S node
#   ./deploy-machinesets.sh --list                # List available GPU types
#   ./deploy-machinesets.sh --help                # Show full help

# Parse command line arguments
DEPLOY_CPU=true
DEPLOY_GPU=true
GPU_TYPES=()

print_usage() {
  echo "Usage: $0 [OPTIONS]"
  echo ""
  echo "Options:"
  echo "  --cpu-only          Deploy only CPU machineset"
  echo "  --gpu-only          Deploy only GPU machinesets"
  echo "  --gpu-type TYPE     Deploy specific GPU type (g6e.2xlarge, g6e.12xlarge, or g6.2xlarge)"
  echo "                      Can be specified multiple times"
  echo "  --list              List available GPU types with specs and exit"
  echo "  --help              Show this help message"
  echo ""
  echo "Environment Variables:"
  echo "  CLUSTER_NAME        Override cluster name (auto-detected)"
  echo "  REGION              Override AWS region (auto-detected)"
  echo "  AVAILABILITY_ZONE   Override availability zone (auto-detected)"
  echo "  INFRA_ID            Override infrastructure ID (auto-detected)"
  echo "  AMI_ID              Override AMI ID (auto-detected)"
  echo "  REPLICA_COUNT       Number of replicas (default: 1)"
  echo ""
  echo "Examples:"
  echo "  $0                              # Deploy all machinesets (CPU + default GPU types)"
  echo "  $0 --cpu-only                   # Deploy only CPU"
  echo "  $0 --gpu-type g6e.2xlarge       # Deploy only g6e.2xlarge GPU"
  echo "  $0 --gpu-type g6e.12xlarge      # Deploy g6e.12xlarge GPU (4x L40S, 1 replica by default)"
  echo "  $0 --gpu-type g6.2xlarge        # Deploy only g6 GPU (0 replicas, for FLUX.2 add-on)"
  echo "  REPLICA_COUNT=2 $0              # Deploy with 2 replicas each"
  echo "  $0 --list                       # Show available GPU types"
}

print_gpu_list() {
  echo "Available GPU MachineSet Types"
  echo "=============================="
  echo ""
  echo "DEFAULT (deployed by ./deploy-machinesets.sh with no flags):"
  echo ""
  echo "  g6e.2xlarge    1x NVIDIA L40S  48GB VRAM   8 vCPU   64GB RAM   ~\$2.24/hr"
  echo "                 → Primary LLM node (qwen3-vl-8b)"
  echo ""
  echo "  g6.2xlarge     1x NVIDIA L4    24GB VRAM   8 vCPU   32GB RAM   ~\$1.10/hr"
  echo "                 → Deployed at 0 replicas; scale up for FLUX.2 add-on"
  echo ""
  echo "AVAILABLE (deploy with --gpu-type <type>):"
  echo ""
  echo "  g6e.12xlarge   4x NVIDIA L40S  192GB VRAM  48 vCPU  384GB RAM  ~\$10.49/hr"
  echo "                 → Multi-GPU node for large model sharding / tensor-parallel inference"
  echo ""
  echo "  g6.2xlarge     (see above)"
  echo "  g6e.2xlarge    (see above)"
  echo ""
  echo "CPU:"
  echo ""
  echo "  m6a.4xlarge    No GPU          —           16 vCPU  64GB RAM   ~\$0.69/hr"
  echo "                 → RHOAI platform pods"
  echo ""
}

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --cpu-only)
      DEPLOY_GPU=false
      shift
      ;;
    --gpu-only)
      DEPLOY_CPU=false
      shift
      ;;
    --gpu-type)
      GPU_TYPES+=("$2")
      shift 2
      ;;
    --list)
      print_gpu_list
      exit 0
      ;;
    --help)
      print_usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      print_usage
      exit 1
      ;;
  esac
done

# If GPU types specified, use those; otherwise deploy default GPU types only (g6e.12xlarge is optional)
if [ ${#GPU_TYPES[@]} -eq 0 ]; then
  GPU_TYPES=("g6e.2xlarge" "g6.2xlarge")
fi

# If --gpu-only with specific types, only deploy those
if [ "$DEPLOY_GPU" = true ] && [ "$DEPLOY_CPU" = false ]; then
  : # GPU_TYPES already set
elif [ "$DEPLOY_CPU" = true ] && [ "$DEPLOY_GPU" = false ]; then
  GPU_TYPES=()
fi

REPLICA_COUNT=${REPLICA_COUNT:-1}

echo "=========================================="
echo "AnythingLLM Demo - MachineSet Deployment"
echo "=========================================="
echo "Deploy CPU: $DEPLOY_CPU"
echo "Deploy GPU: $DEPLOY_GPU"
if [ "$DEPLOY_GPU" = true ]; then
  echo "GPU Types: ${GPU_TYPES[*]}"
fi
echo "Replicas: $REPLICA_COUNT"
echo ""

# Step 1: Get cluster information
echo "Step 1: Gathering cluster information..."
CLUSTER_NAME=${CLUSTER_NAME:-$(oc get infrastructure cluster -o jsonpath='{.status.infrastructureName}')}
REGION=${REGION:-$(oc get infrastructure cluster -o jsonpath='{.status.platformStatus.aws.region}')}

# Try to get availability zone from worker machines first, fallback to master machines
if [ -z "$AVAILABILITY_ZONE" ]; then
  AVAILABILITY_ZONE=$(oc get machines -n openshift-machine-api -l machine.openshift.io/cluster-api-machine-role=worker -o jsonpath='{.items[0].spec.providerSpec.value.placement.availabilityZone}' 2>/dev/null || true)
  if [ -z "$AVAILABILITY_ZONE" ]; then
    echo "  No worker machines found, using master node configuration..."
    AVAILABILITY_ZONE=$(oc get machines -n openshift-machine-api -l machine.openshift.io/cluster-api-machine-role=master -o jsonpath='{.items[0].spec.providerSpec.value.placement.availabilityZone}')
  fi
fi

INFRA_ID=${INFRA_ID:-$(oc get infrastructure cluster -o jsonpath='{.status.infrastructureName}')}

# Try to get AMI from existing machinesets, fallback to machines
if [ -z "$AMI_ID" ]; then
  AMI_ID=$(oc get machineset -n openshift-machine-api -o json 2>/dev/null | jq -r '.items[] | select(.metadata.name | contains("gpu") | not) | .spec.template.spec.providerSpec.value.ami.id' | head -1 || true)
  if [ -z "$AMI_ID" ]; then
    echo "  No machinesets found, using machine AMI configuration..."
    AMI_ID=$(oc get machines -n openshift-machine-api -o jsonpath='{.items[0].spec.providerSpec.value.ami.id}')
  fi
fi

echo "  Cluster Name: $CLUSTER_NAME"
echo "  Region: $REGION"
echo "  Availability Zone: $AVAILABILITY_ZONE"
echo "  Infrastructure ID: $INFRA_ID"
echo "  AMI ID: $AMI_ID"
echo ""

# Validate cluster info
if [ -z "$CLUSTER_NAME" ] || [ -z "$REGION" ] || [ -z "$AVAILABILITY_ZONE" ] || [ -z "$AMI_ID" ]; then
  echo "Error: Failed to retrieve cluster information. Is this an OpenShift cluster on AWS?"
  exit 1
fi

# Step 2: Login to ArgoCD
echo "Step 2: Logging in to ArgoCD..."
ARGOCD_PASSWORD=$(oc get secret/openshift-gitops-cluster -n openshift-gitops -o jsonpath='{.data.admin\.password}' | base64 -d)
ARGOCD_SERVER=$(oc get route openshift-gitops-server -n openshift-gitops -o jsonpath='{.spec.host}')

if [ -z "$ARGOCD_SERVER" ]; then
  echo "Error: OpenShift GitOps not found. Please install OpenShift GitOps first."
  exit 1
fi

argocd login $ARGOCD_SERVER --username admin --password $ARGOCD_PASSWORD --insecure --skip-test-tls > /dev/null 2>&1
echo "  Logged in to ArgoCD at $ARGOCD_SERVER"
echo ""

# Function to deploy a machineset
# Args: APP_NAME GITOPS_FILE INSTANCE_TYPE MACHINE_NAME_SUFFIX [REPLICA_OVERRIDE]
# REPLICA_OVERRIDE: if set, uses this value instead of $REPLICA_COUNT
deploy_machineset() {
  local APP_NAME=$1
  local GITOPS_FILE=$2
  local INSTANCE_TYPE=$3
  local MACHINE_NAME_SUFFIX=$4
  local EFFECTIVE_REPLICAS=${5:-$REPLICA_COUNT}

  echo "----------------------------------------"
  echo "Deploying: $APP_NAME"
  echo "Instance Type: $INSTANCE_TYPE"
  echo "Replicas: $EFFECTIVE_REPLICAS"
  echo "----------------------------------------"
  
  # Step 3: Create the ArgoCD Application
  echo "  Creating ArgoCD Application..."
  if oc get application $APP_NAME -n openshift-gitops > /dev/null 2>&1; then
    echo "    Application '$APP_NAME' already exists. Updating..."
  else
    oc apply -f "$GITOPS_FILE"
    echo "    Created application '$APP_NAME'"
  fi
  
  # Step 4: Set Helm parameters
  echo "  Setting Helm parameters..."
  argocd app set $APP_NAME \
    -p clusterName="$CLUSTER_NAME" \
    -p region="$REGION" \
    -p availabilityZone="$AVAILABILITY_ZONE" \
    -p infraID="$INFRA_ID" \
    -p amiId="$AMI_ID" \
    -p replicas="$EFFECTIVE_REPLICAS" > /dev/null 2>&1
  
  if [ -n "$MACHINE_NAME_SUFFIX" ]; then
    argocd app set $APP_NAME -p machineNameSuffix="$MACHINE_NAME_SUFFIX" > /dev/null 2>&1
  fi
  
  if [ -n "$INSTANCE_TYPE" ]; then
    argocd app set $APP_NAME -p instanceType="$INSTANCE_TYPE" > /dev/null 2>&1
  fi
  
  echo "    Parameters configured"
  
  # Step 5: Enable auto-sync and sync
  echo "  Syncing application..."
  argocd app set $APP_NAME --sync-policy automated --auto-prune --self-heal > /dev/null 2>&1
  argocd app sync $APP_NAME > /dev/null 2>&1
  echo "    Application synced"
  echo ""
}

# Get the repository root (assumes script is in anythingllm-generic/scripts/)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$( cd "$SCRIPT_DIR/../.." && pwd )"

# Deploy CPU machineset
if [ "$DEPLOY_CPU" = true ]; then
  deploy_machineset \
    "cpu-machineset-m6a-4xlarge" \
    "$REPO_ROOT/anythingllm-generic/gitops/app-of-apps/applications/infrastructure/cpu-machineset-m6a-4xlarge.yaml" \
    "m6a.4xlarge" \
    ""
fi

# Deploy GPU machinesets
if [ "$DEPLOY_GPU" = true ]; then
  for GPU_TYPE in "${GPU_TYPES[@]}"; do
    case "$GPU_TYPE" in
      "g6e.2xlarge")
        deploy_machineset \
          "gpu-machineset-g6e-2xlarge" \
          "$REPO_ROOT/anythingllm-generic/gitops/app-of-apps/applications/infrastructure/gpu-machineset-g6e-2xlarge.yaml" \
          "g6e.2xlarge" \
          "g6e"
        ;;
      "g6e.12xlarge")
        # Uses REPLICA_COUNT (default 1) when explicitly requested via --gpu-type; use REPLICA_COUNT=0 to register at 0 replicas
        deploy_machineset \
          "gpu-machineset-g6e-12xlarge" \
          "$REPO_ROOT/anythingllm-generic/gitops/optional/gpu-machineset-g6e-12xlarge.yaml" \
          "g6e.12xlarge" \
          "g6e-12xl"
        ;;
      "g6.2xlarge")
        # Deployed at 0 replicas by default; scale up manually when using the FLUX.2 optional add-on
        deploy_machineset \
          "gpu-machineset-g6-2xlarge" \
          "$REPO_ROOT/anythingllm-generic/gitops/app-of-apps/applications/infrastructure/gpu-machineset-g6-2xlarge.yaml" \
          "g6.2xlarge" \
          "g6" \
          "0"
        ;;
      *)
        echo "Warning: Unsupported GPU type '$GPU_TYPE'. Skipping."
        echo "  Run '$0 --list' to see available GPU types."
        ;;
    esac
  done
fi

echo "=========================================="
echo "Deployment initiated successfully!"
echo "=========================================="
echo ""
echo "Monitor progress with:"
echo "  oc get machineset -n openshift-machine-api -w"
echo "  oc get machine -n openshift-machine-api"
echo ""
if [ "$DEPLOY_GPU" = true ]; then
  echo "Wait for GPU nodes (5-10 minutes):"
  echo "  oc wait --for=condition=Ready nodes -l nvidia.com/gpu.present=true --timeout=600s"
  echo ""
  echo "Verify GPU nodes:"
  echo "  oc get nodes -l nvidia.com/gpu.present=true"
  echo ""
fi
echo "View ArgoCD Applications:"
echo "  oc get applications -n openshift-gitops -l app.kubernetes.io/component=infrastructure"
echo ""
echo "ArgoCD UI:"
echo "  https://$ARGOCD_SERVER"
echo ""
