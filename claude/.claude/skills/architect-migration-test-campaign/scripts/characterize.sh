#!/usr/bin/env bash
# Migrate a workload once and classify the restored process as RESTORED vs FRESH — for
# CRIU-failure-class targets (io_uring, inotify, ptrace, …). Uses a marker file in the container.
# Usage: characterize.sh <name> <image> <port> ['<extra container yaml>']
set -u
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"
NAME=$1; IMAGE=$2; PORT=$3; EXTRA=${4:-}
kn delete deploy,svc "$NAME" --force --grace-period=0 >/dev/null 2>&1; sleep 1
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
          image: $IMAGE
          ports: [{containerPort: $PORT}]
          $EXTRA
---
apiVersion: v1
kind: Service
metadata: {name: $NAME, annotations: {architect.loopholelabs.io/shadow-service: "true"}}
spec: {type: ClusterIP, selector: {app: $NAME}, ports: [{port: $PORT, targetPort: $PORT}]}
EOF
kn wait --for=condition=Ready pod -l app=$NAME --timeout=180s >/dev/null 2>&1 || { log "$NAME | POD-NOT-READY"; exit 0; }
POD=$(kn get pod -l app=$NAME -o jsonpath='{.items[0].metadata.name}')
kn exec $POD -c $NAME -- sh -c 'echo restored-marker >/tmp/criu_marker' >/dev/null 2>&1 || true
MOVE=$(migrate "$NAME"); sleep 6
NP=$(kn get pod -l app=$NAME -o jsonpath='{.items[0].metadata.name}')
MARK=$(kn exec $NP -c $NAME -- cat /tmp/criu_marker 2>/dev/null | tr -d '\r')
CLASS=$([ "$MARK" = "restored-marker" ] && echo RESTORED || echo FRESH)
log "### characterize $NAME move=$MOVE => $CLASS"
echo "=== CRIU dump/restore errors (daemon logs) ==="
kc -n architect logs -l app.kubernetes.io/name=architectd --since=4m 2>/dev/null | grep -iE "$POD|$NP" \
  | grep -iE "proc_parse|fsnotify|seize|Unknown|anon_inode|criu failed|RESTORE errno|starting fresh|CheckpointNotFound" \
  | sed -E 's/controlPlaneRaddr=[^ ]* //' | cut -c1-160 | tail -6
kn delete deploy,svc "$NAME" --force --grace-period=0 >/dev/null 2>&1
