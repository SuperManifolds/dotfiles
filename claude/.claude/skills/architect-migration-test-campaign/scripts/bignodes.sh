#!/usr/bin/env bash
# Create/delete a temporary large nodegroup for the big-RSS downtime curve.
# Clones the architect-workers nodegroup's role+subnets with a bigger instance type.
# Usage: bignodes.sh create|delete   Env: KUBECONFIG CTX REGION CLUSTER [BIG_INSTANCE=r6a.large]
set -u
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"
: "${REGION:?export REGION}"; : "${CLUSTER:?export CLUSTER (eks cluster name)}"
BIG_INSTANCE="${BIG_INSTANCE:-r6a.large}"; NG=architect-bignodes
case "${1:-}" in
  create)
    cfg=$(aws eks describe-nodegroup --cluster-name "$CLUSTER" --region "$REGION" --nodegroup-name architect-workers \
      --query 'nodegroup.{role:nodeRole,subnets:subnets,ami:amiType}' --output json)
    role=$(echo "$cfg" | python3 -c "import json,sys;print(json.load(sys.stdin)['role'])")
    subs=$(echo "$cfg" | python3 -c "import json,sys;print(' '.join(json.load(sys.stdin)['subnets']))")
    ami=$(echo "$cfg" | python3 -c "import json,sys;print(json.load(sys.stdin)['ami'])")
    echo "creating $NG ($BIG_INSTANCE x2) role=$role"
    aws eks create-nodegroup --cluster-name "$CLUSTER" --region "$REGION" --nodegroup-name "$NG" \
      --node-role "$role" --subnets $subs --ami-type "$ami" --instance-types "$BIG_INSTANCE" --disk-size 60 \
      --scaling-config minSize=2,maxSize=2,desiredSize=2 \
      --labels architect.loopholelabs.io/node=true,bignode=true \
      --query 'nodegroup.status' --output text
    echo "waiting for ACTIVE (~5-10 min)..."
    for i in $(seq 1 60); do st=$(aws eks describe-nodegroup --cluster-name "$CLUSTER" --region "$REGION" --nodegroup-name "$NG" --query 'nodegroup.status' --output text 2>/dev/null); echo "[$((i*15))s] $st"; [ "$st" = ACTIVE ] && break; sleep 15; done
    echo "TIP: cordon the small workers so big-RSS pods land on the bignodes."
    ;;
  delete)
    aws eks delete-nodegroup --cluster-name "$CLUSTER" --region "$REGION" --nodegroup-name "$NG" --query 'nodegroup.status' --output text 2>&1 | tail -1
    ;;
  *) echo "usage: bignodes.sh create|delete"; exit 1;;
esac
