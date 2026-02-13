#!/bin/bash
# bootstrap.sh - Smart GitOps installer for RHOAI AnythingLLM Demos
set -e

echo "🔍 Checking for OpenShift GitOps..."

# Check if GitOps is already installed
if oc get deployment openshift-gitops-server -n openshift-gitops &>/dev/null; then
  echo "✅ OpenShift GitOps is already installed. Skipping installation."
  echo ""
  echo "ArgoCD URL:"
  oc get route openshift-gitops-server -n openshift-gitops -o jsonpath='https://{.spec.host}{"\n"}' 2>/dev/null || echo "  (Route not yet available)"
  exit 0
fi

echo "📦 Installing OpenShift GitOps Operator..."
oc apply -k bootstrap/gitops-operator/base/

echo "⏳ Waiting for GitOps Operator subscription to be created..."
sleep 5

echo "⏳ Checking for pending install plans..."
# Check if install plan needs approval
max_retries=3
retry=0
while [ $retry -lt $max_retries ]; do
  install_plan=$(oc get subscription openshift-gitops-operator -n openshift-operators -o jsonpath='{.status.installplan.name}' 2>/dev/null || echo "")
  if [ -n "$install_plan" ]; then
    # Check if install plan needs approval
    approved=$(oc get installplan "$install_plan" -n openshift-operators -o jsonpath='{.spec.approved}' 2>/dev/null || echo "")
    if [ "$approved" = "false" ]; then
      echo "  📝 Install plan $install_plan requires approval, approving..."
      oc patch installplan "$install_plan" -n openshift-operators --type merge -p '{"spec":{"approved":true}}'
      echo "  ✅ Install plan approved"
      break
    elif [ "$approved" = "true" ]; then
      echo "  ✅ Install plan $install_plan is already approved"
      break
    fi
  fi
  retry=$((retry + 1))
  sleep 5
done

echo "⏳ Waiting for GitOps Operator CSV to be ready..."
timeout=300
elapsed=0
while [ $elapsed -lt $timeout ]; do
  csv_phase=$(oc get csv -n openshift-operators -l operators.coreos.com/openshift-gitops-operator.openshift-operators -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo "")
  if [ "$csv_phase" = "Succeeded" ]; then
    echo "✅ GitOps Operator CSV is ready"
    break
  fi
  echo "  CSV phase: ${csv_phase:-Pending}... (${elapsed}s elapsed)"
  sleep 10
  elapsed=$((elapsed + 10))
done

if [ $elapsed -ge $timeout ]; then
  echo "❌ Timeout waiting for GitOps Operator CSV"
  exit 1
fi

echo "⏳ Waiting for GitOps Operator deployment to be available..."
oc wait --for=condition=Available \
  deployment/openshift-gitops-operator-controller-manager \
  -n openshift-operators --timeout=120s

echo "🚀 Creating ArgoCD instance..."
oc apply -k bootstrap/gitops-operator/instance/

echo "⏳ Waiting for ArgoCD to be ready..."
oc wait --for=condition=Ready \
  pod -l app.kubernetes.io/name=openshift-gitops-server \
  -n openshift-gitops --timeout=300s

echo ""
echo "✅ GitOps installation complete!"
echo ""
echo "ArgoCD Details:"
echo "  URL: https://$(oc get route openshift-gitops-server -n openshift-gitops -o jsonpath='{.spec.host}')"
echo "  Username: admin"
echo "  Password: $(oc get secret openshift-gitops-cluster -n openshift-gitops -o jsonpath='{.data.admin\.password}' | base64 -d)"
echo ""
