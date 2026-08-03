#!/usr/bin/env bash
# Migration TRIGGER test: does Architect migrate on a graceful `kubectl drain` (Eviction API)?
# This is the proxy for the real production triggers — Karpenter consolidation, Cluster Autoscaler
# scale-down, managed-node-group updates, spot rebalance drain — which all evict via the same API.
# Verifies state is preserved by exec'ing INTO the migrated pod (no external writer, which the drain evicts).
set -u
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"
NAME=${1:-dr}; KEYS=${2:-1000000}
kn delete deploy "$NAME" --force --grace-period=0 >/dev/null 2>&1; sleep 2
cat <<EOF | kn apply -f - >/dev/null 2>&1
apiVersion: apps/v1
kind: Deployment
metadata: {name: $NAME, labels: {app: $NAME}}
spec:
  replicas: 1
  selector: {matchLabels: {app: $NAME}}
  template:
    metadata:
      labels: {app: $NAME}
      annotations:
$(buffering_annotations "$NAME")
    spec:
      runtimeClassName: runc-architect
      containers:
        - name: $NAME
          image: redis:7-alpine
          args: ["--enable-debug-command","yes","--save",""]
          ports: [{containerPort: 6379}]
          resources: {requests: {memory: "128Mi"}, limits: {memory: "512Mi"}}
EOF
kn wait --for=condition=Ready pod -l app=$NAME --timeout=150s >/dev/null 2>&1 || { echo POD-NOT-READY; exit 1; }
POD=$(kn get pod -l app=$NAME -o jsonpath='{.items[0].metadata.name}'); NODE=$(kn get pod -l app=$NAME -o jsonpath='{.items[0].spec.nodeName}')
kn exec $POD -c $NAME -- redis-cli DEBUG POPULATE $KEYS >/dev/null 2>&1
kn exec $POD -c $NAME -- redis-cli SET drain_marker survived >/dev/null 2>&1
log "### drain-trigger $NAME: seed DBSIZE=$(kn exec $POD -c $NAME -- redis-cli DBSIZE 2>/dev/null|tr -d '\r') on ${NODE##*.}"
echo "=== kubectl drain $NODE (Eviction API — Karpenter/CA/spot use this) ==="
timeout 160 kc drain $NODE --ignore-daemonsets --delete-emptydir-data --force --grace-period=60 --pod-selector="app=$NAME" 2>&1 | tail -2
for i in $(seq 1 40); do nr=$(kn get pod -l app=$NAME -o jsonpath='{.items[0].spec.nodeName}' 2>/dev/null); rd=$(kn get pod -l app=$NAME -o jsonpath='{.items[0].status.containerStatuses[0].ready}' 2>/dev/null); [ "$rd" = true ] && [ -n "$nr" ] && [ "$nr" != "$NODE" ] && break; sleep 4; done
kc uncordon $NODE >/dev/null 2>&1; sleep 4
NP=$(kn get pod -l app=$NAME -o jsonpath='{.items[0].metadata.name}'); NN=$(kn get pod -l app=$NAME -o jsonpath='{.items[0].spec.nodeName}')
DB=$(kn exec $NP -c $NAME -- redis-cli DBSIZE 2>/dev/null|tr -d '\r'); MK=$(kn exec $NP -c $NAME -- redis-cli GET drain_marker 2>/dev/null|tr -d '\r')
log "drain result: moved ${NODE##*.}->${NN##*.} DBSIZE=$DB marker=$MK  (state preserved => Architect hooks the eviction path, so Karpenter/CA/spot drains trigger migration)"
kn delete deploy "$NAME" --force --grace-period=0 >/dev/null 2>&1
