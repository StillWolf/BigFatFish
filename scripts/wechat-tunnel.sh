#!/usr/bin/env bash
set -euo pipefail
ssh_target="${1:?用法: bash scripts/wechat-tunnel.sh user@server [远程端口]}"
exec ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 \
  -L "127.0.0.1:16081:127.0.0.1:${2:-6081}" "$ssh_target"
