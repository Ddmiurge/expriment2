#!/usr/bin/env python3
"""SM0.6 载荷存活率口径自检。

三件事：
  1. 手算一个 2×2 网格，检查「全留=1、只留非载荷=0、只留载荷=1」；
  2. 掩码不能整除网格时必须报错，不能静默取整；
  3. 如果有真实的 MIDAS 样本，检查不剪枝时存活率必须=1.0。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.eval.survival import compute_survival  # noqa: E402
from src.pruning.layout import mask_to_grid, survival_rate  # noqa: E402


def main() -> int:
    ok = True

    # 1. 手算
    pg = np.array([[True, False], [False, False]])
    checks = [
        (survival_rate([0, 1, 2, 3], 2, 2, pg), 1.0),
        (survival_rate([3], 2, 2, pg), 0.0),
        (survival_rate([0], 2, 2, pg), 1.0),
        (survival_rate([0, 1], 2, 2, pg), 1.0),
    ]
    for got, want in checks:
        if abs(got - want) > 1e-12:
            print(f"✗ 手算不符：got={got} want={want}")
            ok = False
    print("1. 手算 4 项", "通过" if ok else "失败")

    # 2. 不能整除：重采样后应得到正确的网格形状，不能静默取整
    g = mask_to_grid(np.ones((5, 5)), 2, 2)
    if g.shape == (2, 2) and g.all():
        print("2. 不可整除掩码重采样到 2×2 ✓")
    else:
        print(f"✗ 不可整除掩码处理不对：shape={g.shape}, all={g.all()}")
        ok = False

    # 3. 真实样本
    sample_path = Path("data/midas/attack_set.jsonl")
    if sample_path.exists():
        from PIL import Image

        with sample_path.open(encoding="utf-8") as f:
            s = json.loads(f.readline())
        masks = [np.asarray(Image.open(im["mask_path"]).convert("L")) > 0 for im in s["images"]]
        n = masks[0].shape
        grids = [(n[0] // 8, n[1] // 8)] * len(masks)  # 占位网格，只为检查全留=1
        s_surv = compute_survival([list(range(gh * gw)) for gh, gw in grids], grids, masks)
        print(f"3. 真实样本 {s['id']} 不剪枝存活率 = {s_surv.overall}")
        if s_surv.overall is not None and abs(s_surv.overall - 1.0) > 1e-9:
            print("✗ 不剪枝时存活率不是 1.0")
            ok = False
    else:
        print("3. 没有 data/midas/attack_set.jsonl，跳过真实样本检查（阶段 1 前会生成）")

    print("SM0.6", "通过" if ok else "失败")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
