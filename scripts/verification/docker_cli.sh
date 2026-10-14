#!/usr/bin/env bash
# Shared by local launchers. Prefer WSL integration; use the user's Windows CLI
# when Desktop is healthy but its WSL socket is not available.
select_docker_cli() {
  local windows_cli='/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe'
  # Probe daemon reachability without collecting the full Desktop diagnostics.
  if command -v docker >/dev/null && timeout 10 docker version --format '{{.Server.Version}}' >/dev/null 2>&1; then
    verification_docker_cli=(docker)
    verification_docker_windows=false
    return 0
  fi
  if [[ -x "$windows_cli" ]] && timeout 20 "$windows_cli" version --format '{{.Server.Version}}' >/dev/null 2>&1; then
    verification_docker_cli=("$windows_cli")
    verification_docker_windows=true
    return 0
  fi
  return 1
}
verification_compose() {
  local argument previous='' converted
  local arguments=()
  for argument in "$@"; do
    converted="$argument"
    if "$verification_docker_windows" && [[ "$previous" == '-f' || "$previous" == '--env-file' ]]; then
      converted="$(wslpath -w "$(realpath "$argument")")"
    fi
    arguments+=("$converted")
    previous="$argument"
  done
  "${verification_docker_cli[@]}" compose "${arguments[@]}"
}
