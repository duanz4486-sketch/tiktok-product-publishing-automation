from __future__ import annotations

import cgi


def field_text(form: cgi.FieldStorage, name: str, default: str = "") -> str:
    field = form[name] if name in form else None
    if field is None or isinstance(field, list):
        return default
    return str(field.value or default).strip()


def decimal_field(
    form: cgi.FieldStorage,
    name: str,
    label: str,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    value = field_text(form, name)
    if not value:
        raise ValueError(f"请填写{label}")
    try:
        number = float(value)
    except ValueError:
        raise ValueError(f"{label}必须是数字")
    if minimum is not None and number < minimum:
        raise ValueError(f"{label}不能小于 {minimum}")
    if maximum is not None and number > maximum:
        raise ValueError(f"{label}不能大于 {maximum}")
    return number


def int_field(form: cgi.FieldStorage, name: str, label: str, minimum: int | None = None) -> int:
    value = field_text(form, name)
    if not value:
        raise ValueError(f"请填写{label}")
    try:
        number = int(value)
    except ValueError:
        raise ValueError(f"{label}必须是整数")
    if minimum is not None and number < minimum:
        raise ValueError(f"{label}不能小于 {minimum}")
    return number


def optional_int(value: str, label: str) -> int | None:
    value = str(value or "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"{label} 必须是数字")
