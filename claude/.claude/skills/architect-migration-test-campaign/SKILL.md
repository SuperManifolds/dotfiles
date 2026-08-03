---
name: architect-migration-test-campaign
description: >-
  Reproduce the Loophole Labs "Architect for Kubernetes" network live-migration
  test campaign on an EKS cluster end-to-end: install Architect (live-migration
  buffering) from the customer helm flow, run the real-world workload migration
  matrix + cluster-config sweep, characterize CRIU failure classes, run the
  deep-dive tests (N-hop repeated-migration stress, downtime curve, StatefulSet /
  PVC / multi-replica / scale-to-zero, lazy-pages, Cilium), and build the
  interactive HTML report. Use when asked to test/validate Architect network live
  migration on EKS, "reproduce the migration campaign", "re-run the migration
  test suite", or characterize where migration breaks and why.
---

# Architect network live-migration test campaign (EKS)

A reproducible runbook for exercising Architect's **network live migration**
(live-migration buffering) on an EKS cluster across a broad workload × config
matrix, characterizing failures, and producing a report. This is the *how*; the
bundled `scripts/` are the mechanical parts. Read the whole file before starting.

## What live migration is (so the tests make sense)

Architect checkpoint/restores a running pod onto another node while holding its
in-flight TCP connections open. The `architect-router` (XDP/eBPF on `eth0`,
DaemonSet, one per node) **buffers** packets to the departing pod's IP during the
CRIU checkpoint, then replays them after restore. Clients must connect through a
**shadow Service** (`<svc>-shadow`, empty selector, endpoints = router pod:shadowPort)
— the front Service bypasses buffering. Per-pod annotations opt each container in.

Key mechanic verified this campaign: on migration A→B an **established** connection
stays pinned to its original router, which re-points its DNAT to the pod's new node
— it is NOT a router-to-router failover; the connection is preserved end-to-end by
CRIU (`rewrite-established-addresses`).

## Prerequisites

- An EKS cluster you can throw away (this campaign cordons nodes, swaps CNIs, and
  recycles instances). `kubectl`, `helm`, `aws` CLIs configured; `KUBECONFIG` pointing
  at it. Set `export CTX=<kube-context>` and `export REGION=<aws-region>` and
  `export CLUSTER=<eks-cluster-name>`.
- A machine token + access to the preview control plane (`api.preview.architect.io`).
- Nodes: AL2023, kernel ≥6.6 recommended (buffering needs 5.18+; lazy-pages needs
  userfaultfd). At least **2 worker nodes labeled `architect.loopholelabs.io/node=true`**
  + 1 `critical-node=true`. For the big-RSS downtime curve you need bigger nodes
  (see `scripts/bignodes.sh`).
- **Use a `main` build, not the pinned `arch-862` tutorial build** — arch-862
  predates several features (see Findings). `scripts/install-architect.sh` discovers
  the latest `main` chart+image automatically.

All scripts read `KUBECONFIG`, `CTX` (defaults to current-context), `NS` (default
`default`), `REGION`, `CLUSTER` from the environment and source `scripts/lib.sh`.

## Hard-won operational gotchas (read first — these cost hours)

1. **Clients must use `<svc>-shadow`, not the front service.** The front service
   bypasses buffering; `port-forward` bypasses the proxy entirely.
2. **`architectRouterGenericXDP=true` is mandatory on AWS ENA.** Native XDP can't TX
   the shadow return path on the ENA driver (`response_packets:0`, every conn hangs).
   It's the chart default on `main`; the arch-862 tutorial ships it `false`.
3. **Always uncordon after a migration.** If a script is killed mid-migration the
   uncordon never runs and the node stays `SchedulingDisabled`, which silently breaks
   later scheduling. `scripts/uncordon-all.sh` recovers.
4. **BOTH node instance roles need `AmazonEKS_CNI_Policy`.** The `architect-workers`
   AND `architect-critical` nodegroups use *different* IAM roles. After any
   vpc-cni addon recreate (which resets aws-node's IRSA), aws-node falls back to the
   node role — if either role lacks the CNI policy, that node's aws-node hangs at
   "Checking for IPAM connectivity" → NotReady → control-plane unschedulable.
5. **`efs-csi-controller` (2×600m CPU) can starve the router DaemonSet rollout** on
   small 2-core nodes → router Pending. Scale it to 1: `kubectl scale deploy efs-csi-controller -n kube-system --replicas=1`.
6. **The router container has `curl`, not `wget`.** Istio 1.31 injects its sidecar as
   a native initContainer.
7. **Big-RSS migrations take minutes** (8 GB dump ≈ 117 s). Size your timeouts.
8. **`DEBUG POPULATE` data is highly compressible**, so the `tar.zst` transfer is
   best-case; the CRIU freeze/dump portion (∝ physical RSS) is realistic.

## Phase 0 — Install Architect (customer helm flow, main build)

```bash
export KUBECONFIG=... CTX=... REGION=eu-west-2 CLUSTER=<name>
export MACHINE_TOKEN=mk_... CLUSTER_NAME=<consoleName>
bash scripts/install-architect.sh          # discovers latest main build, helm upgrade --install
```
This installs with `features.liveMigrationBuffering=true`, `architectShadowServiceEnabled=true`,
`architectRouterGenericXDP=true`, `architectRouterPassthroughPorts=8080;8081`, against
`api.preview.architect.io`. Verify: 6/6 architect pods Running (control-plane,
admission-controller, 2× router, 2× architectd), cluster shows Connected in the console.
If the router is Pending, apply gotcha #5.

## Phase 1 — Baseline workload migration matrix

`scripts/run-migration.sh <name> <image> <port> <tcp|http|redis> ['<extra container yaml>']`
deploys a runc-architect workload with the buffering annotations + a ClusterIP shadow
Service, holds a persistent connection through `<name>-shadow`, cordons+deletes to
migrate, and prints `reg=? moved=? nms=? ok/err => PASS/PARTIAL/FAIL`.

```bash
bash scripts/run-migration.sh redis redis:7-alpine 6379 redis 'args: ["--enable-debug-command","yes"]'
bash scripts/run-migration.sh pg postgres:16-alpine 5432 tcp 'env: [{name: POSTGRES_HOST_AUTH_METHOD, value: trust}]'
bash scripts/run-migration.sh ngx nginx:alpine 80 http
# … iterate the matrix (see scripts/matrix.txt for the full 28-workload list)
```
Expected: ~26 of 28 real-world workloads PASS (connection preserved, 0 resets).
Known non-pass: Envoy (listeners don't restore), Node.js+io_uring (CRIU can't dump).

## Phase 2 — Cluster-config sweep

Re-run a representative subset (redis, postgres, nginx) under each config. CNI-agnostic
configs pass; Cilium breaks the datapath.
- NetworkPolicy default-deny (allow router path), Kong ingress in front, Istio sidecar,
  kube-proxy IPVS, kube-proxy nftables → all PASS.
- Cilium is the gated/destructive one → `scripts/cilium.sh` (see Phase 5).

## Phase 3 — CRIU failure classes

`scripts/characterize.sh <name> <image> <port> [env]` migrates and classifies the
restored process as RESTORED vs FRESH. Deliberately-failing targets:
- io_uring (Node.js `UV_USE_IO_URING=1`) → `anon_inode:[io_uring]`, FRESH.
- inotify (ASP.NET) → `fsnotify.c:314`. ptrace (strace child) → `seize.c:335`.
These are **stock-CRIU/kernel limits on the runc path** — the cruise-engine C/R work
does NOT apply unless the pod opts into `ARCHITECT_CHECKPOINT_ENGINE=cruise`.

## Phase 4 — Deep-dive tests

```bash
# F-3: repeated migration (does data loss compound? — it's intermittent ~50%)
bash scripts/nhop-stress.sh nhop 10 200000

# Downtime curve (needs bigger nodes; provision them first)
bash scripts/bignodes.sh create           # r6a.large x2, ~5-10 min
bash scripts/downtime-curve.sh             # 108MB→8GB, dump window + e2e stall

# Workload shapes & lifecycle
bash scripts/workload-shapes.sh statefulset   # EXPECT: CrashLoopBackOff (see Findings)
bash scripts/workload-shapes.sh pvc            # Deployment+EBS PVC, within-AZ
bash scripts/workload-shapes.sh multireplica   # 3 replicas, migrate one
bash scripts/workload-shapes.sh scaletozero    # hibernate + wake

# Lazy-pages / post-copy
bash scripts/lazy-pages.sh
```
See each script's header for what it asserts. The downtime curve needs 2 nodes in the
SAME AZ for the PVC test (EBS is AZ-bound); `workload-shapes.sh pvc` pins to one AZ.

## Phase 5 — Cilium (gated, destructive, last)

`scripts/cilium.sh <overlay|eni|chaining> install|test|rollback`. This swaps the whole
CNI and recycles nodes. **overlay** is the reliably-reproducible F-2 test. **eni** needs
the node-role CNI policy (gotcha #4) and correct egress masquerade or Architect's shim
pull fails. Always `scripts/cilium.sh <mode> rollback` after (restores VPC CNI + recycles).

## Phase 6 — Build the report

Findings are logged to `$CAMP/retest_findings.txt` as you go (every script `tee`s to it).
To build the report, have Claude generate a fresh interactive HTML dashboard from
`$CAMP/retest_findings.txt` — that's what produced the campaign's `claude.ai/code/artifact`
dashboard. **Load the `artifact-design` skill first**, then publish via the Artifact tool.
Sections that worked well: exec TL;DR, headline findings cards, environment-readiness
matrix, downtime curve, workload matrix + shapes table, config sweep, CRIU failure classes,
recommendations, impact×effort quadrant, raw evidence, glossary.

## Expected findings (what a clean run should reproduce, on a `main` build)

| Finding | Result | Ticket |
|---|---|---|
| Generic XDP required on ENA | Chart defaults `true` on main (was the F-1 dead-feature on arch-862) | ARCH-1248 (fixed) |
| **Cilium incompatible** | eBPF datapath bypasses the router XDP hook → shadow refused (overlay-confirmed) | ARCH-1249 |
| **Repeated-migration data loss** | Intermittent **~50%** (NOT the 2nd hop); `criu failed: type RESTORE errno 0` → silent fresh start | ARCH-1250 |
| Envoy listeners | Don't survive CRIU restore (restored container stopped) | candidate |
| **StatefulSet** | CrashLoopBackOff — daemon requires the Deployment-only `pod-template-hash` label | candidate |
| Deployment + EBS PVC | Works within-AZ (state + PVC preserved; ~15s Multi-Attach); cross-AZ impossible | — |
| Multi-replica | Works (migrate one, others undisturbed) | — |
| Scale-to-zero → wake | Hibernate works; wake-on-activity didn't trigger (needs investigation) | candidate |
| Downtime | Freeze+dump ∝ RSS, super-linear: 108MB=4s·1GB=7s·8GB=117s (r6a.large) | — |
| Lazy-pages | Works on main (source page-server, faults over userfaultfd, container up ~2s); does NOT preserve the connection (skips the buffering hook) | — |
| **Migration trigger** (`kubectl drain` / Eviction API) | **WORKS** — migrates with state preserved → Karpenter/CA/spot drains trigger migration (`drain-trigger.sh`) | — |
| **Istio ambient / ztunnel** | INCOMPATIBLE — shadow path reset; node capture + HBONE breaks the XDP datapath ("second Cilium"). Sidecar mode is fine. | candidate |
| **DB operators (CNPG/Strimzi)** | BLOCKED — no `pod-template-hash` + CRDs expose no `runtimeClassName` → whole operator-managed stateful ecosystem out | candidate |
| Off-cluster egress | Buffering is ingress-only — a managed pod's egress conn to a non-buffered peer resets on migration | — |
| Memory QoS near-limit | No OOM at ~74% of the limit (edge >90% not probed) | — |

## Expanded roadmap validation

See **`VALIDATION-ROADMAP.md`** for the full research-driven roadmap (common CNIs, cluster configs, ecosystem tools,
app shapes) filtered to CRIU-migratable candidates, with per-item verdicts marked TESTED / REASONED / BLOCKED and the two
datapath rules (proxy-pod survives; node-eBPF/encapsulation breaks). New reusable test: `scripts/drain-trigger.sh` (the
Eviction-API trigger — the proxy for Karpenter/CA/spot). Excluded by design (won't work with our CRIU): gVisor, Kata,
GPU/CUDA, IPv6, io_uring-default runtimes, SO_REUSEPORT multi-listener, hugepages, inotify tailers.

## Cleanup (leave the cluster healthy)

```bash
bash scripts/uncordon-all.sh
bash scripts/bignodes.sh delete            # remove the temporary big nodegroup
bash scripts/cilium.sh <mode> rollback     # if any Cilium mode was installed
kubectl --context "$CTX" -n default delete deploy,statefulset,svc,pod,pvc -l 'app' # test workloads
```
Verify: VPC CNI aws-node ready on all nodes, architect 6/6, a smoke migration passes.
```

The definitive per-test details, exact log-line signatures, and the datapath mechanics
live in the campaign memory `project_migration_testing_campaign` — read it for context.
```
