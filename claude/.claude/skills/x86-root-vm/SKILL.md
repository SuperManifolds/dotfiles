---
name: x86-root-vm
description: >-
  Run root-level x86_64 Linux work on the `ssh cachyos` box in a throwaway VM —
  gVisor/runsc checkpoint-restore, netstack (`--network=sandbox`) testing, anything
  needing real root, a second kernel, or an amd64 userspace the arm64 dev machines
  cannot provide. Manages thin per-worktree VMs (`vmctl`) that boot in ~8s from a
  provisioned golden image, keep parallel worktrees from colliding on global kernel
  state, and leave the host free of dev toolchains. Use when asked to test under
  runsc/gVisor, reproduce something on x86_64, get root for kernel/ptrace/netns
  work, spin up or stop a VM on cachyos, or when a finding needs confirming on
  amd64 because arm64 cannot run it.
---

# Root x86_64 work in a throwaway VM

The dev machines are **arm64**, and gVisor cannot checkpoint/restore there at all: its
arm64 sentry serves only `NT_PRSTATUS` from `PtraceGetRegSet`, so cruise's `getRegs`
dies at the first task reading `NT_ARM_TLS` (TPIDR_EL0) and no images get written.
Anything gVisor-related has to run on x86_64.

`ssh cachyos` is that x86_64 box — but it is Alex's **gaming PC**, so:

- **Never pollute the host with dev toolchains.** No Go, no compilers, no 700-package
  installs. Installing a *VM package* is fine; everything else lives inside a VM.
- **Nothing may run when Alex is not working.** No autostart, no systemd unit, no
  linger. Stop your machine by name when done (see Leaving the box).
- Historically this box was no-sudo (`~/gvisor-testenv`, see the memory note). That
  rule is now scoped to toolchains: sudo for VM management is expected.

And rootless runsc **refuses `--network=sandbox`** ("sandbox network isn't supported
with --rootless"), so netstack — the mode LiveKit actually runs — can only be tested
with root, i.e. in a VM.

## Using it

`vmctl` lives at `~/gvisor-testenv/vm/vmctl` on cachyos. The remote login shell is
**fish**, so always drive it as `ssh cachyos "bash -s" <<'EOF' … EOF`, never as a bare
compound command.

    vmctl create <name> [--cpus N] [--mem G] [--disk G]   thin overlay on the golden base
    vmctl start|stop <name>                               stop = ACPI powerdown via QMP
    vmctl stop-all [--yes]                                human's pre-gaming sweep, NOT
                                                          an agent tidy-up — see Leaving the box
    vmctl ssh <name> [cmd...]
    vmctl list
    vmctl destroy <name>
    vmctl golden <name> [label]                           promote a provisioned VM to base
    vmctl bases

If `vmctl` is missing on the box, deploy this skill's copy to
`~/gvisor-testenv/vm/vmctl`, put the authorised keys in
`~/gvisor-testenv/vm/authorized_key` (**one per line — both cachyos's own key and the
dev box's**, see Gotchas), drop a base cloud image beside it, and write its filename
into `~/gvisor-testenv/vm/CURRENT_BASE`. Host packages needed: `qemu-base` and
`xorriso` (24 MB, no toolchains).

### One VM per worktree

Do not share one VM across parallel worktrees. cruise's work is **global kernel
state** — `ns_last_pid`, `shm_next_id` priming, SysV segment ids, iptables rules,
ptrace scope — so two runs in one machine collide on exactly the things under test.
A VM per worktree is ~600 KB (qcow2 overlay) and boots in ~8 s, so there is no reason
to share.

    vmctl create wt-arch1316 && vmctl start wt-arch1316

### Getting binaries in

There is deliberately **no Go or Zig toolchain** on cachyos or in the VM's default
provisioning beyond gcc. Cross-compile on the dev box and copy in:

    zig build -Dtarget=x86_64-linux -Doptimize=ReleaseSafe --prefix <out>   # cruise
    zig cc -target x86_64-linux-musl -static -O2 -o fixture fixture.c       # C fixtures

then hop the two SSH legs (the VM's port is only bound on cachyos's loopback):

    scp -q <files> cachyos:/tmp/
    ssh cachyos "bash -s" <<'EOF'
    V=~/gvisor-testenv/vm
    P=$(sed -n 's/^PORT=//p' "$V/machines/<name>/vm.conf")
    scp -q -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -P "$P" \
      /tmp/<files> alex@127.0.0.1:/tmp/
    EOF

### Golden image

`base-provisioned-*.qcow2` already carries docker (+`docker-cli`), runsc pinned to
`RUNSC_RELEASE` from `cruise/mise.toml`, build-essential, git, iproute2/iptables — so
a new worktree VM is usable immediately rather than after a 15-minute apt run.

To refresh it: create a machine, run `provision.sh` inside it, stop it, promote it.

    vmctl create goldenbuild --cpus 6 --mem 12 --disk 80
    vmctl start goldenbuild
    vmctl ssh goldenbuild "bash -s" < provision.sh      # pass a runsc release to override
    vmctl stop goldenbuild
    vmctl golden goldenbuild $(date +%Y%m%d)

Bases are **never mutated in place**: live overlays record the backing path they were
built against, so promotion writes a new file and repoints `CURRENT_BASE`. Old bases
stay on disk for machines still pointing at them (`vmctl bases` to see them).

### Testing runsc network modes

The two modes behave differently and the difference has already produced one false
blocker, so be explicit about which one a finding applies to.

**netstack** (`--network=sandbox`) is the customer configuration. Needs root, and
needs the sandbox to have real connectivity — a bare netns has no route, so a dial
fails instantly (`st 07` TCP_CLOSE) instead of parking in SYN_SENT. Easiest correct
path is docker with runsc as the runtime, which sets up veth + NAT for you:

    sudo docker run -d --runtime=runsc --name t <image>
    sudo docker exec t <probe>

**hostinet** (`--network=host`) is what the CI bundle uses, because the test spec
shares the host netns so ready-checks reach the workload on localhost. It works
rootless.

## Gotchas

Each of these cost real time once.

- **An overlay must never be smaller than its backing file.** `qemu-img` allows it and
  the result is a truncated GPT — the VM drops to an initramfs shell with
  `PARTUUID=… does not exist`. `vmctl create` clamps the size up to the base's.
- **The cloud-init seed needs one YAML list item per SSH key.** A multi-line
  `$(cat authorized_key)` puts the second key at column 0, silently invalidating the
  whole `users:` block. The only symptom is `Permission denied (publickey)` — cloud-init
  reports success.
- **`vmctl ssh` runs on cachyos**, so cachyos's own key must be authorised too, not
  just the dev box's. Authorising only the dev box's key looks identical to the bug
  above.
- **Debian 13 splits docker**: `docker.io` is the daemon, `docker-cli` the client.
  Installing only `docker.io` leaves no `docker` binary.
- **The remote shell is fish.** Bare compound commands over `ssh cachyos` fail with
  "Unsupported use of '='".
- **`/dev/kvm` is already `0666`** on this box and `kvm_amd nested=1`, so no group
  changes are needed and KVM-inside-VM works if something ever wants it.
- A successful in-sandbox cruise dump **kills the sandbox's PID 1**, so `runsc exec`
  exits 137 either way. Judge by the images written, never the exit status.

## Leaving the box

**Stop the machine you started, by name:**

    vmctl stop wt-<yourworktree>

**Do not use `stop-all` to tidy up.** Several worktrees share this box, and `stop-all`
stops *theirs* too — that has already cost another session a test run mid-flight. It is
gated now (it refuses when more than one machine is running unless passed `--yes`), but
the habit is the fix: stop yours by name. `stop-all --yes` is the human's
"clear-the-box-before-gaming" command, not an agent's cleanup step.

Likewise `vmctl destroy` refuses a running machine without `--force`, for the same
reason: on a shared box a destroy is very often aimed at someone else's work.

Before finishing, check you left nothing of *yours* running:

    vmctl list

A VM is cheap to restart, so erring toward stopping your own is right — but note the
guest's `/tmp` does not survive a restart, so stage fixtures somewhere under `~` if a
restart would cost you setup.
