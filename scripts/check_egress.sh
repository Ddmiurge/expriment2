#!/usr/bin/env bash
# 出网边界探测。服务器上最先跑。
#
# 用 git ls-remote 和 curl 检查三条通道：
#   1. GitHub（代码下行）
#   2. HuggingFace（模型/数据下行）
#   3. OpenAI（本仓库要求 0 依赖；只确认它不通，避免有人偷偷走 API）
#
# 用法：
#   bash scripts/check_egress.sh
#   bash scripts/check_egress.sh https://github.com/zry13/AVTP

set -uo pipefail

GIT_URL="${1:-https://github.com/zry13/AVTP}"

ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; }

echo "== 1. GitHub =="
if GIT_TERMINAL_PROMPT=0 git ls-remote --heads "$GIT_URL" >/dev/null 2>&1; then
  ok "git ls-remote $GIT_URL"
else
  bad "git ls-remote $GIT_URL —— 代码下行不通，先解决这个"
fi

echo "== 2. HuggingFace =="
if curl -sS -m 20 -o /dev/null -w '%{http_code}' https://huggingface.co/api/models/Qwen/Qwen3-VL-8B-Instruct 2>/dev/null | grep -q '^200$'; then
  ok "huggingface.co API"
else
  bad "huggingface.co API —— 模型/数据下行不通；检查镜像或代理设置"
fi

echo "== 3. OpenAI（本仓库不应依赖） =="
if curl -sS -m 8 -o /dev/null https://api.openai.com/v1/models 2>/dev/null; then
  warn "api.openai.com 可达。本仓库的设计要求离线；如果代码里出现 openai 调用，是 bug。"
else
  ok "api.openai.com 不可达（符合离线设计）"
fi

echo
echo "结论：第 1、2 项必须通过；第 3 项只做记录。"
