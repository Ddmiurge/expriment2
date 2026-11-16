#!/usr/bin/env bash
# 拉取并锁定第三方仓库。
#
# 规则与单图仓库一致：
#   - 脚本不写死 commit SHA；首次解析后写进 third_party.lock
#   - 之后所有机器按 lock 检出
#   - third_party/ 里的内容一律不改
#
# 用法：
#     bash env/fetch_third_party.sh
#     bash env/fetch_third_party.sh --relock    # 忽略 lock 重新解析（慎用）

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TP="$ROOT/third_party"
LOCK="$ROOT/third_party.lock"
RELOCK=0
[ "${1:-}" = "--relock" ] && RELOCK=1

mkdir -p "$TP"
[ -f "$LOCK" ] || printf '# name\turl\tsha\tfetched_at\n' > "$LOCK"

ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; }

# name|url|ref
REPOS=(
  "avtp|https://github.com/zry13/AVTP|main"
  "midas|https://github.com/Winnie-Lian/MIDAS|main"
  "mir-safetybench|https://github.com/thu-coai/MIR-SafetyBench|main"
)

locked_sha() {  # $1=name
  [ -f "$LOCK" ] || return 1
  awk -v n="$1" '$1==n {print $3; exit}' "$LOCK"
}

record_lock() {  # $1=name $2=url $3=sha
  printf '%s\t%s\t%s\t%s\n' "$1" "$2" "$3" "$(date -Iseconds)" >> "$LOCK"
}

for entry in "${REPOS[@]}"; do
  IFS='|' read -r name url ref <<< "$entry"

  sha=""
  [ "$RELOCK" -eq 0 ] && sha="$(locked_sha "$name" || true)"

  if [ -z "$sha" ]; then
    sha="$(git ls-remote "$url" "$ref" 2>/dev/null | awk '{print $1}' | head -1)"
    if [ -z "$sha" ]; then
      bad "$name —— 无法从 $url 解析 $ref（URL 错？出网不通？）"
      continue
    fi
    record_lock "$name" "$url" "$sha"
    warn "$name —— 首次解析，已写入 third_party.lock：${sha:0:12}"
  fi

  dest="$TP/$name"
  if [ -d "$dest/.git" ]; then
    if git -C "$dest" fetch --quiet origin "$sha" 2>/dev/null; then
      git -C "$dest" checkout --quiet "$sha" 2>/dev/null \
        && ok "$name @ ${sha:0:12}" \
        || bad "$name —— checkout $sha 失败"
    else
      bad "$name —— fetch $sha 失败（lock 里的 SHA 可能已不存在）"
    fi
  else
    if git clone --quiet "$url" "$dest" 2>/dev/null; then
      git -C "$dest" checkout --quiet "$sha" 2>/dev/null \
        && ok "$name @ ${sha:0:12}（新克隆）" \
        || bad "$name —— clone 成功但 checkout $sha 失败"
    else
      bad "$name —— clone $url 失败"
    fi
  fi
done

printf '\n锁定状态：\n'
[ -f "$LOCK" ] && sed 's/^/  /' "$LOCK"
printf '\nthird_party.lock 要进 git —— 它才是复现依据，仓库内容不是。\n'
