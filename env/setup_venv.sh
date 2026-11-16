#!/usr/bin/env bash
# 建独立 venv，复用系统 CUDA torch，只覆盖 transformers 等纯 Python 包。
#
# 为什么 --system-site-packages：
#   服务器已经装好 CUDA 版 torch（单图仓库在用）。venv 里再装一份 torch 要 2–3 GB，
#   而且 CUDA 版本要重新对一遍。复用系统 torch，只把 transformers 降到 4.57.1。
#
# 用法：
#   bash env/setup_venv.sh
#   source .venv/bin/activate
#   python scripts/apply_avtp_patch.py --mode instrumented

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PY="${PYTHON:-python3}"

echo "== 1. 检查系统 torch =="
"$PY" - <<'EOF'
import torch
print(f"torch {torch.__version__}  cuda={torch.cuda.is_available()}  devices={torch.cuda.device_count()}")
if not torch.cuda.is_available():
    raise SystemExit("系统 torch 没有 CUDA。先解决 torch，再建 venv。")
EOF

echo "== 2. 建 venv =="
# 如果已经存在，先确认它是不是 --system-site-packages 建的
if [ -d .venv ]; then
  if ! grep -q "include-system-site-packages = true" .venv/pyvenv.cfg 2>/dev/null; then
    echo "  ✗ .venv 已存在，但不是 --system-site-packages 建的。"
    echo "    删掉重建：rm -rf .venv && bash env/setup_venv.sh"
    exit 1
  fi
  echo "  .venv 已存在（system-site-packages），跳过创建"
else
  "$PY" -m venv --system-site-packages .venv
  echo "  已建 .venv（--system-site-packages）"
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "== 3. 安装锁定版本 =="
python -m pip install --upgrade pip
python -m pip install -r env/requirements.txt

echo "== 4. 版本核对 =="
python - <<'EOF'
import transformers, torch
print(f"transformers {transformers.__version__}  torch {torch.__version__}")
assert transformers.__version__ == "4.57.1", (
    f"transformers 必须是 4.57.1，现在是 {transformers.__version__}。"
    "AVTP 的 patch 锚点只在 4.57.1 上验过。"
)
EOF

echo
echo "下一步："
echo "  python scripts/apply_avtp_patch.py --check"
echo "  python scripts/apply_avtp_patch.py --mode instrumented"
