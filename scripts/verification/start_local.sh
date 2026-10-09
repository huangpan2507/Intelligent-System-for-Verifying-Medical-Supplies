#!/usr/bin/env bash
# Start the already-configured source simulation, preserving its databases and rules.
set -Eeuo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"
restart=false
case "${1:-}" in
  "") ;;
  --restart) restart=true ;;
  *) echo "用法：bash scripts/verification/start_local.sh [--restart]" >&2; exit 2 ;;
esac
[[ $# -le 1 ]] || exit 2

fail() { echo "启动失败：$*" >&2; exit 1; }
for tool in uv npm node tmux curl ss flock timeout; do
  command -v "$tool" >/dev/null || fail "缺少命令 $tool，请先安装。"
done
runtime="$root/deploy/verification/.cache/runtime/bin/python"
logs="$root/deploy/verification/.cache/source-ui"
[[ -x "$runtime" ]] || fail "缺少专项 Python 环境，请先按 deploy/verification/README.md 配置。"
[[ -f deploy/verification/.env ]] || fail "缺少 deploy/verification/.env，请先完成首次配置。"
[[ -f "$logs/langflow.db" ]] || fail "缺少已配置的平台数据库，请先完成首次配置和流程导入。"
[[ -x src/frontend/node_modules/.bin/vite ]] || fail "缺少前端依赖，请先在 src/frontend 执行 npm ci。"
mkdir -p "$logs"
exec 9>"$logs/start-local.lock"
flock -n 9 || fail "另一个启动或重启命令正在执行，请等待它完成。"
export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/langflow-uv-cache}"
python=(uv run --no-project --python "$runtime" python)
api_port="$("${python[@]}" - <<'PY'
from dotenv import dotenv_values

config = dotenv_values("deploy/verification/.env")
for key in ("VERIFICATION_LANGFLOW_API_KEY", "VERIFICATION_INTERNAL_TOKEN", "VERIFICATION_DB_PASSWORD"):
    if not config.get(key):
        raise SystemExit(f"私有配置缺少 {key}，请先完成首次配置和流程导入。")
port = int(config.get("VERIFICATION_SOURCE_API_PORT") or "8081")
if not 1 <= port <= 65535 or port in {3000, 7860, 8090, 55433}:
    raise SystemExit("VERIFICATION_SOURCE_API_PORT 无效或与其他项目服务端口冲突。")
print(port)
PY
)"

# Docker Desktop installs this CLI when its WSL integration becomes ready.
export PATH="$PATH:/mnt/wsl/docker-desktop/cli-tools/usr/bin"
docker_ready() {
  command -v docker >/dev/null && timeout 5 docker info >/dev/null 2>&1
}
if ! docker_ready; then
  powershell=/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe
  if [[ -x "$powershell" && -f '/mnt/c/Program Files/Docker/Docker/Docker Desktop.exe' ]]; then
    echo "启动 Docker Desktop，等待 WSL 集成就绪……"
    "$powershell" -NoProfile -NonInteractive -Command \
      "Start-Process 'C:\Program Files\Docker\Docker\Docker Desktop.exe'" 9>&-
    deadline=$((SECONDS + 180))
    until docker_ready; do
      (( SECONDS < deadline )) || fail "Docker 未就绪，请检查 Docker Desktop 的 WSL Integration。"
      sleep 2
    done
  else
    fail "Docker 未运行，请启动 Docker 服务后重试。"
  fi
fi

echo "启动并检查 PostgreSQL（保留现有数据）……"
docker compose --env-file deploy/verification/.env \
  -f deploy/verification/compose.yaml -f deploy/verification/compose.source.yaml \
  up -d --no-build --no-recreate --pull never --wait --wait-timeout 120 postgres

session_live() {
  tmux has-session -t "=$1" 2>/dev/null &&
    [[ "$(tmux display-message -p -t "=$1:" '#{pane_dead}')" == 0 ]]
}
stop_service() {
  local session="$1" deadline=$((SECONDS + 60))
  if session_live "$session"; then
    echo "停止 $session……"
    tmux send-keys -t "=$session:" C-c
    while session_live "$session"; do
      (( SECONDS < deadline )) || fail "$session 尚未退出，请查看 $logs，不强制终止运行中的任务。"
      sleep 1
    done
  fi
  if tmux has-session -t "=$session" 2>/dev/null; then
    tmux kill-session -t "=$session"
  fi
}
if "$restart"; then
  for service in verification-worker frontend platform verification-api verification-demo; do
    stop_service "langflow-$service"
  done
fi

start_service() {
  local session="$1" directory="$2" port="$3" command log_file
  shift 3
  if session_live "$session"; then
    echo "$session 已运行，复用现有进程。"
    return
  fi
  stop_service "$session"
  if [[ -n "$port" && -n "$(ss -H -ltn "sport = :$port")" ]]; then
    fail "端口 $port 被其他进程占用；请用 ss -ltnp 检查，不会自动终止其他进程。"
  fi
  printf -v command '%q ' "$@"
  printf -v log_file '%q' "$logs/$session.log"
  echo "启动 $session……"
  tmux new-session -d -s "$session" -c "$directory" \
    "exec $command >>$log_file 2>&1" 9>&-
}
wait_http() {
  local session="$1" url="$2" deadline=$((SECONDS + 180))
  until curl --noproxy '*' --fail --silent --max-time 3 "$url" >/dev/null; do
    session_live "$session" || fail "$session 已退出，请查看 $logs/$session.log。"
    (( SECONDS < deadline )) || fail "$url 就绪超时，请查看 $logs/$session.log。"
    sleep 2
  done
  echo "就绪：$url"
}

for service in demo api platform; do
  case "$service" in
    demo) session=langflow-verification-demo; port=8090; probe=/openapi.json ;;
    api) session=langflow-verification-api; port="$api_port"; probe=/health ;;
    platform) session=langflow-platform; port=7860; probe=/health ;;
  esac
  start_service "$session" "$root" "$port" env UV_CACHE_DIR="$UV_CACHE_DIR" \
    PYTHONUNBUFFERED=1 "${python[@]}" "$root/scripts/verification/run_local.py" "$service"
  wait_http "$session" "http://127.0.0.1:$port$probe"
done
start_service langflow-verification-worker "$root" "" env UV_CACHE_DIR="$UV_CACHE_DIR" \
  PYTHONUNBUFFERED=1 "${python[@]}" "$root/scripts/verification/run_local.py" worker
start_service langflow-frontend "$root/src/frontend" 3000 \
  env VITE_PROXY_TARGET=http://127.0.0.1:7860 npm run start -- --host 127.0.0.1 --port 3000 --strictPort
wait_http langflow-frontend http://127.0.0.1:3000/verification/tasks
wait_http langflow-frontend http://127.0.0.1:3000/health
sleep 2
session_live langflow-verification-worker || fail "Worker 已退出，请查看 $logs/langflow-verification-worker.log。"

cat <<EOF

完整模拟项目已启动，进程由 tmux 在后台保持，关闭当前终端后仍会运行。
前端：http://localhost:3000
核验规则：http://localhost:3000/verification
核验任务：http://localhost:3000/verification/tasks
平台 API：http://localhost:7860/docs
核验 API：http://localhost:$api_port/docs
模拟上游：http://localhost:8090/docs
PostgreSQL：127.0.0.1:55433
账号：verification-admin（密码见 deploy/verification/.env 的 LANGFLOW_SUPERUSER_PASSWORD）
日志目录：$logs/langflow-*.log
重启命令：bash scripts/verification/start_local.sh --restart
EOF
