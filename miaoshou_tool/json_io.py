from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def dumps(data: Any, *, compact: bool = False) -> str:
    if compact:
        return json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return json.dumps(data, ensure_ascii=False, indent=2)


def loads(text: str) -> Any:
    return json.loads(text)


def read(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return loads(path.read_text(encoding="utf-8"))


def write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(data), encoding="utf-8")


def ok(data: Any = None, **extra: Any) -> dict[str, Any]:
    payload = {"ok": True}
    if data is not None:
        payload["data"] = data
    payload.update(extra)
    return payload


def fail(error: object, **extra: Any) -> dict[str, Any]:
    payload = {"ok": False, "error": str(error or "")}
    payload.update(extra)
    return payload


def job_log(summary: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, Any]:
    return {"summary": summary, "results": results}
