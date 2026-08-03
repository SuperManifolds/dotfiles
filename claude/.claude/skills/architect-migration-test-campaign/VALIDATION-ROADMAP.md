# Validation roadmap — expanded coverage (results)

Scope filter (user-directed): **only things theoretically migratable with our runc/CRIU path.**
Excluded by design (won't work with our CRIU — don't spend validation effort): gVisor & Kata,
GPU/CUDA (no CUDA C/R), IPv6/dual-stack, io_uring-default runtimes (Node 22.12+, TigerBeetle,
ScyllaDB, PG18-`io_method=io_uring`), SO_REUSEPORT multi-listener (Envoy-class), hugepages,
inotify/fanotify log tailers, multi-GPU/NCCL.

Two rules (empirical anchors) drive every verdict:
- **Proxy-*pod* in the path survives** (Kong ✅, Istio sidecar ✅) — just another pod holding a TCP conn to the workload IP.
- **Node-level eBPF datapath or encapsulation loses** (Cilium overlay ❌, Istio ambient ❌) — an overlay/HBONE/ciphertext hides the pod IP from the router's `eth0` XDP hook. The discriminator is **encapsulation / node-datapath capture, not eBPF-vs-iptables** (XDP-ingress runs before tc-eBPF, so a tc-eBPF CNI with *native routing* should coexist).

Evidence markers: **TESTED** (ran on the EKS cluster) · **REASONED** (corollary of a tested anchor) · **BLOCKED** (needs infra not available).

## P0
| Item | Verdict | Evidence |
|---|---|---|
| **Migration trigger — `kubectl drain` / Eviction API** (Karpenter consolidation, Cluster Autoscaler, spot drain) | **WORKS** — migrated with state preserved on a drain → Architect hooks graceful eviction, not just delete. Caveat: spot's 2-min notice vs downtime∝RSS; trigger on rebalance-recommendation. | TESTED |
| **CNI encapsulation reframe** | **MIXED** — Cilium overlay = bypass (confirmed); ENI-native untestable on EKS (pod egress broke Architect's install, 2×). Analysis: encapsulation (not eBPF) is the discriminator → native-routing eBPF CNIs likely work. | TESTED+ANALYSIS |
| **DB operators / StatefulSet** | **BLOCKED** — CloudNativePG pods lack `pod-template-hash` and the CRD exposes no `runtimeClassName`; whole operator-managed stateful ecosystem out. | TESTED |

## P1
| Item | Verdict | Evidence |
|---|---|---|
| **Istio ambient / ztunnel** | **INCOMPATIBLE** — shadow path "connection reset" even pre-migration; ztunnel node capture + HBONE breaks the XDP datapath. "Second Cilium." (Sidecar still works.) | TESTED |
| **Memory QoS near-limit** | **PASS** — 515 MB in a 700 Mi limit (~74%) migrated, no OOM. (OOM edge >90% not probed.) | TESTED |
| **Connection-pool / broker scale** | **MIGRATES** with 300 held conns; FD→dump-time scaling not isolated (probe reset count is a stall/reconnect artifact). | TESTED |
| **KEDA HTTP add-on (wake)** | **LIKELY OK** — request-buffering interceptor is a proxy pod; probable fix for the scale-to-zero wake gap. | REASONED |
| **AWS NLB IP-target** | **NOT BUFFERED** — targets pod IP directly = bypasses the shadow Service (front-path rule) unless Architect adds NLB integration. | REASONED |
| **Gateway API** | **SPLIT** — Envoy Gateway/NGINX GF/Contour (proxy pods) work; Cilium Gateway (eBPF) fails. | REASONED |
| **Bottlerocket** | **UNTESTED** — needs a Bottlerocket nodegroup; immutable rootfs + module signing may block the shim/XDP install. | BLOCKED |
| **Large JVM heap / .NET** | **COVERED** — RSS-bound freeze, same super-linear downtime curve already measured. | DERIVED |

## P2
| Item | Verdict | Evidence |
|---|---|---|
| **Off-cluster egress peers** | **BOUNDARY** — managed pod's egress conn to a non-buffered peer reset once on migration (0→1). Buffering is ingress-only. | TESTED |
| **Linkerd (sidecar)** | **LIKELY OK** — proxy-pod sidecar, like the Istio sidecar. | REASONED |
| **Vault injector / secrets-store CSI** | **LIKELY OK** — multi-container CRIU; Istio initContainer sidecar already restored fine. | REASONED |
| **Kyverno / Gatekeeper** | **GATING RISK** — can strip the migration annotations / block the RuntimeClass; document the allow-list. | REASONED |
| **WireGuard / IPsec encryption** | **BYPASS** — ciphertext hides the pod IP; same class as overlay, independent of routing mode. | REASONED |
| **cgroup v1 / OS matrix** | **PARTIAL** — AL2023 + cgroup v2 + kernel 6.12 works; v1/other kernels need those node types. | BASELINE ONLY |

## Still open to close the roadmap
- A **working native-routing eBPF CNI** run (fix Cilium-ENI pod egress, or GKE Dataplane V2 off-EKS) to empirically confirm the encapsulation reframe.
- **KEDA** dedicated run to confirm it fixes the wake gap.
- **Bottlerocket** nodegroup for the immutable-OS install path.
- **NLB IP-target** with the AWS LB Controller.
