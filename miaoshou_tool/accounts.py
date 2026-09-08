from __future__ import annotations

import os
from typing import Any

from batch_tiktok_collect import SHOP_ID, TEMPLATES

from .config import ACCOUNTS_PATH, ROOT
from .json_io import read as read_json
from .json_io import write as write_json


def load_local_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip().strip("\"'"))


def load_accounts_config() -> dict[str, Any]:
    load_local_env()
    if ACCOUNTS_PATH.exists():
        return read_json(ACCOUNTS_PATH, {}) or {}
    password = os.getenv("WEB_PASSWORD", "").strip()
    if not password:
        return {"accounts": {}}
    return {
        "accounts": {
            "default": {
                "name": "默认妙手账号",
                "shop_id": SHOP_ID,
                "templates": {name: data["detail_id"] for name, data in TEMPLATES.items()},
            }
        },
    }


def save_accounts_config(config: dict[str, Any]) -> None:
    write_json(ACCOUNTS_PATH, config)


def default_template_ids() -> dict[str, int]:
    return {name: data["detail_id"] for name, data in TEMPLATES.items()}


def all_account_ids(config: dict[str, Any] | None = None) -> list[str]:
    data = config if config is not None else load_accounts_config()
    return [str(account_id) for account_id in (data.get("accounts") or {}).keys()]


def user_record(username: str) -> dict[str, Any] | None:
    for user in load_accounts_config().get("users", []):
        if str(user.get("username", "")) == username:
            return user
    return None


def user_record_in_config(config: dict[str, Any], username: str) -> dict[str, Any] | None:
    for user in config.get("users", []):
        if str(user.get("username", "")) == username:
            return user
    return None


def allowed_account_ids(user: dict[str, Any]) -> list[str]:
    if user.get("accounts"):
        return [str(account_id) for account_id in user["accounts"]]
    if user.get("account_id"):
        return [str(user["account_id"])]
    return []


def account_credentials(account: dict[str, Any]) -> tuple[str, str]:
    app_key = str(account.get("app_key") or "").strip()
    app_secret = str(account.get("app_secret") or "").strip()
    if not app_key or not app_secret:
        raise ValueError("这个妙手账号缺少 APP ID / App Key 或 App Secret")
    return app_key, app_secret
