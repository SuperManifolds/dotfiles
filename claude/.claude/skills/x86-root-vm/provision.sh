#!/usr/bin/env bash
# Provision a fresh VM into a reusable golden image: the toolchains that must not
# touch the host go here instead. Idempotent — safe to re-run on an existing machine.
#
#   usage: provision.sh [runsc-release]
#   run it INSIDE the VM (vmctl ssh <name> "bash -s" < provision.sh), then:
#     vmctl stop <name> && vmctl golden <name> <label>
#
# The runsc release should match RUNSC_RELEASE in cruise/mise.toml so the sandbox
# under test is the pinned one.
set -euo pipefail
RUNSC_REL="${1:-20260727.0}"
export DEBIAN_FRONTEND=noninteractive

sudo apt-get update -qq
# No -recommends: this image should stay small enough to flatten quickly.
sudo apt-get install -y -qq --no-install-recommends \
  ca-certificates curl git jq xz-utils file procps \
  iproute2 iptables uidmap dbus-user-session \
  build-essential pkg-config \
  redis-tools >/dev/null
# redis-tools is not optional: the valkey workload's prerequisite check runs when the
# TestRuncCR table is built, so a missing redis-cli skips the ENTIRE runc suite even
# when filtered to another workload.

# Debian 13 splits docker: docker.io is the daemon, docker-cli the client. Installing
# only the former leaves you with no `docker` binary and a confusing "command not found".
sudo apt-get install -y -qq --no-install-recommends docker.io docker-cli runc >/dev/null
sudo usermod -aG docker "$USER"
sudo systemctl enable --now docker >/dev/null 2>&1 || true

if ! runsc --version 2>/dev/null | grep -q "$RUNSC_REL"; then
  curl -fsSL -o /tmp/runsc \
    "https://storage.googleapis.com/gvisor/releases/release/${RUNSC_REL}/x86_64/runsc"
  sudo install -m 0755 /tmp/runsc /usr/local/bin/runsc
  rm -f /tmp/runsc
fi
# Registers runsc as a docker runtime, which is how you get netstack with real
# veth/NAT networking without hand-rolling a netns.
sudo runsc install >/dev/null 2>&1 || true
sudo systemctl restart docker; sleep 3

# Shrink what the golden image has to carry.
sudo apt-get clean
sudo journalctl --vacuum-time=1s >/dev/null 2>&1 || true

echo "provisioned:"
echo "  $(uname -srm)"
echo "  runsc  $(runsc --version | head -1 | awk '{print $3}')"
echo "  docker $(docker --version | awk '{print $3}' | tr -d ,) (runtime registered: $(sudo docker info --format '{{if .Runtimes.runsc}}yes{{else}}no{{end}}' 2>/dev/null))"
echo "  gcc    $(gcc -dumpversion)"
