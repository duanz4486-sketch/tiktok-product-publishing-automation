from __future__ import annotations

import re


def masked_app_key(value: str) -> str:
    value = str(value or "")
    if not value:
        return "缺少 APP ID"
    if len(value) <= 8:
        return value[:2] + "..." + value[-2:]
    return value[:4] + "..." + value[-4:]


def normalized_text(value: object) -> str:
    if isinstance(value, dict):
        return " ".join(normalized_text(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(normalized_text(item) for item in value)
    return re.sub(r"\s+", "", str(value or "")).lower()
