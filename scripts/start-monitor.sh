#!/usr/bin/env bash
set -euo pipefail
umask 077
project_root="${FISH_PROJECT_ROOT:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)}"
export FISH_PROJECT_ROOT="$project_root"
mkdir -p "$project_root/data/health"
setsid nohup "${FISH_MONITOR_PYTHON:-python3}" "$project_root/scripts/fish-monitor.py" \
  >> "$project_root/data/health/monitor.log" 2>&1 < /dev/null &
echo '状态监控已启动；页面默认监听 127.0.0.1:18180'
