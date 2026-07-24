#!/usr/bin/env bash
# PreToolUse(Bash) guard for the k8s-investigator subagent: allow read-only
# cluster/container commands, block anything that could mutate. Exit 2 blocks
# the tool call and returns the stderr message as the reason.
export LC_ALL="${LC_ALL:-en_US.UTF-8}" LANG="${LANG:-en_US.UTF-8}"

cmd=$(jq -r '.tool_input.command // empty' 2>/dev/null)
[ -n "$cmd" ] || exit 0

c=$(printf '%s' "$cmd" | tr '\n' ' ')

block() {
  echo "k8s-investigator is read-only: blocked a mutating command ($1)." >&2
  echo "Report the finding and give the command for the user to run manually." >&2
  exit 2
}

# [^|;&]* keeps each match within one pipeline segment (won't cross a pipe).
kubectl_mut='\bkubectl\b[^|;&]*\b(apply|delete|create|replace|patch|edit|scale|rollout|annotate|label|taint|drain|cordon|uncordon|set|exec|cp|run|expose|attach|port-forward|proxy)\b'
helm_mut='\bhelm\b[^|;&]*\b(install|upgrade|uninstall|delete|rollback)\b'
docker_mut='\bdocker\b[^|;&]*\b(run|rm|rmi|kill|stop|start|restart|pause|unpause|exec|create|build|commit|push|prune|update|rename|tag|load|import|volume|network|swarm|service|system)\b'
compose_mut='\bdocker\b[^|;&]*\bcompose\b[^|;&]*\b(up|down|restart|stop|start|rm|build|pull|create)\b'
shell_dangerous='(^|[|;&[:space:]])(rm[[:space:]]+-[a-z]*f|mkfs|dd[[:space:]]|shutdown|reboot|:\(\)\s*\{)'

echo "$c" | grep -qiE "$kubectl_mut"    && block "kubectl mutation"
echo "$c" | grep -qiE "$helm_mut"       && block "helm mutation"
echo "$c" | grep -qiE "$compose_mut"    && block "docker compose mutation"
echo "$c" | grep -qiE "$docker_mut"     && block "docker mutation"
echo "$c" | grep -qiE "$shell_dangerous" && block "destructive shell"

exit 0
