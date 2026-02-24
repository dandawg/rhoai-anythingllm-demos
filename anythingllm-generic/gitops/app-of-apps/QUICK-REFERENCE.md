# Quick Reference Guide

## One-Command Deployment

```bash
oc apply -f anythingllm-generic/gitops/anythingllm-bootstrap.yaml
```

## View All Applications

```bash
# List all applications
oc get applications -n openshift-gitops

# View by project
oc get applications -n openshift-gitops -l app.kubernetes.io/part-of=rhoai-demos

# Watch deployment progress
watch -n 5 "oc get applications -n openshift-gitops | grep -E 'NAME|anythingllm|rhoai|model|eso'"
```

## Filter by ArgoCD Project

```bash
# Infrastructure layer
oc get applications -n openshift-gitops | grep -E "cleanup-hooks|cluster-discovery|machineset|gpu-operator|rhoai-dependencies"

# Platform layer  
oc get applications -n openshift-gitops | grep -E "rhoai-operator|rhoai-instance"

# Model serving
oc get applications -n openshift-gitops | grep -E "model-|hardware-profile"

# Applications
oc get applications -n openshift-gitops | grep -E "eso-|anythingllm"
```

## Manual Sync Operations

```bash
# Sync specific application
oc patch application <app-name> -n openshift-gitops \
  --type merge -p '{"operation":{"initiatedBy":{"username":"admin"},"sync":{"revision":"HEAD"}}}'

# Or via ArgoCD CLI
argocd app sync <app-name>

# Sync all in a layer (e.g., models)
for app in model-base-resources hardware-profile-g6e-2xlarge; do
  argocd app sync $app
done
```

## Delete Operations

### Delete Everything

```bash
oc delete application anythingllm-bootstrap -n openshift-gitops
```

### Delete Specific Layers

**Models only:**
```bash
oc delete applications -n openshift-gitops \
  model-base-resources \
  hardware-profile-g6e-2xlarge \
  model-download-qwen3-vl-8b \
  model-serving-qwen3-vl-8b
```

**Applications only:**
```bash
oc delete applications -n openshift-gitops \
  external-secrets-operator \
  eso-secrets \
  anythingllm
```

**Infrastructure only:**
```bash
oc delete applications -n openshift-gitops \
  cleanup-hooks \
  cluster-discovery \
  rhoai-dependencies \
  nvidia-gpu-operator \
  gpu-machineset-g6e-2xlarge \
  cpu-machineset-m6a-4xlarge
```

### Delete Specific Application

```bash
oc delete application <app-name> -n openshift-gitops
```

## Troubleshooting

### Check Application Status

```bash
# Get application details
oc describe application <app-name> -n openshift-gitops

# Check sync status
oc get application <app-name> -n openshift-gitops -o jsonpath='{.status.sync.status}'

# Check health status
oc get application <app-name> -n openshift-gitops -o jsonpath='{.status.health.status}'
```

### View Application Resources

```bash
# List all resources managed by an application
oc get application <app-name> -n openshift-gitops -o jsonpath='{.status.resources[*].kind}' | tr ' ' '\n' | sort -u

# Get specific resource type
oc get application <app-name> -n openshift-gitops -o json | jq '.status.resources[] | select(.kind=="Pod")'
```

### Refresh Application

```bash
# Refresh to detect changes without syncing
argocd app get <app-name> --refresh

# Hard refresh (bypass cache)
argocd app get <app-name> --hard-refresh
```

### Check Sync Waves

```bash
# List applications by sync wave order
oc get applications -n openshift-gitops \
  -o custom-columns=NAME:.metadata.name,WAVE:.metadata.annotations."argocd\.argoproj\.io/sync-wave" \
  --sort-by='.metadata.annotations.argocd\.argoproj\.io/sync-wave'
```

### View ArgoCD Projects

```bash
# List all projects
oc get appprojects -n openshift-gitops

# Get project details
oc describe appproject <project-name> -n openshift-gitops

# See which apps belong to a project
oc get applications -n openshift-gitops -o json | \
  jq -r '.items[] | select(.spec.project=="rhoai-infrastructure") | .metadata.name'
```

## Access ArgoCD UI

```bash
# Get URL
echo "https://$(oc get route openshift-gitops-server -n openshift-gitops -o jsonpath='{.spec.host}')"

# Get password
oc get secret openshift-gitops-cluster -n openshift-gitops \
  -o jsonpath='{.data.admin\.password}' | base64 -d && echo
```

## ArgoCD CLI Login

```bash
ARGOCD_SERVER=$(oc get route openshift-gitops-server -n openshift-gitops -o jsonpath='{.spec.host}')
ARGOCD_PASSWORD=$(oc get secret openshift-gitops-cluster -n openshift-gitops -o jsonpath='{.data.admin\.password}' | base64 -d)

argocd login $ARGOCD_SERVER --username admin --password $ARGOCD_PASSWORD --insecure
```

## Monitor Resource Deployment

```bash
# Watch GPU nodes
oc get machines -n openshift-machine-api -l gpu-instance-type -w

# Watch model serving
oc get inferenceservice -n demo -w

# Watch AnythingLLM
oc get pods -n demo-apps -l app.kubernetes.io/name=anythingllm -w

# Check all namespaces
oc get pods --all-namespaces | grep -E "demo|rhoai|nvidia|kueue"
```

## Disable Auto-Sync (for debugging)

```bash
# Disable auto-sync for an application
oc patch application <app-name> -n openshift-gitops \
  --type merge -p '{"spec":{"syncPolicy":{"automated":null}}}'

# Re-enable auto-sync
oc patch application <app-name> -n openshift-gitops \
  --type merge -p '{"spec":{"syncPolicy":{"automated":{"selfHeal":true,"prune":true}}}}'
```

## Compare with Git

```bash
# Show differences between live and Git
argocd app diff <app-name>

# Show last sync result
argocd app get <app-name> --show-operation
```

## Export Application Manifest

```bash
# Export application spec
oc get application <app-name> -n openshift-gitops -o yaml > exported-app.yaml

# Export all applications
oc get applications -n openshift-gitops -o yaml > all-apps.yaml
```
