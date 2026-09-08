from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from batch_tiktok_collect import SHOP_ID, TEMPLATES

from .config import ACCOUNTS_PATH, ROOT
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
