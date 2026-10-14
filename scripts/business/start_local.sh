#!/usr/bin/env bash
# Start the generic platform plus isolated MySQL/PostgreSQL example sources.
set -Eeuo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"
export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/langflow-uv-cache}"
export PATH="$PATH:/mnt/wsl/docker-desktop/cli-tools/usr/bin"
runtime="$root/deploy/verification/.cache/runtime/bin/python"
python=(uv run --no-project --python "$runtime" python)
"${python[@]}" scripts/business/configure_sources.py
BUSINESS_DEFER_WORKER=1 BUSINESS_DRAIN_ON_START=1 bash scripts/verification/start_local.sh "$@"
source "$root/scripts/verification/docker_cli.sh"
select_docker_cli || { echo "Docker 服务不可用" >&2; exit 1; }
verification_compose --env-file deploy/verification/.cache/business-sources.env -f deploy/business/compose.yaml up -d --wait --wait-timeout 240
"${python[@]}" scripts/business/migrate_validate_outputs.py
"${python[@]}" -m scripts.business.publish_local
"${python[@]}" scripts/business/bootstrap.py
"${python[@]}" scripts/business/maintenance_local.py open
bash scripts/verification/start_local.sh
cat <<'OUT'

通用业务平台：http://localhost:3000/business
连接管理：http://localhost:3000/business/connections
任务与结果：http://localhost:3000/business/tasks
历史规则：http://localhost:3000/business/history
历史任务：http://localhost:3000/verification/tasks
示例数据源：MySQL 13306 / PostgreSQL 55434（均为模拟业务数据）
一键重启：bash scripts/business/start_local.sh --restart
OUT
