#!/usr/bin/env bash
# Downtime curve: for each RSS, measure server-side freeze+dump window and (per-pod-scoped)
# end-to-end buffered window from daemon logs. Deploy on big nodes (cordon small workers first).
# Env: SIZES="108MB:1300000 515MB:6000000 1GB:12000000 2GB:24000000 4GB:48000000 8GB:96000000"
set -u
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"
NAME=dtc
SIZES="${SIZES:-108MB:1300000 515MB:6000000 1GB:12000000 2GB:24000000 4GB:48000000 8GB:96000000}"
kn delete deploy,svc,pod "$NAME" "${NAME}-w" --force --grace-period=0 >/dev/null 2>&1; sleep 2
cat <<EOF | kn apply -f - >/dev/null 2>&1
apiVersion: apps/v1
kind: Deployment
metadata: {name: $NAME, labels: {app: $NAME}}
spec:
  replicas: 1
  selector: {matchLabels: {app: $NAME}}
  template:
    metadata: {labels: {app: $NAME}, annotations: {$(buffering_annotations "$NAME" | sed 's/^ *//' | paste -sd, -)}}
    spec:
      runtimeClassName: runc-architect
      containers:
        - name: $NAME
          image: redis:7-alpine
          args: ["--enable-debug-command","yes","--save","","--maxmemory","0"]
          ports: [{containerPort: 6379}]
          resources: {requests: {memory: "256Mi"}, limits: {memory: "11Gi"}}
---
apiVersion: v1
kind: Service
metadata: {name: $NAME, annotations: {architect.loopholelabs.io/shadow-service: "true"}}
spec: {type: ClusterIP, selector: {app: $NAME}, ports: [{port: 6379, targetPort: 6379}]}
EOF
kn wait --for=condition=Ready pod -l app=$NAME --timeout=180s >/dev/null 2>&1 || { echo POD-NOT-READY; exit 1; }
ensure_writer "${NAME}-w"
R(){ kn exec ${NAME}-w -- redis-cli -h ${NAME}-shadow -p 6379 "$@" 2>/dev/null | tr -d '\r'; }
log "### downtime curve (measured; DEBUG POPULATE = compressible, best-case transfer)"
printf "%-7s %-10s %-9s %-11s %s\n" LABEL used_mem dump e2e_stall state | tee -a "$CAMP/retest_findings.txt"
for spec in $SIZES; do
  LABEL=${spec%%:*}; KEYS=${spec##*:}
  R FLUSHALL >/dev/null; R DEBUG POPULATE $KEYS >/dev/null
  MEM=$(R INFO memory | grep used_memory_human | cut -d: -f2)
  SRC=$(kn get pod -l app=$NAME -o jsonpath='{.items[0].metadata.name}')
  MOVE=$(migrate "$NAME"); sleep 5
  NEWPOD=$(kn get pod -l app=$NAME -o jsonpath='{.items[0].metadata.name}')
  DBA=$(R DBSIZE); ST=$([ "${DBA:-0}" -gt 10 ] 2>/dev/null && echo preserved || echo FRESH)
  kc -n architect logs -l app.kubernetes.io/name=architectd --tail=15000 2>/dev/null > /tmp/dtc.log
  read DUMP E2E < <(python3 - "$SRC" "$NEWPOD" <<'PY'
import sys,re
src,new=sys.argv[1],sys.argv[2]
def secs(t):h,m,s=map(int,t.split(":"));return h*3600+m*60+s
buf=dd=fl=None
for ln in open("/tmp/dtc.log"):
    tm=re.search(r'\b(\d\d):(\d\d):(\d\d)\b',ln)
    if not tm: continue
    t=secs(tm.group(0)); lo=ln.lower()
    if src in ln and 'starting router-level buffering' in lo and buf is None: buf=t
    if src in ln and 'successfully created checkpoint' in lo and (dd is None or t>=dd): dd=t
    if new in ln and ('acknowledged flush for target' in lo or 'completed flushing migration buffer' in lo) and (fl is None or t>=fl): fl=t
print((dd-buf) if buf is not None and dd is not None else -1, (fl-buf) if buf is not None and fl is not None else -1)
PY
)
  printf "%-7s %-10s %-9s %-11s %s\n" "$LABEL" "${MEM:-?}" "${DUMP}s" "${E2E}s" "$ST" | tee -a "$CAMP/retest_findings.txt"
done
kn delete deploy,svc,pod "$NAME" "${NAME}-w" --force --grace-period=0 >/dev/null 2>&1
