from __future__ import annotations

import cgi
import html
import re
import uuid
from datetime import datetime
from typing import Any


def create_single_job(form: cgi.FieldStorage, username: str, deps: dict[str, Any]) -> dict[str, Any]:
    config = deps["load_accounts_config"]()
    account_ids = deps["all_account_ids"](config)
    account_id = deps["field_text"](form, "account_id")
    if account_id not in account_ids:
        raise ValueError("未找到这个妙手账号配置")
    account = (config.get("accounts") or {}).get(account_id)
    if not account:
        raise ValueError("未找到这个妙手账号配置")
    with deps["jobs_lock"]:
        active_id = deps["active_job_id_unlocked"](account_id)
    if active_id:
        return {"status": "active", "active_id": active_id, "account_count": len(account_ids)}

    credentials = deps["account_credentials"](account)
    cid = deps["int_field"](form, "cid", "类目 ID", 1)
    title = deps["field_text"](form, "title")
    if not 25 <= len(title) <= 255:
        raise ValueError("英文标题长度必须在 25-255 字符")
    deps["require_english"](title, "英文标题")
    notes = deps["field_text"](form, "notes")
    notes_is_fallback = False
    if notes:
        deps["require_english"](notes, "英文详情描述")
    else:
        notes = f"<p>{html.escape(title)}</p>"
        notes_is_fallback = True
    ai_suggest_applied = deps["field_text"](form, "ai_suggest_applied") == "1"
    weight = deps["decimal_field"](form, "weight", "重量", 0.001, 100)
    package_length = deps["decimal_field"](form, "package_length", "包装长度", 1, 1000)
    package_width = deps["decimal_field"](form, "package_width", "包装宽度", 1, 1000)
    package_height = deps["decimal_field"](form, "package_height", "包装高度", 1, 1000)
    shop_ids = [int(str(item.value)) for item in deps["field_list"](form, "shop_id") if str(item.value or "").isdigit()]
    if not shop_ids:
        raise ValueError("请至少选择一个店铺")
    metadata = deps["get_category_metadata"](cid, credentials, shop_ids[:3])
    product_attrs = deps["build_product_attributes"](form, metadata)

    job_id = datetime.now().strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:8]
    upload_dir = deps["upload_root"] / job_id
    sku_image_paths = deps["uploaded_sku_image_files"](form, upload_dir)
    sale_attr_id, spec_name, sku_rows = deps["parse_sku_rows"](form, sku_image_paths)
    image_files = deps["uploaded_image_files"](form, upload_dir)
    if not image_files:
        raise ValueError("请上传产品图片文件夹、多张图片或图片 ZIP")
    video_file = deps["uploaded_video_file"](form, upload_dir)
    image_prefix = deps["clean_prefix"](deps["field_text"](form, "image_prefix"))
    if not image_prefix:
        title_slug = re.sub(r"[^A-Za-z0-9._-]+", "-", title).strip("-")[:80] or "single-product"
        image_prefix = f"single/{title_slug}"
    item_num = deps["field_text"](form, "item_num", f"SINGLE-{datetime.now().strftime('%Y%m%d%H%M%S')}")[:50]

    with deps["jobs_lock"]:
        deps["jobs"][job_id] = deps["single_job_record"](
            title[:60],
            account_id,
            account.get("name", account_id),
            username,
            image_prefix,
        )
    deps["start_single_job"](
        job_id,
        {
            "credentials": credentials,
            "title": title,
            "notes": notes,
            "notes_is_fallback": notes_is_fallback,
            "cid": cid,
            "product_attrs": product_attrs,
            "metadata": metadata,
            "auto_ai": not ai_suggest_applied,
            "sale_attr_id": sale_attr_id,
            "spec_name": spec_name,
            "sku_rows": sku_rows,
            "shop_ids": shop_ids,
            "weight": weight,
            "package_length": package_length,
            "package_width": package_width,
            "package_height": package_height,
            "image_files": image_files,
            "video_file": video_file,
            "image_prefix": image_prefix,
            "item_num": item_num,
        },
    )
    return {"status": "created", "job_id": job_id}
