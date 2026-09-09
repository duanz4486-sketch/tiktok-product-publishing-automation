from __future__ import annotations

import cgi
import uuid
from datetime import datetime
from typing import Any


def create_batch_job(form: cgi.FieldStorage, username: str, deps: dict[str, Any]) -> dict[str, Any]:
    config = deps["load_accounts_config"]()
    account_ids = deps["all_account_ids"](config)
    account_id = deps["field_text"](form, "account_id")
    if account_id not in account_ids:
        raise ValueError("未找到这个妙手账号配置")
    account = (config.get("accounts") or {}).get(account_id)
    if not account:
        raise ValueError("未找到这个妙手账号配置")
    batch = deps["field_text"](form, "batch")
    template = deps["field_text"](form, "template", deps["default_template"])
    image_prefix = deps["field_text"](form, "image_prefix")
    if not batch:
        raise ValueError("请填写批次名")
    if template not in deps["templates"]:
        raise ValueError("请选择有效的产品模板")
    template_detail_id = int((account.get("templates") or {}).get(template) or 0)
    if not template_detail_id:
        raise ValueError(f"这个妙手账号没有配置「{template}」模板")
    shop_id = int(account.get("shop_id") or deps["default_shop_id"])
    app_key = str(account.get("app_key") or "").strip()
    app_secret = str(account.get("app_secret") or "").strip()
    if deps["accounts_path"].exists() and (not app_key or not app_secret):
        raise ValueError("这个妙手账号缺少 app_key/app_secret，请先补全 accounts.json")
    miaoshou_credentials = (app_key, app_secret) if app_key and app_secret else None
    limit_text = deps["field_text"](form, "limit")
    limit = int(limit_text) if limit_text else None
    dry_run = "dry_run" in form
    upload_to_oss = "upload_to_oss" in form

    job_id = datetime.now().strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:8]
    upload_dir = deps["upload_root"] / job_id
    title_path = upload_dir / "title.xlsx"
    image_root = upload_dir / "images"
    title_original_name = deps["upload_filename"](form, "title_file", "title.xlsx")
    deps["save_upload"](form, "title_file", title_path)
    _, image_source_files = deps["stage_batch_images"](form, upload_dir, image_root)
    items = deps["read_items"](title_path)
    if limit:
        items = items[:limit]
    excel_seqs = [int(item["seq"]) for item in items]
    image_root, image_prefix = deps["resolve_image_layout"](image_root, batch, excel_seqs, image_prefix)
    image_seqs = deps["image_seq_dirs"](image_root)
    preflight_failures = deps["build_preflight_failures"](items, image_root, image_seqs, include_image_only=limit is None)
    items = [item for item in items if int(item["seq"]) in image_seqs]
    process_seqs = [int(item["seq"]) for item in items]
    if not items and not preflight_failures:
        found_text = "、".join(str(seq) for seq in sorted(image_seqs)[:30]) or "没有找到序号文件夹"
        raise ValueError(f"本次图片来源里没有任何能和 Excel 序号对应的图片文件夹。当前识别到的图片序号是：{found_text}")
    total_count = len(items) + len(preflight_failures)

    with deps["jobs_lock"]:
        active_id = deps["active_job_id_unlocked"](account_id)
        if not active_id:
            deps["jobs"][job_id] = deps["batch_job_record"](
                batch,
                account_id,
                account.get("name", account_id),
                username,
                template,
                image_prefix,
                total_count,
                preflight_failures,
            )
    if active_id:
        return {"status": "active", "active_id": active_id, "account_count": len(account_ids)}
    deps["start_job"](
        job_id,
        {
            "batch": batch,
            "title_file": title_path,
            "local_image_root": image_root,
            "shop_id": shop_id,
            "image_prefix": image_prefix,
            "template": template,
            "template_detail_id": template_detail_id,
            "limit": limit,
            "dry_run": dry_run,
            "upload_to_oss": upload_to_oss,
            "seqs": process_seqs,
            "only_seqs": process_seqs,
            "source_files": [(title_path, title_original_name), *image_source_files],
            "preflight_failures": preflight_failures,
            "reuse_existing": False,
            "log_dir": deps["run_root"],
            "miaoshou_credentials": miaoshou_credentials,
        },
    )
    return {"status": "created", "job_id": job_id}
