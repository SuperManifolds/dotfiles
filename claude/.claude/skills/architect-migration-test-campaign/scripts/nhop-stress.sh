#!/usr/bin/env bash
# N-hop repeated-migration stress (F-3). Sets a fresh key BEFORE each hop and checks it
# AFTER, so per-hop preservation is unambiguous. Reveals the intermittent (~50%) pattern.
# Usage: nhop-stress.sh [name] [hops] [bulk-keys]   (best on a stable 2-node pair; cordon others)
set -u
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"
NAME=${1:-nhop}; HOPS=${2:-10}; BULK=${3:-200000}
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
    spec:
      runtimeClassName: runc-architect
      containers:
        - name: $NAME
          image: redis:7-alpine
          args: ["--enable-debug-command","yes","--save",""]
          ports: [{containerPort: 6379}]
          resources: {requests: {memory: "128Mi"}, limits: {memory: "512Mi"}}
---
apiVersion: v1
kind: Service
metadata: {name: $NAME, annotations: {architect.loopholelabs.io/shadow-service: "true"}}
spec: {type: ClusterIP, selector: {app: $NAME}, ports: [{port: 6379, targetPort: 6379}]}
EOF
kn wait --for=condition=Ready pod -l app=$NAME --timeout=180s >/dev/null 2>&1 || { echo POD-NOT-READY; exit 1; }
ensure_writer "${NAME}-w"
R(){ kn exec ${NAME}-w -- redis-cli -h ${NAME}-shadow -p 6379 "$@" 2>/dev/null | tr -d '\r'; }
R DEBUG POPULATE $BULK >/dev/null
log "### N-hop stress $NAME: $HOPS hops, seed DBSIZE=$(R DBSIZE)"
printf "%-4s %-10s %-9s %s\n" HOP move survived result | tee -a "$CAMP/retest_findings.txt"
lost=0
for h in $(seq 1 $HOPS); do
  R SET hop$h "v$h" >/dev/null
  MOVE=$(migrate "$NAME"); sleep 4
  GOT=$(R GET hop$h)
  if [ "$GOT" = "v$h" ]; then SURV=YES; RES=restored; else SURV=no; RES=FRESH; lost=$((lost+1)); fi
  printf "%-4s %-10s %-9s %s\n" "$h" "$MOVE" "$SURV" "$RES" | tee -a "$CAMP/retest_findings.txt"
  db=$(R DBSIZE); [ "${db:-0}" -lt 10 ] 2>/dev/null && R DEBUG POPULATE $BULK >/dev/null
done
log "=> $lost/$HOPS hops lost state (expect intermittent ~50%, NOT a fixed hop)"
kn delete deploy,svc,pod "$NAME" "${NAME}-w" --force --grace-period=0 >/dev/null 2>&1
