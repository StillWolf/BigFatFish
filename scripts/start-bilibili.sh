#!/usr/bin/env bash
set -euo pipefail
project_root="${FISH_PROJECT_ROOT:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)}"
exec "${FISH_PYTHON:-python3}" "$project_root/scripts/bilibili-runtime.py"
