from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

from batch_tiktok_collect import TEMPLATES

from .config import ACCOUNTS_PATH, ROOT
from .json_io import read as read_json


PROTECTED_PATTERNS = [".env", "accounts.json", "ai_settings.json", "runs/", "uploads/"]


def _check(key: str, label: str, status: str, message: str, fix: str = "") -> dict[str, str]:
    return {"key": key, "label": label, "status": status, "message": message, "fix": fix}


def _env_values(env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        values[name.strip()] = value.strip().strip("\"'")
    return values


def _has_env(name: str, file_values: dict[str, str]) -> bool:
    return bool((os.getenv(name) or file_values.get(name) or "").strip())


def _accounts_checks(accounts_path: Path) -> list[dict[str, str]]:
    if not accounts_path.exists():
        return [
            _check(
                "accounts_file",
                "妙手账号配置",
                "error",
                "没有找到 accounts.json。",
                "复制 accounts.example.json 为 accounts.json，或在网页「妙手账号管理」新增账号。",
            )
        ]
    try:
        config = read_json(accounts_path, {}) or {}
    except Exception as exc:
        return [
            _check(
                "accounts_file",
                "妙手账号配置",
                "error",
                f"accounts.json 不是有效 JSON：{exc}",
                "检查逗号、引号和括号，修正后重新打开系统自检。",
            )
        ]

    accounts = config.get("accounts") or {}
    if not accounts:
        return [
            _check(
                "accounts_count",
                "妙手账号数量",
                "error",
                "accounts.json 里还没有妙手账号。",
                "进入「妙手账号管理」新增至少一个妙手账号。",
            )
        ]

    checks = [
        _check("accounts_count", "妙手账号数量", "ok", f"已配置 {len(accounts)} 个妙手账号。"),
    ]
    for account_id, account in accounts.items():
        name = str(account.get("name") or account_id)
        missing = []
        if not str(account.get("app_key") or "").strip():
            missing.append("APP ID / App Key")
        if not str(account.get("app_secret") or "").strip():
            missing.append("App Secret")
        if not str(account.get("shop_id") or "").strip():
            missing.append("妙手账号 / shopId")
        templates = account.get("templates") or {}
        missing_templates = [template for template in TEMPLATES if not templates.get(template)]
        if missing_templates:
            missing.append("模板 ID：" + "、".join(missing_templates))
        if missing:
            checks.append(
                _check(
                    f"account_{account_id}",
                    f"账号：{name}",
                    "error",
                    "缺少 " + "；".join(missing),
                    "进入「妙手账号管理」补齐，或重新识别并确认账号。",
                )
            )
        else:
            checks.append(_check(f"account_{account_id}", f"账号：{name}", "ok", "模板批量上传所需配置完整。"))
    return checks


def run_release_check(root: Path = ROOT, accounts_path: Path = ACCOUNTS_PATH) -> dict[str, Any]:
    env_path = root / ".env"
    gitignore_path = root / ".gitignore"
    env_values = _env_values(env_path)
    checks: list[dict[str, str]] = []

    python_ok = sys.version_info >= (3, 10)
    checks.append(
        _check(
            "python",
            "Python 版本",
            "ok" if python_ok else "error",
            f"当前 Python：{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "安装 Python 3.10 或更新版本。" if not python_ok else "",
        )
    )

    checks.append(
        _check(
            "openpyxl",
            "Excel 依赖",
            "ok" if importlib.util.find_spec("openpyxl") else "error",
            "openpyxl 已安装。" if importlib.util.find_spec("openpyxl") else "缺少 openpyxl，无法读取标题 Excel。",
            "运行 python -m pip install -r requirements.txt",
        )
    )

    checks.append(
        _check(
            "env_file",
            ".env 文件",
            "ok" if env_path.exists() else "error",
            ".env 已存在。" if env_path.exists() else "没有找到 .env。",
            "复制 .env.example 为 .env，并填写 OSS 密钥。",
        )
    )

    oss_missing = [name for name in ("OSS_ACCESS_KEY_ID", "OSS_ACCESS_KEY_SECRET") if not _has_env(name, env_values)]
    checks.append(
        _check(
            "oss",
            "OSS 配置",
            "ok" if not oss_missing else "error",
            "OSS 必需配置已填写。" if not oss_missing else "缺少 " + "、".join(oss_missing),
            "在 .env 里填写阿里云 OSS AccessKey。",
        )
    )

    gate_password = _has_env("WEB_ACCESS_PASSWORD", env_values)
    gate_secret = _has_env("WEB_SESSION_SECRET", env_values)
    if gate_password and gate_secret:
        checks.append(_check("access_gate", "网页访问保护", "ok", "已配置站点访问密码。"))
    elif gate_password or gate_secret:
        checks.append(
            _check(
                "access_gate",
                "网页访问保护",
                "error",
                "站点访问密码配置不完整。",
                "在 .env 里同时填写 WEB_ACCESS_PASSWORD 和 WEB_SESSION_SECRET，或两个都留空只用于本地测试。",
            )
        )
    else:
        checks.append(
            _check(
                "access_gate",
                "网页访问保护",
                "warn",
                "未配置站点访问密码。本地测试可以忽略，公网部署前必须配置。",
                "在 .env 里设置 WEB_ACCESS_PASSWORD 和 WEB_SESSION_SECRET。",
            )
        )

    checks.extend(_accounts_checks(accounts_path))

    if gitignore_path.exists():
        gitignore_text = gitignore_path.read_text(encoding="utf-8", errors="ignore")
        missing_patterns = [pattern for pattern in PROTECTED_PATTERNS if pattern not in gitignore_text]
        checks.append(
            _check(
                "gitignore",
                "GitHub 安全排除",
                "ok" if not missing_patterns else "warn",
                "敏感配置和运行目录已在 .gitignore 中排除。" if not missing_patterns else "缺少排除项：" + "、".join(missing_patterns),
                "把缺少的排除项加入 .gitignore。",
            )
        )
    else:
        checks.append(_check("gitignore", "GitHub 安全排除", "warn", "没有找到 .gitignore。", "公开仓库前先添加 .gitignore。"))

    summary = {
        "ok": sum(1 for item in checks if item["status"] == "ok"),
        "warn": sum(1 for item in checks if item["status"] == "warn"),
        "error": sum(1 for item in checks if item["status"] == "error"),
    }
    return {"ok": summary["error"] == 0, "summary": summary, "checks": checks}
