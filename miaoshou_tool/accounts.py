from __future__ import annotations

import os
import secrets
import urllib.parse
import uuid
from collections.abc import Callable
from typing import Any

from batch_tiktok_collect import SHOP_ID, TEMPLATES

from .config import ACCOUNTS_PATH, ROOT
from .forms import field_text, optional_int
from .json_io import read as read_json
from .json_io import write as write_json
from .text import normalized_text


MiaoshouPost = Callable[[str, dict, tuple[str, str]], dict]


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


def matched_template_name(text: str) -> str | None:
    for name in sorted(TEMPLATES, key=lambda item: len(normalized_text(item)), reverse=True):
        if normalized_text(name) in text:
            return name
    return None


def shop_name_from_shops(shops: list[dict]) -> str:
    name_keys = ("shopName", "shop_name", "storeName", "store_name", "sellerName", "seller_name", "name", "nickName", "alias")
    for shop in shops:
        for key in name_keys:
            value = str(shop.get(key) or "").strip()
            if value:
                return value
    return ""


def discover_templates(
    credentials: tuple[str, str],
    miaoshou_post: MiaoshouPost,
    requested_shop_id: int | None = None,
) -> tuple[int, dict[str, int], str]:
    found: dict[str, int] = {}
    shop_id = requested_shop_id
    shop_name = ""
    for page in range(1, 11):
        response = miaoshou_post(
            "search_tk_collect_products",
            {"pageNo": page, "pageSize": 100, "status": "notPublished"},
            credentials,
        )
        if response.get("result") == "fail":
            raise RuntimeError(f"妙手模板自动识别失败: {response}")
        items = (response.get("data") or {}).get("detailList") or []
        for item in items:
            text = normalized_text(item)
            shops = item.get("collectBoxDetailShopList") or []
            shop_ids = [int(shop["shopId"]) for shop in shops if str(shop.get("shopId") or "").isdigit()]
            if requested_shop_id and shop_ids and requested_shop_id not in shop_ids:
                continue
            if not shop_name:
                shop_name = shop_name_from_shops(shops)
            name = matched_template_name(text)
            if name and name not in found:
                found[name] = int(item["collectBoxDetailId"])
                if shop_id is None and shop_ids:
                    shop_id = shop_ids[0]
        if len(found) == len(TEMPLATES) or len(items) < 100:
            break
    missing = [name for name in TEMPLATES if name not in found]
    if missing:
        raise RuntimeError("未自动识别模板：" + "、".join(missing) + "。请确认模板产品在对应分组里，并处于 TikTok 未发布采集箱。")
    if shop_id is None:
        raise RuntimeError("模板已找到，但没有返回妙手账号/shopId。")
    if not shop_name:
        first_detail_id = next(iter(found.values()))
        response = miaoshou_post("get_tk_shop_collect_item_info", {"detailId": first_detail_id, "shopId": shop_id}, credentials)
        info = (response.get("data") or {}).get("shopCollectItemInfo") or {}
        shop_name = shop_name_from_shops(info.get("collectBoxDetailShopList") or [])
    return shop_id, found, shop_name


def _accounts_redirect(kind: str, message: str) -> str:
    return f"/accounts?{kind}=" + urllib.parse.quote(message)


def handle_account_post(
    path: str,
    form: Any,
    config: dict[str, Any],
    pending_accounts: dict[str, dict],
    pending_lock: Any,
    discover_templates_func: Callable[[tuple[str, str], int | None], tuple[int, dict[str, int], str]],
    active_job_id_func: Callable[[str], str | None],
) -> str:
    accounts = config.setdefault("accounts", {})
    user_accounts = all_account_ids(config)

    if path == "/accounts/confirm":
        token = field_text(form, "token")
        action = field_text(form, "action", "save")
        with pending_lock:
            pending = pending_accounts.pop(token, None)
        if not pending:
            raise ValueError("确认已失效，请重新识别")
        if action != "save":
            return _accounts_redirect("message", "已取消保存")
        account_id = "miaoshou_" + uuid.uuid4().hex[:8]
        accounts[account_id] = {
            "name": pending["name"],
            "shop_id": pending["shop_id"],
            "shop_name": pending.get("shop_name") or "",
            "app_key": pending["app_key"],
            "app_secret": pending["app_secret"],
            "locked": False,
            "templates": pending["templates"],
        }
        save_accounts_config(config)
        return _accounts_redirect("message", "妙手账号已确认并保存")

    if path == "/accounts/toggle-lock":
        account_id = field_text(form, "account_id")
        if account_id not in user_accounts or account_id not in accounts:
            raise ValueError("当前用户没有这个妙手账号权限")
        accounts[account_id]["locked"] = not bool(accounts[account_id].get("locked"))
        save_accounts_config(config)
        message = "账号已上锁" if accounts[account_id]["locked"] else "账号已开锁"
        return _accounts_redirect("message", message)

    if path == "/accounts/delete":
        account_id = field_text(form, "account_id")
        if account_id not in user_accounts or account_id not in accounts:
            raise ValueError("当前用户没有这个妙手账号权限")
        if accounts[account_id].get("locked"):
            raise ValueError("这个妙手账号已上锁，开锁后才能删除")
        if active_job_id_func(account_id):
            raise ValueError("这个妙手账号正在处理任务，完成后才能删除")
        accounts.pop(account_id, None)
        for item in config.get("users", []):
            item["accounts"] = [value for value in allowed_account_ids(item) if value != account_id]
        save_accounts_config(config)
        return _accounts_redirect("message", "妙手账号已删除")

    if path in {"/accounts/rename", "/accounts/update"}:
        account_id = field_text(form, "account_id")
        name = field_text(form, "name")
        if account_id not in user_accounts or account_id not in accounts:
            raise ValueError("当前用户没有这个妙手账号权限")
        if accounts[account_id].get("locked"):
            raise ValueError("这个妙手账号已上锁，开锁后才能修改")
        if not name:
            raise ValueError("请填写妙手账号名称")
        shop_id = optional_int(field_text(form, "shop_id"), "妙手账号")
        app_key = field_text(form, "app_key", str(accounts[account_id].get("app_key") or ""))
        app_secret = field_text(form, "app_secret")
        if not app_key:
            raise ValueError("请填写 APP ID / App Key")
        if app_secret:
            accounts[account_id]["app_secret"] = app_secret
        if not accounts[account_id].get("app_secret"):
            raise ValueError("请填写 App Secret")
        template_values = {
            template_name: optional_int(field_text(form, f"template_{template_name}"), f"{template_name}模板 ID")
            for template_name in TEMPLATES
        }
        if shop_id is None or any(value is None for value in template_values.values()):
            found_shop_id, found_templates, found_shop_name = discover_templates_func((app_key, accounts[account_id]["app_secret"]), shop_id)
            shop_id = shop_id or found_shop_id
            template_values = {
                template_name: value or found_templates[template_name]
                for template_name, value in template_values.items()
            }
            accounts[account_id]["shop_name"] = found_shop_name
        accounts[account_id]["name"] = name
        accounts[account_id]["shop_id"] = shop_id
        accounts[account_id]["app_key"] = app_key
        accounts[account_id]["templates"] = template_values
        save_accounts_config(config)
        return _accounts_redirect("message", "账号信息已保存")

    name = field_text(form, "name")
    app_key = field_text(form, "app_key")
    app_secret = field_text(form, "app_secret")
    shop_id = optional_int(field_text(form, "shop_id"), "妙手账号")
    if not name or not app_key or not app_secret:
        raise ValueError("请填写妙手账号名称、APP ID / App Key 和 App Secret")
    requested_templates = {
        template_name: optional_int(field_text(form, f"template_{template_name}"), f"{template_name}模板 ID")
        for template_name in TEMPLATES
    }
    found_shop_id, found_templates, found_shop_name = discover_templates_func((app_key, app_secret), shop_id)
    shop_id = shop_id or found_shop_id
    templates = {
        template_name: requested_templates[template_name] or found_templates[template_name]
        for template_name in TEMPLATES
    }
    token = secrets.token_urlsafe(24)
    with pending_lock:
        pending_accounts[token] = {
            "name": name,
            "shop_id": shop_id,
            "shop_name": found_shop_name,
            "app_key": app_key,
            "app_secret": app_secret,
            "templates": templates,
        }
    return "/accounts/confirm?token=" + urllib.parse.quote(token)
