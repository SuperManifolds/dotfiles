#!/usr/bin/env bash
# Install/upgrade Architect (live-migration buffering) via the customer helm flow, on a MAIN build.
# Env: KUBECONFIG CTX MACHINE_TOKEN CLUSTER_NAME (console name); optional VERSION (else auto-discover latest main).
set -u
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"
: "${MACHINE_TOKEN:?export MACHINE_TOKEN=mk_...}"
: "${CLUSTER_NAME:?export CLUSTER_NAME=<console cluster name>}"
API_URL="${API_URL:-https://api.preview.architect.io}"

discover(){
  # newest main build present in BOTH the chart and daemon repos on ghcr, matched to the
  # architect repo's main HEAD (falls back: newest main chart tag if HEAD has no build yet).
  local head; head=$(git ls-remote https://github.com/loopholelabs/architect refs/heads/main 2>/dev/null | cut -c1-8)
  python3 - "$head" <<'PY'
import urllib.request,json,sys,re
head=sys.argv[1] if len(sys.argv)>1 else ""
def tags(pkg):
    tok=json.load(urllib.request.urlopen(f"https://ghcr.io/token?scope=repository:loopholelabs/{pkg}:pull&service=ghcr.io"))['token']
    url=f"https://ghcr.io/v2/loopholelabs/{pkg}/tags/list?n=1000"; out=[]
    while url:
        r=urllib.request.urlopen(urllib.request.Request(url,headers={"Authorization":f"Bearer {tok}"}))
        out+=json.load(r).get('tags',[]); link=r.headers.get("Link")
        m=re.search(r'<([^>]+)>;\s*rel="next"',link) if link else None
        url=("https://ghcr.io"+m.group(1)) if m else None
    return {t.split('.')[-1].lstrip('g'):t for t in out if t.startswith('0.0.0-main')}
c=tags("architect-chart"); d=tags("architectd"); common=set(c)&set(d)
pick=None
if head:
    for s in common:
        if s.startswith(head) or head.startswith(s): pick=s; break
if not pick and common: pick=sorted(common)[-1]   # weak fallback
print(c[pick] if pick else "")
PY
}

VERSION="${VERSION:-$(discover)}"
[ -z "$VERSION" ] && { echo "Could not auto-discover a main build; set VERSION=0.0.0-main.1.g<sha>"; exit 1; }
echo "Installing Architect chart version: $VERSION"

helm upgrade architect oci://ghcr.io/loopholelabs/architect-chart \
  --kube-context "$CTX" --namespace architect --create-namespace --install \
  --set kubernetesDistro=eks \
  --set apiUrl="$API_URL" \
  --set machineToken="$MACHINE_TOKEN" \
  --set clusterName="$CLUSTER_NAME" \
  --set features.liveMigrationBuffering=true \
  --set architectShadowServiceEnabled=true \
  --set architectRouterGenericXDP=true \
  --set 'architectRouterPassthroughPorts=8080;8081' \
  --devel --version "$VERSION" --wait --timeout 8m 2>&1 | tail -8

echo "=== architect pods ==="
kc -n architect get pods -o wide 2>/dev/null | awk '{print $1,$2,$3}'
echo "If a router is Pending on a small node: kubectl scale deploy efs-csi-controller -n kube-system --replicas=1"
