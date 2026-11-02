#!/usr/bin/env bash
set -euo pipefail
umask 077
project_root="${FISH_PROJECT_ROOT:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)}"
runtime_root="${FISH_XHS_ROOT:-$project_root/data/xiaohongshu}"
mkdir -p "$runtime_root/logs"
export FISH_PROJECT_ROOT="$project_root" FISH_XHS_ROOT="$runtime_root"
setsid nohup "${FISH_PYTHON:-python3}" "$project_root/scripts/xiaohongshu-runtime.py" \
  >> "$runtime_root/logs/runtime.log" 2>&1 < /dev/null &
echo '小红书只读浏览器已启动；桌面默认监听 127.0.0.1:6083'
