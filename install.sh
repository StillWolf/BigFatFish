#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$project_root"
if [[ "${1:-}" = --help || "${1:-}" = -h ]]; then
  cat <<'EOF'
用法：bash install.sh [--wechat] [--config 文件.json] [--non-interactive] [--configure-only]
默认交互配置并安装 Docker Compose 服务。API Key 隐藏输入；QQ/微信需要自行扫码登录。
--configure-only 只写配置，不安装 Docker、不拉镜像、不启动服务。
非交互模式通过 DEEPSEEK_API_KEY 环境变量提供密钥，配置文件参考 config/fish.example.json。
EOF
  exit 0
fi
case "$(uname -s)/$(uname -m)" in Linux/x86_64|Linux/aarch64|Linux/arm64) ;; *) echo '支持 Linux x86_64/ARM64；Windows 请在 WSL2 Linux 中运行' >&2; exit 1;; esac
privilege=()
if [[ "$(id -u)" != 0 ]]; then privilege=(sudo); fi
if ! command -v python3 >/dev/null; then
  command -v apt-get >/dev/null || { echo '请先安装 Python 3.10+' >&2; exit 1; }
  "${privilege[@]}" apt-get update
  "${privilege[@]}" apt-get install -y python3
fi
python3 scripts/configure.py "$@"
for arg in "$@"; do [[ "$arg" != --configure-only ]] || exit 0; done
if ! command -v docker >/dev/null || ! docker compose version >/dev/null 2>&1; then
  # Install Docker from its signed official apt repository; leave existing engines/data intact.
  . /etc/os-release
  [[ "${ID:-}" = ubuntu || "${ID:-}" = debian ]] || { echo '请按 https://docs.docker.com/engine/install/ 安装 Docker Engine 和 Compose v2 后重试' >&2; exit 1; }
  "${privilege[@]}" apt-get update
  "${privilege[@]}" apt-get install -y ca-certificates curl
  "${privilege[@]}" install -m 0755 -d /etc/apt/keyrings
  key_temp="$(mktemp)"
  trap 'rm -f "$key_temp"' EXIT
  curl -fsSL --retry 3 "https://download.docker.com/linux/${ID}/gpg" -o "$key_temp"
  "${privilege[@]}" install -m 0644 "$key_temp" /etc/apt/keyrings/docker.asc
  codename="${UBUNTU_CODENAME:-${VERSION_CODENAME:-}}"
  [[ -n "$codename" ]] || { echo '无法识别发行版代号，请手动安装 Docker' >&2; exit 1; }
  arch="$(dpkg --print-architecture)"
  printf '%s\n' "deb [arch=${arch} signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/${ID} ${codename} stable" | "${privilege[@]}" tee /etc/apt/sources.list.d/docker.list >/dev/null
  "${privilege[@]}" apt-get update
  if command -v docker >/dev/null; then
    "${privilege[@]}" apt-get install -y docker-buildx-plugin docker-compose-plugin
  else
    "${privilege[@]}" apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  fi
fi
if ! docker info >/dev/null 2>&1 && ! "${privilege[@]}" docker info >/dev/null 2>&1; then
  if command -v systemctl >/dev/null; then "${privilege[@]}" systemctl start docker; fi
fi
exec bash fishctl up
