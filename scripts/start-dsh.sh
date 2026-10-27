#!/usr/bin/env bash
set -euo pipefail
project_root="${FISH_PROJECT_ROOT:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)}"
export FISH_PROJECT_ROOT="$project_root"
export DSH_HOME="${DSH_HOME:-$project_root/data/dsh}"
cd "$project_root/data/qq-bridge"
exec "$project_root/node_modules/.bin/dsh" web --no-open "$@"
