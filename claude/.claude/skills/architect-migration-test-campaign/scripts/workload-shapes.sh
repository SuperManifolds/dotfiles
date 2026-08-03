#!/usr/bin/env bash
# Controller shapes & lifecycle paths that differ from a single-replica Deployment.
# Usage: workload-shapes.sh <statefulset|pvc|multireplica|scaletozero>
set -u
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"
CMD=${1:?usage: workload-shapes.sh statefulset|pvc|multireplica|scaletozero}

# pick an AZ that has >=2 schedulable node=true workers (EBS RWO is AZ-bound)
pick_az(){
  kc get nodes -l architect.loopholelabs.io/node=true -o jsonpath='{range .items[*]}{.metadata.labels.topology\.kubernetes\.io/zone}{"\n"}{end}' 2>/dev/null \
    | sort | uniq -c | awk '$1>=2{print $2; exit}'
}

case "$CMD" in
statefulset)
  log "### StatefulSet under runc-architect (EXPECT: CrashLoopBackOff — no pod-template-hash)"
  kn delete statefulset,svc sts sts-hl --force --grace-period=0 >/dev/null 2>&1; kn delete pvc data-sts-0 >/dev/null 2>&1; sleep 2
  cat <<EOF | kn apply -f - >/dev/null 2>&1
apiVersion: v1
kind: Service
metadata: {name: sts-hl, labels: {app: sts}}
spec: {clusterIP: None, selector: {app: sts}, ports: [{port: 6379}]}
---
apiVersion: apps/v1
kind: StatefulSet
metadata: {name: sts, labels: {app: sts}}
spec:
  serviceName: sts-hl
  replicas: 1
  selector: {matchLabels: {app: sts}}
  template:
    metadata: {labels: {app: sts}, annotations: {$(buffering_annotations sts | sed 's/^ *//' | paste -sd, -)}}
    spec:
      runtimeClassName: runc-architect
      containers: [{name: sts, image: redis:7-alpine, args: ["--save",""], ports: [{containerPort: 6379}]}]
EOF
  sleep 60
  ST=$(kn get pod sts-0 -o jsonpath='{.status.containerStatuses[0].state.waiting.reason}' 2>/dev/null)
  log "sts-0 state: ${ST:-<running?>} (daemon log below)"
  kc -n architect logs -l app.kubernetes.io/name=architectd --since=3m 2>/dev/null | grep sts-0 | grep -i "template hash" | tail -1
  kn delete statefulset,svc sts sts-hl --force --grace-period=0 >/dev/null 2>&1; kn delete pvc data-sts-0 >/dev/null 2>&1
  ;;

pvc)
  AZ=$(pick_az); : "${AZ:?need an AZ with >=2 node=true workers for EBS RWO}"
  log "### Deployment + EBS RWO PVC in AZ $AZ (EXPECT: state + PVC preserved within-AZ)"
  kn delete deploy,svc,pod dpv dpv-w --force --grace-period=0 >/dev/null 2>&1; kn delete pvc dpv-data >/dev/null 2>&1; sleep 2
  cat <<EOF | kn apply -f - >/dev/null 2>&1
apiVersion: v1
kind: PersistentVolumeClaim
metadata: {name: dpv-data}
spec: {accessModes: [ReadWriteOnce], storageClassName: gp2, resources: {requests: {storage: 2Gi}}}
---
apiVersion: apps/v1
kind: Deployment
metadata: {name: dpv, labels: {app: dpv}}
spec:
  replicas: 1
  strategy: {type: Recreate}
  selector: {matchLabels: {app: dpv}}
  template:
    metadata: {labels: {app: dpv}, annotations: {$(buffering_annotations dpv | sed 's/^ *//' | paste -sd, -)}}
    spec:
      runtimeClassName: runc-architect
      nodeSelector: {topology.kubernetes.io/zone: $AZ}
      containers: [{name: dpv, image: redis:7-alpine, args: ["--enable-debug-command","yes","--save","","--dir","/data"], ports: [{containerPort: 6379}], volumeMounts: [{name: data, mountPath: /data}]}]
      volumes: [{name: data, persistentVolumeClaim: {claimName: dpv-data}}]
---
apiVersion: v1
kind: Service
metadata: {name: dpv, annotations: {architect.loopholelabs.io/shadow-service: "true"}}
spec: {type: ClusterIP, selector: {app: dpv}, ports: [{port: 6379, targetPort: 6379}]}
EOF
  kn wait --for=condition=Ready pod -l app=dpv --timeout=200s >/dev/null 2>&1 || { log "dpv NOT READY"; exit 1; }
  ensure_writer dpv-w; POD=$(kn get pod -l app=dpv -o jsonpath='{.items[0].metadata.name}')
  kn exec dpv-w -- redis-cli -h dpv -p 6379 SET inmem alive >/dev/null 2>&1
  kn exec $POD -c dpv -- sh -c 'echo pvc-marker >/data/onpvc.txt' 2>/dev/null
  MOVE=$(migrate dpv); sleep 5; NP=$(kn get pod -l app=dpv -o jsonpath='{.items[0].metadata.name}')
  log "move=$MOVE  in-memory(CRIU)=$(kn exec dpv-w -- redis-cli -h dpv -p 6379 GET inmem 2>/dev/null|tr -d '\r')  on-PVC=$(kn exec $NP -c dpv -- cat /data/onpvc.txt 2>/dev/null|tr -d '\r')"
  kn delete deploy,svc,pod dpv dpv-w --force --grace-period=0 >/dev/null 2>&1; kn delete pvc dpv-data >/dev/null 2>&1
  ;;

multireplica)
  log "### 3-replica Deployment: migrate one, others undisturbed"
  kn delete deploy,svc mr --force --grace-period=0 >/dev/null 2>&1; sleep 2
  cat <<EOF | kn apply -f - >/dev/null 2>&1
apiVersion: apps/v1
kind: Deployment
metadata: {name: mr, labels: {app: mr}}
spec:
  replicas: 3
  selector: {matchLabels: {app: mr}}
  template:
    metadata: {labels: {app: mr}, annotations: {$(buffering_annotations mr | sed 's/^ *//' | paste -sd, -)}}
    spec:
      runtimeClassName: runc-architect
      containers: [{name: mr, image: redis:7-alpine, args: ["--save",""], ports: [{containerPort: 6379}]}]
---
apiVersion: v1
kind: Service
metadata: {name: mr, annotations: {architect.loopholelabs.io/shadow-service: "true"}}
spec: {type: ClusterIP, selector: {app: mr}, ports: [{port: 6379, targetPort: 6379}]}
EOF
  kn wait --for=condition=Ready pod -l app=mr --timeout=180s >/dev/null 2>&1
  V=$(kn get pod -l app=mr -o jsonpath='{.items[0].metadata.name}'); VN=$(kn get pod -l app=mr -o jsonpath='{.items[0].spec.nodeName}')
  kc cordon $VN >/dev/null 2>&1; kn delete pod $V --wait=false >/dev/null 2>&1; sleep 30; kc uncordon $VN >/dev/null 2>&1
  log "endpoints=$(kn get endpoints mr-shadow -o jsonpath='{.subsets[*].addresses[*].ip}' 2>/dev/null | wc -w) (expect 3)  running=$(kn get pods -l app=mr --no-headers 2>/dev/null | grep -c Running)/3"
  kn delete deploy,svc mr --force --grace-period=0 >/dev/null 2>&1
  ;;

scaletozero)
  log "### Scale-to-zero (hibernate) -> wake. EXPECT: hibernate works; wake trigger is the open question."
  kn delete deploy,svc,pod swk swk-w --force --grace-period=0 >/dev/null 2>&1; sleep 2
  cat <<EOF | kn apply -f - >/dev/null 2>&1
apiVersion: apps/v1
kind: Deployment
metadata: {name: swk, labels: {app: swk}}
spec:
  replicas: 1
  selector: {matchLabels: {app: swk}}
  template:
    metadata:
      labels: {app: swk}
      annotations:
        architect.loopholelabs.io/managed-containers: '["swk"]'
        architect.loopholelabs.io/shadow-service-pod: "true"
        architect.loopholelabs.io/postmigration-autoscaleup-containers: '["swk"]'
        architect.loopholelabs.io/rewrite-established-addresses-containers: '["swk"]'
        architect.loopholelabs.io/scaledown-durations: '{"swk":"20s"}'
        architect.loopholelabs.io/initial-scaledown-delays: '{"swk":"10s"}'
        architect.loopholelabs.io/network-monitor: "connections"
    spec:
      runtimeClassName: runc-architect
      containers: [{name: swk, image: redis:7-alpine, args: ["--enable-debug-command","yes","--save",""], ports: [{containerPort: 6379}]}]
---
apiVersion: v1
kind: Service
metadata: {name: swk, annotations: {architect.loopholelabs.io/shadow-service: "true"}}
spec: {type: ClusterIP, selector: {app: swk}, ports: [{port: 6379, targetPort: 6379}]}
EOF
  kn wait --for=condition=Ready pod -l app=swk --timeout=150s >/dev/null 2>&1 || { log "swk NOT READY"; exit 1; }
  ensure_writer swk-w; POD=$(kn get pod -l app=swk -o jsonpath='{.items[0].metadata.name}'); PIP=$(kn get pod -l app=swk -o jsonpath='{.items[0].status.podIP}')
  kn exec swk-w -- redis-cli -h swk-shadow -p 6379 SET hib survived >/dev/null 2>&1
  SD=no; for i in $(seq 1 15); do sleep 8; [ "$(kn get pod $POD -o jsonpath='{.metadata.labels.status\.architect\.loopholelabs\.io/swk}' 2>/dev/null)" = SCALED_DOWN ] && { SD=yes; break; }; done
  log "hibernated=$SD"
  W=""; for i in $(seq 1 15); do G=$(kn exec swk-w -- redis-cli -h swk -p 6379 -t 6 GET hib 2>/dev/null|tr -d '\r'); GD=$(kn exec swk-w -- redis-cli -h $PIP -p 6379 -t 6 GET hib 2>/dev/null|tr -d '\r'); [ -n "$G" ] && { W=$G; break; }; [ -n "$GD" ] && { W=$GD; break; }; sleep 5; done
  log "woke_via_activity=${W:-NO(stayed $(kn get pod $POD -o jsonpath='{.metadata.labels.status\.architect\.loopholelabs\.io/swk}' 2>/dev/null))}"
  kn delete deploy,svc,pod swk swk-w --force --grace-period=0 >/dev/null 2>&1
  ;;
*) echo "usage: workload-shapes.sh statefulset|pvc|multireplica|scaletozero"; exit 1;;
esac
