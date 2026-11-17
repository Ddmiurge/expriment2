"""统一的 chat template 调用。

Qwen3 默认开 thinking。判官只给 8 个 token、关键词抽取只给 64 个 token，
思考前缀会把预算吃光（实测 `"<think>\\nOkay, let's see."`）。
所有本地 Qwen3 调用都走这里，避免第三次漏。
"""

from __future__ import annotations


def apply_chat_template_no_think(tokenizer, messages, **kwargs):
    """关闭 thinking 的 apply_chat_template；模型不支持该参数时退回旧行为。"""
    try:
        return tokenizer.apply_chat_template(
            messages, enable_thinking=False, **kwargs
        )
    except TypeError:
        return tokenizer.apply_chat_template(messages, **kwargs)
