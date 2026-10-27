#!/usr/bin/env bash
set -euo pipefail
ssh_target="${1:?用法: bash scripts/bilibili-tunnel.sh user@server [远程端口]}"
exec ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 \
  -L "127.0.0.1:16082:127.0.0.1:${2:-6082}" "$ssh_target"
