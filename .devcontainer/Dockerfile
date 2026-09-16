# 讓 Claude Code 以 --dangerously-skip-permissions 執行的隔離環境
# 參考：https://github.com/anthropics/claude-code/tree/main/.devcontainer
FROM node:22-bookworm

ARG TZ
ENV TZ="$TZ"

ARG CLAUDE_CODE_VERSION=latest

# 基本工具；iptables / ipset / dnsutils / aggregate 供 init-firewall.sh 使用
RUN apt-get update && apt-get install -y --no-install-recommends \
  less \
  git \
  procps \
  sudo \
  jq \
  curl \
  ca-certificates \
  iptables \
  ipset \
  iproute2 \
  dnsutils \
  aggregate \
  vim \
  && apt-get clean && rm -rf /var/lib/apt/lists/*

# uv（官方建議的安裝方式：https://docs.astral.sh/uv/guides/integration/docker/）
COPY --from=ghcr.io/astral-sh/uv:0.12.15 /uv /uvx /bin/

# npm 全域套件裝在 node 使用者可寫的位置，Claude Code 才能自動更新
RUN mkdir -p /usr/local/share/npm-global /workspace /home/node/.claude && \
  chown -R node:node /usr/local/share/npm-global /workspace /home/node/.claude

ENV DEVCONTAINER=true

# 以非 root 使用者執行：--dangerously-skip-permissions 在 root 下會被拒絕
USER node
WORKDIR /workspace

ENV NPM_CONFIG_PREFIX=/usr/local/share/npm-global
ENV PATH=$PATH:/usr/local/share/npm-global/bin
ENV EDITOR=vim

RUN npm install -g @anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}

# Python 在建置階段安裝（此時尚未啟用防火牆）
RUN uv python install 3.14

# 防火牆腳本：node 使用者只能以 sudo 執行這一支
COPY init-firewall.sh /usr/local/bin/
USER root
RUN chmod +x /usr/local/bin/init-firewall.sh && \
  echo "node ALL=(root) NOPASSWD: /usr/local/bin/init-firewall.sh" > /etc/sudoers.d/node-firewall && \
  chmod 0440 /etc/sudoers.d/node-firewall
USER node
