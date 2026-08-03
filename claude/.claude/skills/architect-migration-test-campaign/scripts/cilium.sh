#!/usr/bin/env bash
# GATED / DESTRUCTIVE. Swap the CNI to Cilium to test F-2, then roll back.
# Usage: cilium.sh <overlay|eni|chaining> <install|test|rollback>
# Env: KUBECONFIG CTX REGION CLUSTER
# NOTES:
#   overlay  = reliably reproduces F-2 (eBPF datapath bypasses the router XDP -> shadow refused).
#   eni      = VPC-native IPs; needs BOTH node roles to have AmazonEKS_CNI_Policy, and correct
#              egress masquerade or Architect's shim image pull fails (architectd CrashLoopBackOff).
#   chaining = keeps aws-node; aws-cni chaining is finicky (PodCIDR errors) — often inconclusive.
# ALWAYS run `cilium.sh <mode> rollback` after. It restores VPC CNI and recycles nodes.
set -u
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"
: "${REGION:?export REGION}"; : "${CLUSTER:?export CLUSTER}"
MODE=${1:?overlay|eni|chaining}; ACTION=${2:?install|test|rollback}
EP=$(aws eks describe-cluster --name "$CLUSTER" --region "$REGION" --query 'cluster.endpoint' --output text 2>/dev/null | sed 's#https://##')
CVER="${CVER:-1.19.6}"

recycle_nodes(){ # terminate all cluster instances; ASGs replace them
  local ids; ids=$(aws ec2 describe-instances --region "$REGION" \
    --filters "Name=tag:kubernetes.io/cluster/$CLUSTER,Values=owned" "Name=instance-state-name,Values=running" \
    --query 'Reservations[].Instances[].InstanceId' --output text 2>/dev/null | tr '\n\t' ' ')
  echo "recycling: $ids"; [ -n "$(echo $ids)" ] && aws ec2 terminate-instances --region "$REGION" --instance-ids $(echo $ids) >/dev/null 2>&1
  echo "waiting for nodes+architect to converge (~5-10 min)..."
  for i in $(seq 1 50); do
    local wn arch; wn=$(kc get nodes -l architect.loopholelabs.io/node=true --no-headers 2>/dev/null | grep -c " Ready ")
    arch=$(kc -n architect get pods --no-headers 2>/dev/null | grep -cE "1/1|2/2")
    echo "[$((i*15))s] node=true workers Ready=$wn architect=$arch/6"; [ "$wn" -ge 2 ] && [ "$arch" -ge 6 ] && break; sleep 15
  done
}

case "$ACTION" in
install)
  echo ">>> Installing Cilium ($MODE). This removes VPC CNI (except chaining) and recycles nodes."
  if [ "$MODE" != chaining ]; then
    aws eks delete-addon --cluster-name "$CLUSTER" --region "$REGION" --addon-name vpc-cni >/dev/null 2>&1
    for i in $(seq 1 20); do [ "$(kc -n kube-system get ds aws-node --no-headers 2>/dev/null | wc -l)" = 0 ] && break; sleep 5; done
  fi
  case "$MODE" in
    overlay)  ARGS="--set eni.enabled=false --set ipam.mode=cluster-pool --set ipam.operator.clusterPoolIPv4PodCIDRList={10.244.0.0/16} --set routingMode=tunnel --set tunnelProtocol=vxlan";;
    eni)      ARGS="--set eni.enabled=true --set ipam.mode=eni --set routingMode=native --set endpointRoutes.enabled=true --set enableIPv4Masquerade=true --set egressMasqueradeInterfaces=eth0+ --set bpf.masquerade=false";;
    chaining) ARGS="--set cni.chainingMode=aws-cni --set cni.exclusive=false --set enableIPv4Masquerade=false --set routingMode=native --set endpointRoutes.enabled=true";;
  esac
  helm --kube-context "$CTX" install cilium cilium/cilium --version "$CVER" -n kube-system \
    $ARGS --set kubeProxyReplacement=false --set operator.replicas=1 \
    --set k8sServiceHost="$EP" --set k8sServicePort=443 2>&1 | tail -3
  [ "$MODE" != chaining ] && recycle_nodes
  echo "check: kubectl -n kube-system get ds cilium ; architect pods Ready"
  ;;
test)
  N=cil; kn delete deploy,svc,pod $N ${N}-w --force --grace-period=0 >/dev/null 2>&1; sleep 2
  cat <<EOF | kn apply -f - >/dev/null 2>&1
apiVersion: apps/v1
kind: Deployment
metadata: {name: $N, labels: {app: $N}}
spec:
  replicas: 1
  selector: {matchLabels: {app: $N}}
  template:
    metadata: {labels: {app: $N}, annotations: {$(buffering_annotations $N | sed 's/^ *//' | paste -sd, -)}}
    spec:
      runtimeClassName: runc-architect
      containers: [{name: $N, image: redis:7-alpine, args: ["--save",""], ports: [{containerPort: 6379}]}]
---
apiVersion: v1
kind: Service
metadata: {name: $N, annotations: {architect.loopholelabs.io/shadow-service: "true"}}
spec: {type: ClusterIP, selector: {app: $N}, ports: [{port: 6379, targetPort: 6379}]}
EOF
  kn wait --for=condition=Ready pod -l app=$N --timeout=180s >/dev/null 2>&1 || { log "cil pod NOT READY under $MODE (see architectd logs — eni egress?)"; exit 1; }
  ensure_writer ${N}-w; PIP=$(kn get pod -l app=$N -o jsonpath='{.items[0].status.podIP}')
  log "### Cilium $MODE F-2 test  (pod ip=$PIP)"
  log "direct pod: $(kn exec ${N}-w -- redis-cli -h $PIP -p 6379 -t 5 PING 2>&1|tr -d '\r')"
  log "front svc:  $(kn exec ${N}-w -- redis-cli -h $N -p 6379 -t 5 PING 2>&1|tr -d '\r')"
  log "SHADOW svc: $(kn exec ${N}-w -- redis-cli -h ${N}-shadow -p 6379 -t 5 PING 2>&1|tr -d '\r')  <- refused => eBPF bypasses router XDP (F-2)"
  kn delete deploy,svc,pod $N ${N}-w --force --grace-period=0 >/dev/null 2>&1
  ;;
rollback)
  helm --kube-context "$CTX" uninstall cilium -n kube-system 2>&1 | tail -1
  aws eks create-addon --cluster-name "$CLUSTER" --region "$REGION" --addon-name vpc-cni --resolve-conflicts OVERWRITE >/dev/null 2>&1
  recycle_nodes
  bash "$(dirname "$0")/uncordon-all.sh"
  echo "restored VPC CNI. Verify aws-node Ready on all nodes + a smoke migration passes."
  ;;
esac
