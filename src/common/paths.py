"""路径与配置。所有脚本都从这里拿路径，避免各写一份。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def load_paths() -> dict:
    p = repo_root() / "env" / "paths.yaml"
    if not p.exists():
        raise FileNotFoundError(
            f"{p} 不存在。先复制模板：cp env/paths.example.yaml env/paths.yaml"
        )
    with p.open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    for key in ("third_party", "results"):
        if key in cfg and not Path(cfg[key]).is_absolute():
            cfg[key] = str((repo_root() / cfg[key]).resolve())
    return cfg


def model_path(name: str) -> str:
    return load_paths()["models"][name]


def data_path(name: str) -> str:
    return load_paths()["data"][name]


def runtime() -> dict:
    return load_paths().get("runtime", {})


def judge_cfg() -> dict:
    return load_paths().get("judge", {})
