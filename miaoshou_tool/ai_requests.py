from __future__ import annotations

import cgi
import uuid
from datetime import datetime
from typing import Any
from urllib.parse import quote


def handle_ai_settings_form(form: cgi.FieldStorage, deps: dict[str, Any]) -> str:
    settings = deps["ai_settings_from_form"](form)
    if deps["field_text"](form, "action", "save") == "test":
        deps["test_ai_settings"](deps["settings_for_ai_test"](settings))
        return "/ai-settings?message=" + quote("AI 测试成功：当前配置可以返回图片识别 JSON。")
    deps["save_ai_settings"](settings)
    return "/ai-settings?message=" + quote("AI 设置已保存")


def suggest_single_product(form: cgi.FieldStorage, deps: dict[str, Any]) -> dict[str, Any]:
    config = deps["load_accounts_config"]()
    account_id = deps["field_text"](form, "account_id")
    account = (config.get("accounts") or {}).get(account_id)
    if not account:
        raise ValueError("请先选择有效的妙手账号")
    credentials = deps["account_credentials"](account)
    title = deps["field_text"](form, "title")
    if not title:
        raise ValueError("请先填写英文标题")
    deps["require_english"](title, "英文标题")
    notes = deps["field_text"](form, "notes")
    if notes:
        deps["require_english"](notes, "英文详情描述")
    cid = deps["int_field"](form, "cid", "类目 ID", 1)
    shop_ids = [int(str(item.value)) for item in deps["field_list"](form, "shop_id") if str(item.value or "").isdigit()]
    metadata = deps["get_category_metadata"](cid, credentials, shop_ids[:3] if shop_ids else None)
    upload_dir = deps["upload_root"] / ("ai-" + datetime.now().strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:8])
    image_files = deps["uploaded_image_files"](form, upload_dir)
    if not image_files:
        raise ValueError("请先上传产品图片，AI 需要图片才能识别软参数")
    return deps["call_deepseek_ai"](title, notes, image_files, metadata)
