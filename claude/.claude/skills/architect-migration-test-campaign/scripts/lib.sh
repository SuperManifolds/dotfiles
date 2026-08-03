#!/usr/bin/env bash
# Shared env + helpers for the Architect migration test campaign scripts.
# Source this from every script:  source "$(dirname "$0")/lib.sh"
#
# Env contract (export before running):
#   KUBECONFIG   kubeconfig for the target throwaway EKS cluster (required)
#   CTX          kube-context     (default: current-context)
#   NS           namespace        (default: default)
#   REGION       aws region       (needed for aws/nodegroup/Cilium scripts)
#   CLUSTER      eks cluster name (needed for aws/nodegroup/Cilium scripts)
#   CAMP         results/log dir  (default: ./migration-results)
: "${KUBECONFIG:?export KUBECONFIG to your throwaway EKS cluster kubeconfig}"
export KUBECONFIG
CTX="${CTX:-$(kubectl config current-context 2>/dev/null)}"
NS="${NS:-default}"
CAMP="${CAMP:-$(pwd)/migration-results}"; mkdir -p "$CAMP"
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROBES="$SKILL_DIR/probes"

# buffering annotations applied to every managed workload's pod template
buffering_annotations(){ local n="$1"; cat <<EOF
        architect.loopholelabs.io/managed-containers: '["$n"]'
        architect.loopholelabs.io/shadow-service-pod: "true"
        architect.loopholelabs.io/postmigration-autoscaleup-containers: '["$n"]'
        architect.loopholelabs.io/disable-autoscaledown-containers: '["$n"]'
        architect.loopholelabs.io/rewrite-established-addresses-containers: '["$n"]'
EOF
}

kn(){ kubectl --context "$CTX" -n "$NS" "$@"; }
kc(){ kubectl --context "$CTX" "$@"; }

# migrate <app-label-value> : cordon the pod's node, delete it, wait until Ready on a
# DIFFERENT node, then uncordon. Prints "fromNode->toNode" (toNode empty = stuck).
migrate(){
  local app="$1" pod node nr rd new=""
  pod=$(kn get pod -l app="$app" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
  node=$(kn get pod -l app="$app" -o jsonpath='{.items[0].spec.nodeName}' 2>/dev/null)
  kc cordon "$node" >/dev/null 2>&1
  kn delete pod "$pod" --wait=false >/dev/null 2>&1
  local i
  for i in $(seq 1 90); do
    nr=$(kn get pod -l app="$app" -o jsonpath='{.items[0].spec.nodeName}' 2>/dev/null)
    rd=$(kn get pod -l app="$app" -o jsonpath='{.items[0].status.containerStatuses[0].ready}' 2>/dev/null)
    [ "$rd" = true ] && [ -n "$nr" ] && [ "$nr" != "$node" ] && { new="$nr"; break; }
    sleep 3
  done
  kc uncordon "$node" >/dev/null 2>&1
  echo "${node%%.*}->${new%%.*}"
}

# redis writer helper pod that talks to <name>-shadow
ensure_writer(){ local w="$1"
  kn get pod "$w" >/dev/null 2>&1 || kn run "$w" --image=redis:7-alpine --restart=Never --command -- sleep 7200 >/dev/null 2>&1
  kn wait --for=condition=Ready pod "$w" --timeout=60s >/dev/null 2>&1
}

log(){ echo "$*" | tee -a "$CAMP/retest_findings.txt"; }
