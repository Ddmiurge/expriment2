"""AVTP 运行时配置。

补丁把 `_PRUNE_CONFIG` / `_PRUNE_STATE` / `_PRUNE_RECORD` 放在
`transformers.models.qwen3_vl.modeling_qwen3_vl` 的模块级。这里只做三件事：
  1. 检查补丁在不在；
  2. 写入配置；
  3. 跑完后把记录读出来。

**不要重新赋值这些字典**，只能原地改：注入的函数按模块全局名查找它们，
从外面换一个新 dict 不会生效。
"""

from __future__ import annotations

from dataclasses import dataclass

# 原文报过的三档 + 我们校准的 25% 档
#   50%: 0.8 * 0.8 * 0.78 ≈ 0.499（原文）
#   20%: 0.8 * 0.5 * 0.5  = 0.20 （原文注释里的档）
#   5% : 0.8 * 0.5 * 0.125= 0.05 （原文注释里的档）
#   25%: 0.8 * 0.60 * 0.52≈ 0.2496（我们校准；论文里要注明不是原文数字）
SCHEDULES: dict[float, list[float]] = {
    0.50: [0.8, 0.8, 0.78],
    0.25: [0.8, 0.60, 0.52],
    0.20: [0.8, 0.5, 0.5],
    0.05: [0.8, 0.5, 0.125],
}


def schedule_for(budget: float) -> list[float]:
    for b, s in SCHEDULES.items():
        if abs(b - budget) < 1e-9:
            return list(s)
    raise ValueError(
        f"没有预算 {budget} 的 AVTP 档位。可选：{sorted(SCHEDULES)}。"
        "要加新档位，先想清楚三层比例的乘积是多少，再写进 SCHEDULES。"
    )


def _module(required: bool = True):
    try:
        from transformers.models.qwen3_vl import modeling_qwen3_vl as m
    except ImportError as e:
        raise RuntimeError(f"import transformers 失败：{e}") from e
    if not hasattr(m, "_PRUNE_CONFIG"):
        if not required:
            return None
        raise RuntimeError(
            "当前 transformers 没有多图剪枝补丁。先跑：\n"
            "  python scripts/apply_avtp_patch.py --mode instrumented"
        )
    return m


def available() -> bool:
    return _module(required=False) is not None


def configure(
    *,
    method: str,
    budget: float = 0.5,
    layers: tuple[int, ...] = (1, 19, 22),
    alpha: float = 1.0,
    keep_local: list[list[int]] | None = None,
    record_scores: bool = False,
    record_indices: bool = False,
) -> None:
    m = _module()
    if method not in ("avtp", "equal", "precomputed"):
        raise ValueError(f"method={method!r} 只允许 avtp / equal / precomputed")
    ratios = [1.0] * len(layers) if method == "precomputed" else schedule_for(budget)
    if len(ratios) != len(layers):
        raise ValueError("层数与比例档数不一致")
    m._PRUNE_CONFIG.update(
        enabled=True,
        method=method,
        reduce_layers=list(layers),
        base_ratios=list(ratios),
        alpha=float(alpha),
        keep_local=keep_local,
        record_scores=record_scores,
        record_indices=record_indices,
    )
    m._PRUNE_STATE.clear()
    m._PRUNE_RECORD.clear()


def disable() -> None:
    m = _module(required=False)
    if m is None:
        return  # 没打补丁时基线本来就不剪枝
    m._PRUNE_CONFIG["enabled"] = False
    m._PRUNE_STATE.clear()
    m._PRUNE_RECORD.clear()


def reset() -> None:
    m = _module(required=False)
    if m is None:
        return
    m._PRUNE_STATE.clear()
    m._PRUNE_RECORD.clear()


def records() -> list[dict]:
    m = _module()
    return list(m._PRUNE_RECORD)


def last_kept_local() -> list[list[int]] | None:
    recs = records()
    if not recs:
        return None
    return recs[-1]["per_image_kept_local"]


@dataclass
class PruneSummary:
    n_before: int
    n_after: int
    per_image_keep_count: list[int]

    @property
    def keep_fraction(self) -> float:
        return self.n_after / self.n_before if self.n_before else 0.0


def summary() -> PruneSummary | None:
    recs = records()
    if not recs:
        return None
    r = recs[-1]
    return PruneSummary(
        n_before=recs[0]["n_before"],
        n_after=r["n_after"],
        per_image_keep_count=r["per_image_keep_count"],
    )
