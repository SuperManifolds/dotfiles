#!/usr/bin/env bash
# Lazy-pages / post-copy migration. EXPECT (on main): source runs a criu --lazy-pages
# page-server, destination emits LazyPagesTransferStarted and faults over userfaultfd,
# container starts ~2s after transfer begins, state preserved. Caveat: the held TCP
# connection still resets — lazy preserves STATE, not the connection (skips the buffering hook).
set -u
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"
NAME=${1:-lzt}; KEYS=${2:-3000000}
kn delete deploy,svc,pod "$NAME" "${NAME}-w" --force --grace-period=0 >/dev/null 2>&1; sleep 2
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
        architect.loopholelabs.io/lazy-pages-migration-containers: '["$NAME"]'
    spec:
      runtimeClassName: runc-architect
      containers:
        - name: $NAME
          image: redis:7-alpine
          args: ["--enable-debug-command","yes","--save",""]
          ports: [{containerPort: 6379}]
          resources: {requests: {memory: "256Mi"}, limits: {memory: "1536Mi"}}
---
apiVersion: v1
kind: Service
metadata: {name: $NAME, annotations: {architect.loopholelabs.io/shadow-service: "true"}}
spec: {type: ClusterIP, selector: {app: $NAME}, ports: [{port: 6379, targetPort: 6379}]}
EOF
kn wait --for=condition=Ready pod -l app=$NAME --timeout=180s >/dev/null 2>&1 || { echo POD-NOT-READY; exit 1; }
ensure_writer "${NAME}-w"
R(){ kn exec ${NAME}-w -- redis-cli -h ${NAME}-shadow -p 6379 "$@" 2>/dev/null | tr -d '\r'; }
R DEBUG POPULATE $KEYS >/dev/null; R SET marker preserved >/dev/null
SRC=$(kn get pod -l app=$NAME -o jsonpath='{.items[0].metadata.name}')
log "### lazy-pages $NAME mem=$(R INFO memory|grep used_memory_human|cut -d: -f2) DBSIZE=$(R DBSIZE)"
MOVE=$(migrate "$NAME"); sleep 6
log "move=$MOVE DBSIZE=$(R DBSIZE) marker=$(R GET marker)"
echo "=== lazy-pages engagement (daemon logs) ==="
kc -n architect logs -l app.kubernetes.io/name=architectd --since=5m 2>/dev/null | grep -iE "$SRC|lazy" | grep -iE \
  "is in lazy-pages-migration-containers annotation|opted into lazy-pages|page-server is ready|LazyPagesTransferStarted|Lazy-pages transfer started|connected to source page-server|criu lazy-pages dump exited cleanly" \
  | sed -E 's/controlPlaneRaddr=[^ ]* //' | cut -c1-150 | tail -8
log "NOTE: state preserved but the held TCP connection resets — lazy != buffered (separate mechanisms)."
kn delete deploy,svc,pod "$NAME" "${NAME}-w" --force --grace-period=0 >/dev/null 2>&1
