#!/bin/bash
# 限制容器對外連線，只允許下列網域；其餘一律拒絕。
# 改寫自 https://github.com/anthropics/claude-code/blob/main/.devcontainer/init-firewall.sh
# 與原版的差異：
#   - 不開放 SSH（git remote 走 HTTPS）
#   - 先切成預設拒絕再加入允許清單，中途失敗時網路維持封鎖（fail-closed）
#   - 加入本專案需要的網域（Gemini API、104、PyPI）
set -euo pipefail
IFS=$'\n\t'

ALLOWED_DOMAINS=(
  # Claude Code（https://code.claude.com/docs/en/network-config）
  "api.anthropic.com"
  "claude.ai"
  "claude.com"
  "platform.claude.com"
  "mcp-proxy.anthropic.com"
  "code.claude.com"
  "raw.githubusercontent.com"
  "registry.npmjs.org"
  # Claude Code Remote Control：bridge 是連線用的 websocket，cdn.growthbook.io 供 feature flag 判斷功能是否可用
  "bridge.claudeusercontent.com"
  "cdn.growthbook.io"
  # VS Code 擴充套件
  "marketplace.visualstudio.com"
  "vscode.blob.core.windows.net"
  "update.code.visualstudio.com"
  # 本專案
  "generativelanguage.googleapis.com"
  "www.104.com.tw"
  "pypi.org"
  "files.pythonhosted.org"
)

# 保留 Docker 內建 DNS 的規則，清空後再還原
DOCKER_DNS_RULES=$(iptables-save -t nat | grep "127\.0\.0\.11" || true)

iptables -F
iptables -X
iptables -t nat -F
iptables -t nat -X
iptables -t mangle -F
iptables -t mangle -X
ipset destroy allowed-domains 2>/dev/null || true

if [ -n "$DOCKER_DNS_RULES" ]; then
  echo "還原 Docker DNS 規則"
  iptables -t nat -N DOCKER_OUTPUT 2>/dev/null || true
  iptables -t nat -N DOCKER_POSTROUTING 2>/dev/null || true
  echo "$DOCKER_DNS_RULES" | xargs -L 1 iptables -t nat
fi

# DNS 與 localhost
iptables -A OUTPUT -p udp --dport 53 -j ACCEPT
iptables -A INPUT -p udp --sport 53 -j ACCEPT
iptables -A INPUT -i lo -j ACCEPT
iptables -A OUTPUT -o lo -j ACCEPT

# 主機所在網段（Docker Desktop 與容器溝通用）
HOST_IP=$(ip route | grep default | cut -d" " -f3)
if [ -z "$HOST_IP" ]; then
  echo "錯誤：找不到主機 IP"
  exit 1
fi
HOST_NETWORK=$(echo "$HOST_IP" | sed "s/\.[0-9]*$/.0\/24/")
iptables -A INPUT -s "$HOST_NETWORK" -j ACCEPT
iptables -A OUTPUT -d "$HOST_NETWORK" -j ACCEPT

# 封鎖前先取得 GitHub 的 IP 範圍（需要連到 api.github.com）
echo "取得 GitHub IP 範圍"
gh_ranges=$(curl -sf --connect-timeout 10 https://api.github.com/meta || true)

# 從這裡開始預設拒絕；之後任何步驟失敗，網路都維持封鎖
ipset create allowed-domains hash:net
iptables -P INPUT DROP
iptables -P FORWARD DROP
iptables -P OUTPUT DROP
iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
iptables -A OUTPUT -m set --match-set allowed-domains dst -j ACCEPT
iptables -A OUTPUT -j REJECT --reject-with icmp-admin-prohibited

if ! echo "$gh_ranges" | jq -e '.web and .api and .git' >/dev/null 2>&1; then
  echo "錯誤：無法取得 GitHub IP 範圍，網路維持封鎖"
  exit 1
fi
while read -r cidr; do
  if [[ ! "$cidr" =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}/[0-9]{1,2}$ ]]; then
    echo "錯誤：GitHub 回傳的 CIDR 格式不正確：$cidr"
    exit 1
  fi
  ipset add -exist allowed-domains "$cidr"
done < <(echo "$gh_ranges" | jq -r '(.web + .api + .git)[]' | aggregate -q)

for domain in "${ALLOWED_DOMAINS[@]}"; do
  ips=$(dig +noall +answer A "$domain" | awk '$4 == "A" {print $5}')
  if [ -z "$ips" ]; then
    echo "警告：無法解析 $domain，略過"
    continue
  fi
  while read -r ip; do
    if [[ ! "$ip" =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; then
      echo "錯誤：$domain 解析出的 IP 格式不正確：$ip"
      exit 1
    fi
    ipset add -exist allowed-domains "$ip"
  done < <(echo "$ips")
  echo "已允許 $domain"
done

echo "驗證防火牆"
if curl -s --connect-timeout 5 https://example.com >/dev/null; then
  echo "錯誤：仍可連到 example.com，防火牆未生效"
  exit 1
fi
for url in https://api.github.com/zen https://api.anthropic.com https://generativelanguage.googleapis.com; do
  if ! curl -s --connect-timeout 5 -o /dev/null "$url"; then
    echo "錯誤：無法連到 $url"
    exit 1
  fi
done
echo "防火牆設定完成"
