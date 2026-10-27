FROM ubuntu:24.04
ARG INSTALL_BILIBILI=1
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-venv python3-dev build-essential ca-certificates curl git xz-utils \
    ffmpeg xvfb openbox x11vnc novnc websockify scrot fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*
# Pin Node to the production baseline and verify its architecture-specific archive.
RUN arch="$(dpkg --print-architecture)" && \
    case "$arch" in amd64) node_arch=x64 ;; arm64) node_arch=arm64 ;; *) exit 1 ;; esac && \
    curl -fsSL --retry 3 -o /tmp/node.tar.xz "https://nodejs.org/dist/v22.22.0/node-v22.22.0-linux-${node_arch}.tar.xz" && \
    curl -fsSL --retry 3 -o /tmp/node-sha.txt https://nodejs.org/dist/v22.22.0/SHASUMS256.txt && \
    awk -v file="node-v22.22.0-linux-${node_arch}.tar.xz" '$2 == file {print $1 "  /tmp/node.tar.xz"}' /tmp/node-sha.txt > /tmp/node-check.txt && \
    test -s /tmp/node-check.txt && sha256sum -c /tmp/node-check.txt && \
    tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:/opt/fish/node_modules/.bin:${PATH}" \
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright \
    FISH_PROJECT_ROOT=/opt/fish \
    FISH_CONFIG=/run/fish/fish.config.json \
    FISH_NAPCAT_CONFIG=/state/napcat-config \
    FISH_BILIBILI_WEB_BIND=0.0.0.0 \
    FISH_WECHAT_MCP_URL=http://wechat:8000/mcp \
    DSH_HOME=/state/dsh \
    HF_HUB_DISABLE_TELEMETRY=1 \
    HF_HUB_DISABLE_XET=1 \
    PYTHONUNBUFFERED=1
WORKDIR /opt/fish
COPY scripts/requirements-tts.txt scripts/requirements-bilibili.txt /tmp/requirements/
RUN pip install --no-cache-dir -r /tmp/requirements/requirements-tts.txt && \
    if [ "$INSTALL_BILIBILI" = 1 ]; then \
      pip install --no-cache-dir -r /tmp/requirements/requirements-bilibili.txt && \
      python -m playwright install --with-deps chromium; \
    fi && rm -rf /var/lib/apt/lists/*
COPY package.json package-lock.json ./
COPY dsh-qq-onebot-bridge ./dsh-qq-onebot-bridge
COPY dsh-wechat-ai-bridge ./dsh-wechat-ai-bridge
RUN npm ci --omit=dev && npm cache clean --force
COPY config ./config
COPY scripts ./scripts
HEALTHCHECK --interval=15s --timeout=5s --start-period=120s --retries=4 \
    CMD ["python", "/opt/fish/scripts/health.py"]
CMD ["python", "/opt/fish/scripts/runtime.py"]
