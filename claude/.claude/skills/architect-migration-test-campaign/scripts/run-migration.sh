#!/usr/bin/env bash
# Generic single-workload migration test.
# Usage: run-migration.sh <name> <image> <port> <tcp|http|redis> ['<extra container yaml>']
#   extra yaml is spliced into the container spec (e.g. 'args: [...]' or 'env: [...]').
set -u
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"
NAME=$1; IMAGE=$2; PORT=$3; PTYPE=$4; EXTRA=${5:-}
echo "### $NAME ($IMAGE) port=$PORT probe=$PTYPE ###"
kn delete deploy,svc,pod "$NAME" "${NAME}-probe" --force --grace-period=0 >/dev/null 2>&1; sleep 1
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
if ! kn wait --for=condition=Ready pod -l app=$NAME --timeout=240s >/dev/null 2>&1; then
  log "$NAME | POD-NOT-READY"; kn delete deploy,svc "$NAME" --force --grace-period=0 >/dev/null 2>&1; exit 0
fi
NODE=$(kn get pod -l app=$NAME -o jsonpath='{.items[0].spec.nodeName}')
# start held-connection probe through the SHADOW service
case $PTYPE in
  redis) kn run ${NAME}-probe --image=redis:7-alpine --restart=Never -- redis-cli -h ${NAME}-shadow -p $PORT -i 0.2 -r 300 PING >/dev/null 2>&1; TOK=PONG;;
  http)  kn run ${NAME}-probe --image=python:3-alpine --restart=Never --command -- python3 -u -c "$(cat "$PROBES/probe_http.py")" ${NAME}-shadow $PORT >/dev/null 2>&1; TOK=OK;;
  *)     kn run ${NAME}-probe --image=python:3-alpine --restart=Never --command -- python3 -u -c "$(cat "$PROBES/probe_tcp.py")" ${NAME}-shadow $PORT >/dev/null 2>&1; TOK=OK;;
esac
sleep 8
PRE=$(kn logs ${NAME}-probe 2>&1 | grep -c "$TOK")
MOVE=$(migrate "$NAME")
sleep 6
L=$(kn logs ${NAME}-probe 2>&1); OKC=$(echo "$L" | grep -c "$TOK"); ERR=$(echo "$L" | grep -c "ERR")
NEW=${MOVE##*->}
V=FAIL; [ -n "$NEW" ] && [ "$OKC" -gt "$PRE" ] && [ "$ERR" -le 3 ] && V=PASS
[ -n "$NEW" ] && [ "$OKC" -gt "$PRE" ] && [ "$ERR" -gt 3 ] && V=PARTIAL
log "$NAME | move=$MOVE ok=$OKC(pre$PRE) err=$ERR => $V"
kn delete deploy,svc,pod "$NAME" "${NAME}-probe" --force --grace-period=0 >/dev/null 2>&1
