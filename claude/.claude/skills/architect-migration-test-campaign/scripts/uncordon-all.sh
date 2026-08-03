#!/usr/bin/env bash
# Recover from scripts killed mid-migration: uncordon every node.
set -u
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"
for n in $(kc get nodes -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}'); do
  kc uncordon "$n" 2>&1 | sed 's/^/  /'
done
echo "schedulable node=true workers:"
kc get nodes -l architect.loopholelabs.io/node=true -o jsonpath='{range .items[*]}{.metadata.name}{" unsched="}{.spec.unschedulable}{"\n"}{end}'
