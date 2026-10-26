---
name: x86-root-vm
description: >-
  Run root-level x86_64 Linux work on the `ssh van-0` box in a throwaway VM —
  gVisor/runsc checkpoint-restore, netstack (`--network=sandbox`) testing, anything
  needing real root, a second kernel, or an amd64 userspace the arm64 dev machines
  cannot provide. Manages thin per-worktree VMs (`vmctl`) that boot in ~17s from a
  provisioned golden image, keep parallel worktrees from colliding on global kernel
  state, and leave the host free of dev toolchains. Use when asked to test under
  runsc/gVisor, reproduce something on x86_64, get root for kernel/ptrace/netns
  work, spin up or stop a VM on van-0, or when a finding needs confirming on
  amd64 because arm64 cannot run it.
---

# Root x86_64 work in a throwaway VM

The dev machines are **arm64**, and gVisor cannot checkpoint/restore there at all: its
arm64 sentry serves only `NT_PRSTATUS` from `PtraceGetRegSet`, so cruise's `getRegs`
dies at the first task reading `NT_ARM_TLS` (TPIDR_EL0) and no images get written.
Anything gVisor-related has to run on x86_64.

`ssh van-0` is that x86_64 box: Fedora 43 Server on an AMD EPYC 7643, 16 vCPU, 31 GB RAM,
login shell bash, passwordless sudo, `/dev/kvm` at `0666` and `kvm_amd nested=1`.

- **Keep dev toolchains off the host.** No Go, no compilers, no 700-package installs.
  Installing a *VM package* is fine; everything else lives inside a VM, so the host
  stays reproducible and cruise's global kernel state stays per-VM.
- **Nothing autostarts.** No systemd unit, no linger. Stop your machine by name when
  done (see Leaving the box).
- **`/` is only 15 GB** (`fedora-root`), with ~83 GB of the `fedora` VG unallocated. A
  golden base plus a few working overlays outgrow that, so grow the root LV before the
  first base (`sudo lvextend -r -L +60G fedora/root`) rather than finding out mid-run.

And rootless runsc **refuses `--network=sandbox`** ("sandbox network isn't supported
with --rootless"), so netstack — the mode LiveKit actually runs — can only be tested
with root, i.e. in a VM.

## Using it

`vmctl` lives at `~/gvisor-testenv/vm/vmctl` on van-0. Drive it as
`ssh van-0 "bash -s" <<'EOF' … EOF`, which keeps multi-line scripts free of a second
layer of quoting.

    vmctl create <name> [--cpus N] [--mem G] [--disk G]   thin overlay on the golden base
    vmctl start|stop <name>                               stop = ACPI powerdown via QMP
    vmctl stop-all [--yes]                                human's clear-the-box sweep, NOT
                                                          an agent tidy-up — see Leaving the box
    vmctl ssh <name> [cmd...]
    vmctl list
    vmctl destroy <name>
    vmctl golden <name> [label]                           promote a provisioned VM to base
    vmctl bases

If `vmctl` is missing on the box, deploy this skill's copy to
`~/gvisor-testenv/vm/vmctl`, put the authorised keys in
`~/gvisor-testenv/vm/authorized_key` (**one per line — both van-0's own key and the
dev box's**, see Gotchas), drop a base Debian cloud image beside it, and write its
filename into `~/gvisor-testenv/vm/CURRENT_BASE`. Host packages needed:
`sudo dnf install -y qemu-system-x86-core qemu-img xorriso` (no toolchains). van-0 has
no SSH key of its own yet, so `ssh-keygen -t ed25519 -N '' -f ~/.ssh/id_ed25519` there
first and add its `.pub` to `authorized_key`.

### One VM per worktree

Do not share one VM across parallel worktrees. cruise's work is **global kernel
state** — `ns_last_pid`, `shm_next_id` priming, SysV segment ids, iptables rules,
ptrace scope — so two runs in one machine collide on exactly the things under test.
A VM per worktree is ~600 KB (qcow2 overlay) and boots in ~17 s (first boot on van-0, cloud-init included), so there is no reason
to share.

    vmctl create wt-arch1316 && vmctl start wt-arch1316

### Getting binaries in

There is deliberately **no Go or Zig toolchain** on van-0 or in the VM's default
provisioning beyond gcc. Cross-compile on the dev box and copy in:

    zig build -Dtarget=x86_64-linux -Doptimize=ReleaseSafe --prefix <out>   # cruise
    zig cc -target x86_64-linux-musl -static -O2 -o fixture fixture.c       # C fixtures

then hop the two SSH legs (the VM's port is only bound on van-0's loopback):

    scp -q <files> van-0:/tmp/
    ssh van-0 "bash -s" <<'EOF'
    V=~/gvisor-testenv/vm
    P=$(sed -n 's/^PORT=//p' "$V/machines/<name>/vm.conf")
    scp -q -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -P "$P" \
      /tmp/<files> alex@127.0.0.1:/tmp/
    EOF

### Running cruise's real test suites in the VM

The whole Go suite runs here. It is not a toolchain problem, it is a path problem, and the recipe
below is the one that works. Do this rather than hand-rolling probes: a probe answers a mechanism
question, a suite answers whether the change is good.

Cross-compile on the dev box, build the C fixtures **in the VM** (a musl cross-build makes `raise()`
look broken after a restore, see the memory note), then mirror the source path:

    # dev box
    cd cruise/zig && zig build -Dtarget=x86_64-linux -Doptimize=ReleaseSafe --prefix /tmp/cruise-x86
    cd cruise/go  && GOOS=linux GOARCH=amd64 go test -c ./tests/ -o /tmp/tests.test
    tar czf /tmp/src.tgz cruise/example-programs cruise/mise-tasks cruise/mise.toml \
        cruise/zig cruise/scripts cruise/kernel-configs cruise/workloads

`projectRoot()` is `runtime.Caller(0)`, so the test binary hardcodes the **dev box's** source path.
Recreate it exactly in the VM and unpack there, then:

    R=<the dev box's absolute worktree path>      # must match, character for character
    mkdir -p $R && cd $R && tar xzf /tmp/src.tgz
    mkdir -p $R/cruise/dist/{example-programs,cruise}
    cp /tmp/cruise /tmp/ptsup $R/cruise/dist/cruise/
    for d in $R/cruise/example-programs/*/; do n=$(basename $d)
      make -C "$d" -s OUT="$R/cruise/dist/example-programs/$n" 2>/dev/null; done
    sudo -E CRUISE_BIN=$R/cruise/dist/cruise/cruise /tmp/tests.test -test.v \
        -test.run 'TestCR/^cruise$'

`CRUISE_BIN` and `PTSUP_BIN` are honoured, which is what saves you from `mise`. The Go/Java/Node
fixtures will not build without those toolchains and simply skip.

**Container rows** (`TestRuncCR`, `TestRuncStartup`, `TestCrossRuntimeCR`) additionally want
`PATH=/opt/runsc:$PATH` and `CRUISE_OVERLAY_ROOT=/var/tmp/overlay`.

### Images and credentials, before you call a row unrunnable

Most `TestRuncCR` failures in a fresh VM are image pulls, not regressions. Read the error: `denied`
is auth, `manifest unknown` means the image is monorepo-built and never published.

    gh auth token | sudo docker login ghcr.io -u <user> --password-stdin   # scopes: read:packages
    bash mise-tasks/workload-image <cell>        # builds it locally from workloads/

`workload-image` keys its cache on git content, so the mirrored tree needs a repo or it dies with
`fatal: not a git repository`: `git init -q && git add -A cruise/workloads && git commit -qm x`.
LiveKit rows want `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, which live in
`~/livekit.env` on the dev box. Stream it in without landing it on van-0's disk:

    cat ~/livekit.env | ssh van-0 "ssh -p <port> alex@127.0.0.1 'umask 077; cat > ~/livekit.env'"

### Cross-kernel work (`vmtest-cr-cross`) nests fine

`/dev/kvm` is present, so vmtest boots guests inside the VM. Four things bite, in order:

1. `/dev/kvm` is `root:kvm 0660` and the VM user is in neither: `sudo chmod 666 /dev/kvm`.
2. vmtest 9p-mounts the VM's rootfs as the guest root and spawns `qemu-ga` from it, so
   `sudo apt-get install qemu-guest-agent` or the guest panics on init.
3. Build the kernels with the repo's own recipe rather than by hand. Cross-compile
   `go build ./cmd/get-kernel`, ship it, and run it; it builds in Docker and caches under
   `/root/.cache/cruise/kernels/<version>/<hash>/bzImage`. Two kernels is roughly 20 minutes.
4. `mise-tasks/vmtest-cr-cross` shells out to `mise` only to pre-warm builds you have already
   staged, so a `#!/bin/bash\nexit 0` stub at `/usr/local/bin/mise` is faithful. Drive it with
   `usage_dump_kernel=`, `usage_restore_kernel=` and `usage_programs=` set as env vars and a bzImage
   path for each kernel (`resolve_kernel` takes a path directly).

Its validator counts `[tick] N PASS` lines, so a fixture that emits anything else reports
`pre-ticks=0` and reads as a failure when the C/R actually worked. To probe something the tick
programs do not report, write a small program that prints in tick format and drop it into
`dist/example-programs/`.

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

`/tmp` in the VM is a **7.9 GB tmpfs, and `nodev`**. Two separate traps. An OCI bundle with device
nodes in its rootfs fails there with `error reopening /dev/null: permission denied`, so put bundles
under `/var/tmp`. And the startup suite extracts rootfs and writes checkpoint snapshots into
`TMPDIR`, where a single row can want 4 GB (TigerBeetle's is 4201.6 MiB), so run it with
`TMPDIR=/var/tmp/tt` against the 50 GB disk. Without that, rows fail as `cruise embed: NoSpaceLeft`
and the neighbouring rows fail in less obvious ways, which reads exactly like a regression.

**A/B any failure against `origin/main` before you believe it.** Build the control the same way
(`git archive origin/main cruise/zig`, then copy `src/proto/gen` in from the working tree since it
is generated and gitignored) and run the failing rows with `CRUISE_BIN` pointed at each binary in
turn. On this rig five `TestRuncStartup` rows fail identically on both arms; without the control
they look like the branch's doing.


Each of these cost real time once.

- **An overlay must never be smaller than its backing file.** `qemu-img` allows it and
  the result is a truncated GPT — the VM drops to an initramfs shell with
  `PARTUUID=… does not exist`. `vmctl create` clamps the size up to the base's.
- **The cloud-init seed needs one YAML list item per SSH key.** A multi-line
  `$(cat authorized_key)` puts the second key at column 0, silently invalidating the
  whole `users:` block. The only symptom is `Permission denied (publickey)` — cloud-init
  reports success.
- **`vmctl ssh` runs on van-0**, so van-0's own key must be authorised too, not
  just the dev box's. Authorising only the dev box's key looks identical to the bug
  above.
- **Debian 13 splits docker**: `docker.io` is the daemon, `docker-cli` the client.
  Installing only `docker.io` leaves no `docker` binary. (That is the guest; the
  host is Fedora and never gets docker.)
- **`vmctl ssh <vm> <cmd>` reads stdin**, so inside a `ssh van-0 "bash -s" <<'EOF'` heredoc
  it swallows every line after it and the rest of the script silently never runs. Give
  it `< /dev/null` there (it cannot take `-n` itself: `vmctl ssh <vm> "bash -s" < script`
  needs stdin). A plain `ssh -p <port> alex@127.0.0.1 …` hop inside the same heredoc does
  the same thing, so give it `-n` (and `scp` a `< /dev/null`). The only symptom is a
  script that stops after that line with exit 0 and no error.
- **Detect a long job's end with a marker file, never `pgrep -f`.** Over ssh,
  `pgrep -f tests.test` matches the ssh command line that carries the same string, so a
  wait loop sees the job as running forever. That once hid a passing run for about an
  hour. Wrap the job as `nohup bash -c "<cmd> > log 2>&1; echo \$? > log.done" &` and poll
  for `log.done`, which also hands you the exit code.
- **`sudo env PATH=$PATH` carries the guest user's PATH, which has no `/usr/sbin`** on
  Debian. Tests that look up `iptables` or `ip` then fail with "no `iptables` binary on
  PATH", which reads like a missing package. Pass `PATH=/usr/local/bin:/usr/sbin:/sbin:$PATH`.
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
clear-the-box command, not an agent's cleanup step.

Likewise `vmctl destroy` refuses a running machine without `--force`, for the same
reason: on a shared box a destroy is very often aimed at someone else's work.

Before finishing, check you left nothing of *yours* running:

    vmctl list

A VM is cheap to restart, so erring toward stopping your own is right — but note the
guest's `/tmp` does not survive a restart, so stage fixtures somewhere under `~` if a
restart would cost you setup.
