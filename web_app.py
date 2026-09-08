#!/usr/bin/env python3
from __future__ import annotations

import argparse
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning, message="'cgi' is deprecated.*")
import cgi
import html
import re
import secrets
import threading
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from batch_tiktok_collect import DEFAULT_TEMPLATE, SHOP_ID, TEMPLATES, VALID_IMAGE_EXTS, natural_key, post as miaoshou_post, read_items, run_batch
from miaoshou_tool import accounts as account_module
from miaoshou_tool import ai as ai_module
from miaoshou_tool import errors as error_module
from miaoshou_tool import files as file_module
from miaoshou_tool import json_io
from miaoshou_tool import miaoshou_api
from miaoshou_tool import oss_upload
from miaoshou_tool import publishing as publishing_module
from miaoshou_tool import rendering
from miaoshou_tool import self_check

ROOT = Path(__file__).resolve().parent
UPLOAD_ROOT = ROOT / "uploads"
RUN_ROOT = ROOT / "runs"
ACCOUNTS_PATH = ROOT / "accounts.json"
AI_SETTINGS_PATH = ROOT / "ai_settings.json"
OSS_BUCKET = "duanhah-miaoshou-picture"
OSS_ENDPOINT = "oss-cn-shenzhen.aliyuncs.com"
OSS_REGION = "cn-shenzhen"
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()
ACTIVE_STATUSES = {"queued", "uploading", "ai_processing", "running"}
PENDING_ACCOUNTS: dict[str, dict] = {}
PENDING_ACCOUNTS_LOCK = threading.Lock()
CATEGORY_CACHE: dict[str, list[dict]] = {}
CATEGORY_CACHE_LOCK = threading.Lock()
SINGLE_IMAGE_LIMIT = 9
VALID_VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".webm"}
MIN_AI_DESCRIPTION_CHARS = 1000
AI_PROVIDER_PRESETS = {
    "deepseek": {
        "label": "DeepSeek",
        "model": "deepseek-v4-flash-vision-exp",
        "base_url": "https://api.deepseek.com/chat/completions",
        "env": "DEEPSEEK_API_KEY",
        "help": "适合当前流程，已支持 OpenAI 兼容和图片输入。",
    },
    "openai": {
        "label": "OpenAI",
        "model": "gpt-4.1-mini",
        "base_url": "https://api.openai.com/v1/chat/completions",
        "env": "OPENAI_API_KEY",
        "help": "需要服务器能访问 OpenAI，并选择支持图片识别的模型。",
    },
    "dashscope": {
        "label": "阿里云百炼 / 通义千问",
        "model": "qwen-vl-max",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        "env": "DASHSCOPE_API_KEY",
        "help": "API Key 必须和接口地域匹配；如使用专属工作空间，请改接口地址。",
    },
    "volcengine": {
        "label": "火山方舟 / 豆包",
        "model": "doubao-1.5-vision-pro-32k",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
        "env": "ARK_API_KEY",
        "help": "通常需要填写火山方舟实际模型名或推理接入点 ID。",
    },
    "custom": {
        "label": "自定义 OpenAI 兼容接口",
        "model": "",
        "base_url": "",
        "env": "AI_API_KEY",
        "help": "用于第三方中转或其他兼容服务，需自行填写接口地址和模型名。",
    },
}
BANNED_AI_DESCRIPTION_PATTERNS = [
    (re.compile(r"\bkids?\b", re.I), "kid/kids"),
    (re.compile(r"\bchild(?:ren)?\b", re.I), "child/children"),
    (re.compile(r"\bbab(?:y|ies)\b", re.I), "baby/babies"),
    (re.compile(r"\binfants?\b", re.I), "infant/infants"),
    (re.compile(r"\btoddlers?\b", re.I), "toddler/toddlers"),
    (re.compile(r"\bnewborns?\b", re.I), "newborn/newborns"),
    (re.compile(r"\bteens?\b", re.I), "teen/teens"),
    (re.compile(r"\bpets?\b", re.I), "pet/pets"),
]
SITE = "US"
DEFAULT_OPERATOR = "网页操作"


e = rendering.escape
alert_html = rendering.alert_html


def field_text(form: cgi.FieldStorage, name: str, default: str = "") -> str:
    field = form[name] if name in form else None
    if field is None or isinstance(field, list):
        return default
    return str(field.value or default).strip()


load_accounts_config = account_module.load_accounts_config
save_accounts_config = account_module.save_accounts_config
default_template_ids = account_module.default_template_ids
all_account_ids = account_module.all_account_ids
user_record = account_module.user_record
user_record_in_config = account_module.user_record_in_config
allowed_account_ids = account_module.allowed_account_ids
clean_prefix = file_module.clean_prefix


def save_upload(form: cgi.FieldStorage, name: str, target: Path) -> None:
    file_module.save_upload(form, name, target)


safe_upload_relative_path = file_module.safe_upload_relative_path
extract_zip = file_module.extract_zip


def stage_batch_images(form: cgi.FieldStorage, upload_dir: Path, image_root: Path) -> tuple[str, list[tuple[Path, str]]]:
    return file_module.stage_batch_images(form, upload_dir, image_root)


def load_local_env() -> None:
    account_module.load_local_env()


def oss_credentials() -> tuple[str, str, str]:
    return oss_upload.oss_credentials()


def put_oss_object(file_path: Path, object_key: str) -> None:
    oss_upload.put_oss_object(file_path, object_key)


def upload_images_to_oss(image_root: Path, image_prefix: str, seqs: list[int]) -> int:
    return oss_upload.upload_images_to_oss(image_root, image_prefix, seqs, put_object=put_oss_object)


def upload_source_files_to_oss(image_prefix: str, source_files: list[tuple[Path, str]]) -> int:
    return oss_upload.upload_source_files_to_oss(image_prefix, source_files, put_object=put_oss_object)


upload_filename = file_module.upload_filename
field_list = file_module.field_list


def decimal_field(form: cgi.FieldStorage, name: str, label: str, minimum: float | None = None, maximum: float | None = None) -> float:
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


contains_cjk = ai_module.contains_cjk
require_english = ai_module.require_english
require_ai_description_policy = ai_module.require_ai_description_policy
account_credentials = account_module.account_credentials
expect_miaoshou_success = miaoshou_api.expect_miaoshou_success
shop_display_name = miaoshou_api.shop_display_name


def get_tiktok_shops(credentials: tuple[str, str]) -> list[dict]:
    return miaoshou_api.get_tiktok_shops(credentials, miaoshou_post)


pick_warehouse = miaoshou_api.pick_warehouse


def get_default_warehouse_ids(shop_ids: list[int], credentials: tuple[str, str]) -> dict[str, str]:
    return miaoshou_api.get_default_warehouse_ids(shop_ids, credentials, miaoshou_post)


flatten_category_tree = miaoshou_api.flatten_category_tree


def load_categories(credentials: tuple[str, str]) -> list[dict]:
    with CATEGORY_CACHE_LOCK:
        return miaoshou_api.load_categories(credentials, miaoshou_post, CATEGORY_CACHE)


def get_category_metadata(cid: int, credentials: tuple[str, str], shop_ids: list[int] | None = None) -> dict:
    return miaoshou_api.get_category_metadata(cid, credentials, miaoshou_post, shop_ids)


metadata_attrs = miaoshou_api.metadata_attrs
truthy_flag = miaoshou_api.truthy_flag
attr_label = miaoshou_api.attr_label
is_required_attr = miaoshou_api.is_required_attr
category_required_notes = miaoshou_api.category_required_notes
save_uploaded_file = file_module.save_uploaded_file
uploaded_image_files = file_module.uploaded_image_files
uploaded_sku_image_files = file_module.uploaded_sku_image_files
uploaded_video_file = file_module.uploaded_video_file


def upload_single_images(files: list[Path], object_prefix: str) -> list[str]:
    return oss_upload.upload_single_images(files, object_prefix, put_object=put_oss_object)


def upload_single_video(file_path: Path | None, object_prefix: str) -> str:
    return oss_upload.upload_single_video(file_path, object_prefix, put_object=put_oss_object)


def load_ai_settings() -> dict:
    return ai_module.load_ai_settings(load_local_env)


def save_ai_settings(settings: dict) -> None:
    ai_module.save_ai_settings(settings, load_ai_settings)


image_data_url = ai_module.image_data_url
attr_prompt_rows = ai_module.attr_prompt_rows
ai_suggestion_prompt = ai_module.ai_suggestion_prompt
extract_json_object = ai_module.extract_json_object
ai_provider_label = ai_module.ai_provider_label
normalize_chat_completions_url = ai_module.normalize_chat_completions_url


def call_openai_compatible_chat(settings: dict, content: list[dict], timeout: int = 90) -> str:
    return ai_module.call_openai_compatible_chat(settings, content, timeout, urllib.request.urlopen)


def call_deepseek_ai(title: str, notes: str, image_files: list[Path], metadata: dict) -> dict:
    return ai_module.call_ai(title, notes, image_files, metadata, load_ai_settings(), call_openai_compatible_chat)


def test_ai_settings(settings: dict) -> None:
    ai_module.test_ai_settings(settings, call_openai_compatible_chat)


def ai_settings_from_form(form: cgi.FieldStorage) -> dict:
    return ai_module.ai_settings_from_form(form, field_text)


def settings_for_ai_test(posted: dict) -> dict:
    return ai_module.settings_for_ai_test(posted, load_ai_settings())


def ai_configured() -> bool:
    return ai_module.ai_configured(load_ai_settings())


def merge_ai_attributes(product_attrs: list[dict], suggestion_attrs: list[dict], metadata: dict) -> list[dict]:
    return ai_module.merge_ai_attributes(product_attrs, suggestion_attrs, metadata)


def build_common_single_product(item_num: str, credentials: tuple[str, str], title: str, notes: str, image_urls: list[str], skus: list[dict], spec_name: str, weight: float, package_length: float, package_width: float, package_height: float, video_url: str = "") -> int:
    return publishing_module.build_common_single_product(
        item_num,
        credentials,
        title,
        notes,
        image_urls,
        skus,
        spec_name,
        weight,
        package_length,
        package_width,
        package_height,
        miaoshou_post,
        video_url,
    )


def build_product_attributes(form: cgi.FieldStorage, metadata: dict) -> list[dict]:
    return publishing_module.build_product_attributes(form, metadata, field_text)


custom_value_id = publishing_module.custom_value_id


def get_site_info(detail_id: int, credentials: tuple[str, str]) -> tuple[str, dict]:
    return publishing_module.get_site_info(detail_id, credentials, miaoshou_post)


def save_site_product(detail_id: int, credentials: tuple[str, str], site_info: dict, oss_md5: str, title: str, notes: str, image_urls: list[str], cid: int, product_attrs: list[dict], sale_attr_id: str, spec_name: str, skus: list[dict], shop_ids: list[int], weight: float, package_length: float, package_width: float, package_height: float, warehouse_ids: dict[str, str] | None = None, video_url: str = "") -> None:
    publishing_module.save_site_product(
        detail_id,
        credentials,
        site_info,
        oss_md5,
        title,
        notes,
        image_urls,
        cid,
        product_attrs,
        sale_attr_id,
        spec_name,
        skus,
        shop_ids,
        weight,
        package_length,
        package_width,
        package_height,
        miaoshou_post,
        warehouse_ids,
        video_url,
    )


def claim_tiktok_to_shops(detail_id: int, shop_ids: list[int], credentials: tuple[str, str]) -> None:
    publishing_module.claim_tiktok_to_shops(detail_id, shop_ids, credentials, miaoshou_post)


def claim_common_to_tiktok_single(common_id: int, credentials: tuple[str, str]) -> int:
    return publishing_module.claim_common_to_tiktok_single(common_id, credentials, miaoshou_post)


def delete_common_collect_products(detail_ids: list[int], credentials: tuple[str, str]) -> None:
    publishing_module.delete_common_collect_products(detail_ids, credentials, miaoshou_post)


def delete_tiktok_collect_products(detail_ids: list[int], credentials: tuple[str, str]) -> None:
    publishing_module.delete_tiktok_collect_products(detail_ids, credentials, miaoshou_post)


def cleanup_created_single_product(common_id: int | None, detail_id: int | None, credentials: tuple[str, str]) -> list[str]:
    errors: list[str] = []
    if detail_id is not None:
        try:
            delete_tiktok_collect_products([detail_id], credentials)
        except Exception as exc:
            errors.append(f"TikTok 草稿删除失败：{exc!r}")
    if common_id is not None:
        try:
            delete_common_collect_products([common_id], credentials)
        except Exception as exc:
            errors.append(f"公共采集箱草稿删除失败：{exc!r}")
    return errors


resolve_skus = publishing_module.resolve_skus


def parse_sku_rows(form: cgi.FieldStorage, sku_image_paths: dict[str, Path] | None = None) -> tuple[str, str, list[dict]]:
    return publishing_module.parse_sku_rows(form, field_text, field_list, sku_image_paths)


def run_single_job(job_id: str, params: dict) -> None:
    result: dict[str, object] = {"seq": "单品", "status": "started", "image_count": len(params["image_files"])}
    common_id: int | None = None
    detail_id: int | None = None
    try:
        set_job(job_id, status="uploading")
        image_urls = upload_single_images(params["image_files"], params["image_prefix"])
        video_url = upload_single_video(params.get("video_file"), params["image_prefix"])
        for row in params["sku_rows"]:
            sku_image_path = row.get("image_path")
            if sku_image_path:
                row["image_url"] = upload_single_images([sku_image_path], f"{params['image_prefix']}/sku")[0]
        set_job(job_id, uploaded_count=len(image_urls))
        skus = resolve_skus(params["sku_rows"], image_urls, params["weight"])
        notes = params["notes"]
        product_attrs = list(params["product_attrs"])
        ai_status: dict[str, object] = {"status": "skipped", "reason": "已在页面应用 AI 建议或未请求 AI"}
        if params.get("auto_ai"):
            set_job(job_id, status="ai_processing")
            try:
                suggestion = call_deepseek_ai(
                    params["title"],
                    "" if params.get("notes_is_fallback") else notes,
                    params["image_files"],
                    params["metadata"],
                )
                if params.get("notes_is_fallback") and suggestion.get("description_html"):
                    notes = str(suggestion["description_html"])
                product_attrs = merge_ai_attributes(product_attrs, suggestion.get("attributes") or [], params["metadata"])
                ai_status = {
                    "status": "success",
                    "description": "已生成" if not params.get("notes_is_fallback") else ("已采用" if notes != params["notes"] else "未采用"),
                    "attributeCount": len(suggestion.get("attributes") or []),
                    "warnings": suggestion.get("warnings") or [],
                }
            except Exception as exc:
                ai_status = {"status": "failed", "error": readable_error_text(exc) or repr(exc)}
                result["ai"] = ai_status
                raise RuntimeError("AI 处理失败：" + ai_status["error"]) from exc
        result["ai"] = ai_status
        set_job(job_id, status="running")
        common_id = build_common_single_product(
            params["item_num"],
            params["credentials"],
            params["title"],
            notes,
            image_urls,
            skus,
            params["spec_name"],
            params["weight"],
            params["package_length"],
            params["package_width"],
            params["package_height"],
            video_url,
        )
        detail_id = claim_common_to_tiktok_single(common_id, params["credentials"])
        oss_md5, site_info = get_site_info(detail_id, params["credentials"])
        warehouse_ids = get_default_warehouse_ids(params["shop_ids"], params["credentials"])
        save_site_product(
            detail_id,
            params["credentials"],
            site_info,
            oss_md5,
            params["title"],
            notes,
            image_urls,
            params["cid"],
            product_attrs,
            params["sale_attr_id"],
            params["spec_name"],
            skus,
            params["shop_ids"],
            params["weight"],
            params["package_length"],
            params["package_width"],
            params["package_height"],
            warehouse_ids,
            video_url,
        )
        claim_tiktok_to_shops(detail_id, params["shop_ids"], params["credentials"])
        shop_results = []
        for shop_id in params["shop_ids"]:
            try:
                miaoshou_post("get_tk_shop_collect_item_info", {"detailId": detail_id, "shopId": shop_id}, params["credentials"])
                shop_results.append({"shopId": shop_id, "status": "success"})
            except Exception as exc:
                shop_results.append({"shopId": shop_id, "status": "failed", "error": repr(exc)})
        result.update(
            {
                "status": "success" if all(item["status"] == "success" for item in shop_results) else "done_with_errors",
                "commonCollectBoxDetailId": common_id,
                "tiktokDetailId": detail_id,
                "shopResults": shop_results,
                "image_count": len(image_urls),
            }
        )
    except Exception as exc:
        result.update({"status": "failed", "error": repr(exc)})
        cleanup_errors = cleanup_created_single_product(common_id, detail_id, params["credentials"])
        if cleanup_errors:
            result["cleanupErrors"] = cleanup_errors
    log_path = RUN_ROOT / f"single_{job_id}.json"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    json_io.write(log_path, json_io.job_log(result, [result]))
    set_job(
        job_id,
        status="done" if result["status"] == "success" else "failed",
        done_count=1,
        total_count=1,
        results=[result],
        summary=result,
        log_path=str(log_path.resolve()),
        finished_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


def start_single_job(job_id: str, params: dict) -> None:
    thread = threading.Thread(target=run_single_job, args=(job_id, params), daemon=True)
    thread.start()


image_seq_dirs = file_module.image_seq_dirs
image_count_for_seq = file_module.image_count_for_seq
build_preflight_failures = file_module.build_preflight_failures
find_image_base = file_module.find_image_base
resolve_image_layout = file_module.resolve_image_layout


def set_job(job_id: str, **values) -> None:
    with JOBS_LOCK:
        JOBS[job_id].update(values)


def active_job_id_unlocked(account_id: str | None = None) -> str | None:
    for job_id, job in reversed(list(JOBS.items())):
        if job.get("status") in ACTIVE_STATUSES and (account_id is None or job.get("account_id") == account_id):
            return job_id
    return None


def progress_html(job: dict) -> str:
    done = int(job.get("done_count") or 0)
    total = int(job.get("total_count") or 0)
    percent = min(100, round(done * 100 / total)) if total else 0
    return f"""
  <div class="progress-head">
    <span>当前进度</span>
    <strong>{done} / {total or "未知"} · {percent}%</strong>
  </div>
  <div class="progress" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="{percent}" aria-label="任务处理进度">
    <div class="bar" style="width: {percent}%"></div>
  </div>
  <div class="progress-meta">
    <span>源文件 {e(job.get("source_uploaded_count", 0))}</span>
    <span>图片 {e(job.get("uploaded_count", 0))}</span>
    <span>预检失败 {e(job.get("preflight_failed_count", 0))}</span>
  </div>"""


STATUS_LABELS = rendering.STATUS_LABELS
status_label = rendering.status_label
status_badge = rendering.status_badge


readable_error_text = error_module.readable_error_text
readable_job_error = error_module.readable_job_error
ai_status_text = error_module.ai_status_text


def job_count_text(job: dict) -> str:
    done = int(job.get("done_count") or 0)
    total = int(job.get("total_count") or 0)
    return f"{done} / {total}" if total else str(done)


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


def optional_int(value: str, label: str) -> int | None:
    value = str(value or "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"{label} 必须是数字")


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


def discover_templates(credentials: tuple[str, str], requested_shop_id: int | None = None) -> tuple[int, dict[str, int], str]:
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


def run_job(job_id: str, params: dict) -> None:
    def progress(result: dict) -> None:
        with JOBS_LOCK:
            job = JOBS[job_id]
            job["done_count"] = job.get("done_count", 0) + 1
            job.setdefault("results", []).append(result)

    try:
        seqs = params.pop("seqs")
        source_files = params.pop("source_files", [])
        preflight_failures = params.pop("preflight_failures", [])
        if params.pop("upload_to_oss", False):
            set_job(job_id, status="uploading")
            source_uploaded_count = upload_source_files_to_oss(params["image_prefix"], source_files)
            uploaded_count = upload_images_to_oss(params["local_image_root"], params["image_prefix"], seqs)
            set_job(job_id, uploaded_count=uploaded_count, source_uploaded_count=source_uploaded_count)
        if not seqs:
            run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_path = RUN_ROOT / f"{params['batch']}_{run_id}.json"
            summary = {
                "batch": params["batch"],
                "template": params["template"],
                "total": len(preflight_failures),
                "success": 0,
                "dryRunOk": 0,
                "failed": preflight_failures,
                "logPath": str(log_path.resolve()),
            }
            log_path.parent.mkdir(parents=True, exist_ok=True)
            json_io.write(log_path, json_io.job_log(summary, preflight_failures))
            set_job(job_id, status="done_with_errors", summary=summary, log_path=summary["logPath"])
            return
        set_job(job_id, status="running", started_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        summary = run_batch(progress=progress, **params)
        if preflight_failures:
            log_path = Path(summary["logPath"])
            data = json_io.read(log_path, {}) or {}
            data["results"] = preflight_failures + (data.get("results") or [])
            summary["total"] = len(data["results"])
            summary["failed"] = preflight_failures + (summary.get("failed") or [])
            data["summary"] = summary
            json_io.write(log_path, data)
        status = "done" if not summary["failed"] else "done_with_errors"
        set_job(job_id, status=status, summary=summary, log_path=summary["logPath"])
    except Exception as exc:
        set_job(job_id, status="failed", error=repr(exc))

    set_job(job_id, finished_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


def start_job(job_id: str, params: dict) -> None:
    thread = threading.Thread(target=run_job, args=(job_id, params), daemon=True)
    thread.start()


def render_page(title: str, body: str, refresh: bool = False, header_right: str = "") -> bytes:
    meta = '<meta http-equiv="refresh" content="3">' if refresh else ""
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  {meta}
  <title>{e(title)}</title>
  <style>
    :root {{
      --ink: #17212b;
      --muted: #627180;
      --line: #d9e1e8;
      --paper: #f7f9fb;
      --panel: #ffffff;
      --blue: #1f64d8;
      --green: #18745a;
      --red: #b42318;
      --amber: #946200;
      --focus: #00a2a8;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Microsoft YaHei", "Segoe UI", Arial, sans-serif;
      color: var(--ink);
      background: var(--paper);
    }}
    header {{
      padding: 22px 32px;
      background: #fff;
      border-bottom: 1px solid var(--line);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
    }}
    h1 {{ margin: 0; font-size: 22px; font-weight: 700; }}
    main {{ max-width: 1080px; margin: 0 auto; padding: 24px; }}
    section {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 20px;
      margin-bottom: 16px;
    }}
    h2 {{ margin: 0 0 16px; font-size: 17px; }}
    fieldset {{ border: 0; margin: 0; padding: 0; }}
    fieldset:disabled {{ opacity: .55; }}
    label {{ display: block; color: var(--muted); font-size: 13px; margin-bottom: 6px; }}
    input, select, textarea {{
      width: 100%;
      min-height: 40px;
      border: 1px solid #b9c5d0;
      border-radius: 6px;
      padding: 8px 10px;
      background: #fff;
      color: var(--ink);
      font: inherit;
    }}
    textarea {{ min-height: 120px; resize: vertical; line-height: 1.5; }}
    input:focus, select:focus, textarea:focus, button:focus {{ outline: 2px solid var(--focus); outline-offset: 2px; }}
    .grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }}
    .grid-three {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }}
    .wide {{ grid-column: 1 / -1; }}
    .row {{ display: flex; align-items: center; gap: 10px; }}
    .row input[type="checkbox"] {{ width: 18px; min-height: 18px; }}
    .inline-form {{ display: grid; grid-template-columns: minmax(140px, 1fr) 120px auto; gap: 8px; align-items: center; }}
    .account-edit-form {{ display: grid; grid-template-columns: repeat(2, minmax(160px, 1fr)); gap: 10px; align-items: end; min-width: 560px; }}
    .account-edit-form .actions-row {{ grid-column: 1 / -1; display: flex; gap: 8px; }}
    .inline-form button {{ min-height: 40px; }}
    .danger {{ background: #fff1f0; color: var(--red); border: 1px solid #f3b4ad; }}
    .account-actions {{ display: grid; gap: 8px; }}
    .lock-switch {{
      min-height: 38px;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      background: #fff;
      color: var(--ink);
      border: 1px solid var(--line);
      font-weight: 600;
    }}
    .lock-track {{
      width: 42px;
      height: 22px;
      border-radius: 999px;
      background: #8a98a8;
      position: relative;
      transition: background .22s ease;
    }}
    .lock-track::after {{
      content: "";
      width: 18px;
      height: 18px;
      border-radius: 50%;
      background: #fff;
      position: absolute;
      left: 2px;
      top: 2px;
      box-shadow: 0 1px 3px rgba(23, 33, 43, .25);
      transition: transform .22s ease;
    }}
    .lock-switch.locked .lock-track {{ background: var(--green); }}
    .lock-switch.locked .lock-track::after {{ transform: translateX(20px); }}
    input[readonly] {{ background: #f2f5f8; color: var(--muted); }}
    .hint {{ color: var(--muted); font-size: 13px; line-height: 1.6; }}
    button {{
      min-height: 42px;
      border: 0;
      border-radius: 6px;
      padding: 0 18px;
      background: var(--blue);
      color: white;
      font-weight: 700;
      cursor: pointer;
    }}
    button:disabled {{ background: #8a98a8; cursor: not-allowed; }}
    .ghost {{ background: #eef3f7; color: var(--ink); border: 1px solid var(--line); }}
    .account {{ position: relative; }}
    .account summary {{ list-style: none; cursor: pointer; }}
    .account summary::-webkit-details-marker {{ display: none; }}
    .avatar {{
      width: 42px;
      height: 42px;
      border-radius: 50%;
      display: grid;
      place-items: center;
      background: #1f64d8;
      color: #fff;
      font-weight: 700;
      box-shadow: 0 2px 8px rgba(31, 100, 216, .22);
    }}
    .account-panel {{
      position: absolute;
      right: 0;
      top: 52px;
      width: 260px;
      padding: 16px;
      background: #fff;
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: 0 12px 32px rgba(23, 33, 43, .14);
      z-index: 10;
    }}
    .account-name {{ margin: 0 0 4px; font-weight: 700; }}
    .account-meta {{ margin: 0 0 14px; color: var(--muted); font-size: 13px; }}
    .account-link {{ display: block; margin: 0 0 12px; }}
    .notice {{ border-left: 4px solid var(--amber); padding-left: 12px; }}
    .progress {{ height: 14px; border: 1px solid var(--line); border-radius: 999px; background: #eef3f7; overflow: hidden; }}
    .bar {{ height: 100%; background: linear-gradient(90deg, var(--blue), var(--focus)); transition: width .2s ease; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ padding: 10px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }}
    th {{ color: var(--muted); font-weight: 600; }}
    a {{ color: var(--blue); text-decoration: none; }}
    .status {{ font-weight: 700; }}
    .done, .dry_run_ok, .success {{ color: var(--green); }}
    .failed, .done_with_errors {{ color: var(--red); }}
    .running, .started, .uploading {{ color: var(--amber); }}
    .actions {{ margin-top: 16px; }}
    .top-nav {{ display: flex; gap: 10px; margin-bottom: 16px; }}
    .top-nav a {{ padding: 10px 12px; border: 1px solid var(--line); border-radius: 6px; background: #fff; }}
    .required-mark {{ color: var(--red); font-weight: 700; }}
    .mini-button {{ min-height: 34px; padding: 0 12px; }}
    .shop-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px 14px; }}
    .shop-grid label {{ display: flex; align-items: center; gap: 8px; color: var(--ink); }}
    .shop-grid input {{ width: 18px; min-height: 18px; }}
    .sku-row {{ display: grid; grid-template-columns: 1.4fr .8fr .8fr 1.4fr auto; gap: 8px; align-items: end; margin-bottom: 8px; }}
    .category-picker {{
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      overflow-x: auto;
      margin-top: 10px;
    }}
    .category-columns {{ display: grid; grid-auto-flow: column; grid-auto-columns: minmax(220px, 1fr); min-height: 220px; }}
    .category-column {{ border-right: 1px solid var(--line); padding: 8px; max-height: 260px; overflow-y: auto; }}
    .category-column:last-child {{ border-right: 0; }}
    .category-item {{
      width: 100%;
      min-height: 34px;
      padding: 6px 8px;
      border: 0;
      border-radius: 4px;
      background: transparent;
      color: var(--ink);
      text-align: left;
      font-weight: 500;
    }}
    .category-item:hover, .category-item.active {{ background: #e8f2ff; color: var(--blue); }}
    .category-item.leaf::before {{ content: "✓ "; color: var(--focus); }}
    @media (max-width: 720px) {{
      header {{ padding: 18px; }}
      main {{ padding: 14px; }}
      .grid, .grid-three, .shop-grid, .sku-row {{ grid-template-columns: 1fr; }}
      table {{ display: block; overflow-x: auto; }}
    }}
    :root {{
      --bg: #f4f7fa;
      --surface: #ffffff;
      --surface-2: #f8fafc;
      --text: #13202c;
      --text-soft: #5d6b78;
      --border: #d7e0e8;
      --border-strong: #b8c6d3;
      --accent: #165dff;
      --accent-strong: #1048c5;
      --accent-soft: #eaf1ff;
      --ok: #0f7a5a;
      --ok-soft: #e9f7f1;
      --warn: #9a6400;
      --warn-soft: #fff6df;
      --bad: #b42318;
      --bad-soft: #fff0ed;
      --shadow-sm: 0 1px 2px rgba(16, 32, 48, .06);
      --shadow-md: 0 16px 42px rgba(16, 32, 48, .12);
    }}
    body {{ background: var(--bg); color: var(--text); font-size: 14px; }}
    header.app-header {{
      position: sticky;
      top: 0;
      z-index: 20;
      padding: 14px 28px;
      background: rgba(255, 255, 255, .96);
      backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--border);
    }}
    .brand {{ display: flex; align-items: center; gap: 12px; min-width: 260px; }}
    .brand-mark {{
      width: 38px;
      height: 38px;
      border-radius: 10px;
      display: grid;
      place-items: center;
      background: #102033;
      color: #fff;
      font-weight: 800;
      letter-spacing: 0;
    }}
    .brand-title {{ display: block; font-size: 18px; line-height: 1.2; }}
    .brand-subtitle {{ display: block; margin-top: 2px; color: var(--text-soft); font-size: 12px; font-weight: 500; }}
    main {{ max-width: 1180px; padding: 24px; }}
    section {{
      border-color: var(--border);
      border-radius: 10px;
      box-shadow: var(--shadow-sm);
    }}
    section h2 {{ font-size: 18px; letter-spacing: 0; }}
    .section-head {{ display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; margin-bottom: 16px; }}
    .section-head h2 {{ margin-bottom: 4px; }}
    .section-kicker {{ margin: 0; color: var(--text-soft); font-size: 13px; line-height: 1.6; }}
    .top-nav {{
      position: sticky;
      top: 67px;
      z-index: 15;
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      padding: 10px 0 14px;
      margin-bottom: 8px;
      background: linear-gradient(var(--bg) 72%, rgba(244, 247, 250, 0));
    }}
    .top-nav a {{
      display: inline-flex;
      align-items: center;
      gap: 7px;
      border-radius: 999px;
      padding: 9px 14px;
      color: var(--text-soft);
      background: var(--surface);
      border-color: var(--border);
      font-weight: 700;
      box-shadow: var(--shadow-sm);
    }}
    .top-nav a.active {{ color: var(--accent); background: var(--accent-soft); border-color: #bad0ff; }}
    .nav-badge {{ padding: 2px 6px; border-radius: 999px; font-size: 11px; line-height: 1.2; font-weight: 800; }}
    .nav-badge.stable {{ color: var(--ok); background: var(--ok-soft); }}
    .nav-badge.beta {{ color: var(--warn); background: var(--warn-soft); }}
    input, select, textarea {{
      border-color: var(--border-strong);
      border-radius: 8px;
      min-height: 42px;
      transition: border-color .16s ease, box-shadow .16s ease, background .16s ease;
    }}
    input:hover, select:hover, textarea:hover {{ border-color: #8797a7; }}
    input:focus, select:focus, textarea:focus, button:focus {{ outline: 3px solid rgba(0, 162, 168, .18); border-color: var(--focus); }}
    label {{ color: #344556; font-weight: 700; }}
    .field-help {{ margin: 6px 0 0; color: var(--text-soft); font-size: 12px; line-height: 1.5; }}
    button {{ border-radius: 8px; background: var(--accent); transition: background .16s ease, transform .16s ease, box-shadow .16s ease; }}
    button:hover:not(:disabled) {{ background: var(--accent-strong); box-shadow: 0 8px 18px rgba(22, 93, 255, .18); transform: translateY(-1px); }}
    .ghost {{ background: #f1f5f9; border-color: var(--border); color: var(--text); }}
    .ghost:hover:not(:disabled) {{ background: #e8eef5; box-shadow: none; }}
    .danger {{ background: var(--bad-soft); color: var(--bad); border-color: #f0b8b1; }}
    .danger:hover:not(:disabled) {{ background: #ffe1dd; box-shadow: none; }}
    .form-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px 16px; }}
    .field-card {{ padding: 12px; border: 1px solid var(--border); border-radius: 9px; background: var(--surface-2); }}
    .upload-choice-row {{ display: flex; align-items: center; flex-wrap: wrap; gap: 10px; margin-top: 8px; }}
    .upload-actions {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 10px; }}
    .upload-button {{ display: inline-flex; align-items: center; justify-content: center; min-height: 38px; padding: 0 14px; border: 1px solid var(--border); border-radius: 8px; background: #fff; color: var(--text); font-weight: 700; cursor: pointer; }}
    .upload-button:hover {{ border-color: var(--accent); color: var(--accent); }}
    .file-choice-name {{ color: var(--text-soft); font-size: 13px; }}
    .hidden-file {{ position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }}
    .check-row {{ display: flex; align-items: flex-start; gap: 10px; padding: 12px; border: 1px solid var(--border); border-radius: 9px; background: var(--surface-2); }}
    .check-row input {{ width: 18px; min-height: 18px; margin-top: 2px; flex: 0 0 auto; }}
    .check-row label {{ margin: 0; color: var(--text); }}
    .alert {{ border: 1px solid var(--border); border-left-width: 4px; border-radius: 8px; padding: 12px 14px; margin: 12px 0; line-height: 1.65; }}
    .alert-info {{ background: #eef6ff; border-color: #bfdcff; color: #183b66; }}
    .alert-warn {{ background: var(--warn-soft); border-color: #f2d288; color: #624100; }}
    .alert-error {{ background: var(--bad-soft); border-color: #f0b8b1; color: var(--bad); }}
    .alert-success {{ background: var(--ok-soft); border-color: #a8dec7; color: var(--ok); }}
    .progress-head {{ display: flex; justify-content: space-between; gap: 12px; margin: 10px 0 6px; color: var(--text-soft); font-size: 13px; }}
    .progress-head strong {{ color: var(--text); }}
    .progress {{ height: 12px; border: 0; background: #e5edf5; }}
    .bar {{ background: linear-gradient(90deg, #165dff, #00a2a8); }}
    .progress-meta {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; color: var(--text-soft); font-size: 12px; }}
    .progress-meta span {{ padding: 3px 8px; border-radius: 999px; background: var(--surface-2); border: 1px solid var(--border); }}
    .badge {{ display: inline-flex; align-items: center; min-height: 24px; padding: 3px 9px; border-radius: 999px; font-weight: 800; font-size: 12px; white-space: nowrap; }}
    .badge.done, .badge.success, .badge.dry_run_ok, .badge.ok {{ color: var(--ok); background: var(--ok-soft); }}
    .badge.running, .badge.started, .badge.uploading, .badge.queued, .badge.warn {{ color: var(--warn); background: var(--warn-soft); }}
    .badge.failed, .badge.done_with_errors, .badge.error {{ color: var(--bad); background: var(--bad-soft); }}
    .table-wrap {{ width: 100%; overflow-x: auto; border: 1px solid var(--border); border-radius: 10px; background: var(--surface); }}
    .table-wrap table {{ min-width: 860px; }}
    th {{ color: #425466; background: #f6f9fc; font-size: 12px; text-transform: none; }}
    td {{ line-height: 1.55; }}
    .error-cell {{ max-width: 360px; word-break: break-word; color: var(--bad); }}
    .empty-row {{ color: var(--text-soft); text-align: center; padding: 20px; }}
    .account summary {{ display: flex; align-items: center; gap: 10px; }}
    .account-summary-text {{ display: grid; gap: 2px; line-height: 1.1; }}
    .account-summary-text strong {{ font-size: 13px; color: var(--text); }}
    .account-summary-text small {{ color: var(--text-soft); font-size: 12px; }}
    .avatar {{ width: 36px; height: 36px; background: #102033; box-shadow: none; }}
    .account-panel {{ width: 286px; border-radius: 12px; box-shadow: var(--shadow-md); }}
    .account-name {{ font-size: 15px; }}
    .account-link {{ padding: 9px 10px; border-radius: 8px; color: var(--text); font-weight: 700; }}
    .account-link:hover {{ background: var(--surface-2); color: var(--accent); }}
    .account-edit-form {{ min-width: 640px; }}
    .template-grid {{ display: grid; grid-template-columns: repeat(3, minmax(150px, 1fr)); gap: 10px; }}
    .template-grid.wide {{ grid-column: 1 / -1; }}
    .lock-switch {{ border-radius: 999px; }}
    .category-picker {{ border-radius: 10px; }}
    .category-column {{ background: var(--surface); }}
    .category-item {{ border-radius: 7px; }}
    .sku-row {{ padding: 10px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface-2); }}
    @media (max-width: 780px) {{
      header.app-header {{ align-items: flex-start; padding: 12px 16px; }}
      .brand {{ min-width: 0; }}
      .brand-title {{ font-size: 16px; }}
      .brand-subtitle {{ display: none; }}
      .account-summary-text {{ display: none; }}
      .top-nav {{ top: 63px; overflow-x: auto; flex-wrap: nowrap; padding-bottom: 10px; }}
      .top-nav a {{ white-space: nowrap; }}
      .section-head {{ display: block; }}
      .form-grid, .grid, .grid-three, .shop-grid, .sku-row, .account-edit-form, .template-grid {{ grid-template-columns: 1fr; min-width: 0; }}
      .account-panel {{ right: -4px; width: min(286px, calc(100vw - 24px)); }}
      .table-wrap table {{ min-width: 760px; }}
    }}
    @media (prefers-reduced-motion: reduce) {{
      *, *::before, *::after {{ transition: none !important; scroll-behavior: auto !important; }}
    }}
  </style>
</head>
<body>
  <header class="app-header">
    <div class="brand">
      <span class="brand-mark">MS</span>
      <h1><span class="brand-title">妙手 TikTok 批量上货工具</span><span class="brand-subtitle">团队运营工作台</span></h1>
    </div>
    {header_right}
  </header>
  <main>{body}</main>
  <script>
    document.querySelectorAll('form[data-submit-lock]').forEach((form) => {{
      form.addEventListener('submit', (event) => {{
        const button = event.submitter || form.querySelector('button[type="submit"]');
        if (button) {{
          button.disabled = true;
          button.textContent = button.dataset.workingLabel || '处理中...';
        }}
      }});
    }});
  </script>
</body>
</html>""".encode("utf-8")


def render_account_menu(username: str | None, account_count: int) -> str:
    return rendering.account_menu(account_count)


def render_top_nav(current: str = "batch") -> str:
    return rendering.top_nav(current)


def render_setup_needed() -> bytes:
    body = """
<section>
  <h2>还没有配置妙手账号</h2>
  <p class="hint">请先进入「妙手账号管理」新增妙手账号。真实妙手密钥只保存在本机 accounts.json，不要放进 GitHub。</p>
  <p><a href="/accounts">去配置妙手账号</a>　<a href="/check">查看系统自检</a></p>
</section>"""
    return render_page("需要配置", body)


def render_release_check(username: str) -> bytes:
    report = self_check.run_release_check(ROOT, ACCOUNTS_PATH)
    summary = report["summary"]
    rows = "".join(
        f"""<tr>
          <td>{status_badge(item["status"])}</td>
          <td>{e(item["label"])}</td>
          <td>{e(item["message"])}</td>
          <td>{e(item.get("fix") if item["status"] != "ok" and item.get("fix") else "无需处理")}</td>
        </tr>"""
        for item in report["checks"]
    )
    overall = "success" if report["ok"] else "error"
    overall_text = "基础配置可以运行模板批量上传。" if report["ok"] else "还有必需配置未完成，请先处理红色失败项。"
    body = f"""
{render_top_nav("check")}
<section>
  <div class="section-head">
    <div>
      <h2>系统自检</h2>
      <p class="section-kicker">用于公开部署或换电脑部署后，快速确认模板批量上传入口是否准备好。</p>
    </div>
  </div>
  {alert_html(overall, overall_text)}
  <div class="progress-meta">
    <span>正常 {e(summary["ok"])}</span>
    <span>提醒 {e(summary["warn"])}</span>
    <span>失败 {e(summary["error"])}</span>
  </div>
</section>
<section>
  <div class="section-head">
    <div>
      <h2>检查结果</h2>
      <p class="section-kicker">自检只检查配置是否齐全，不会调用妙手创建产品，也不会显示任何密钥明文。</p>
    </div>
  </div>
  <div class="table-wrap">
    <table>
      <thead><tr><th>状态</th><th>项目</th><th>结果</th><th>处理方式</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
</section>"""
    return render_page("系统自检", body, header_right=render_account_menu(username, len(all_account_ids())))


def render_account_row(account_id: str, account: dict) -> str:
    locked = bool(account.get("locked"))
    readonly = "readonly" if locked else ""
    disabled = "disabled" if locked else ""
    lock_class = "locked" if locked else "unlocked"
    lock_text = "已上锁，点击开锁" if locked else "未上锁，点击上锁"
    shop_label = e(account.get("shop_id") or "")
    if account.get("shop_name"):
        shop_label += f"<br><span class=\"hint\">{e(account.get('shop_name'))}</span>"
    templates = account.get("templates") or {}
    template_inputs = "".join(
        f"""<div>
                <label>{e(name)}模板 ID</label>
                <input name="template_{e(name)}" type="number" value="{e(templates.get(name) or '')}" placeholder="留空自动识别" {readonly}>
              </div>"""
        for name, data in TEMPLATES.items()
    )
    return f"""<tr>
          <td>{e(account.get("name", account_id))}</td>
          <td>{shop_label}</td>
          <td>{e(masked_app_key(account.get("app_key")))} / {'Secret 已配置' if account.get("app_secret") else '缺少 Secret'}</td>
          <td>
            <form action="/accounts/toggle-lock" method="post" data-submit-lock>
              <input type="hidden" name="account_id" value="{e(account_id)}">
              <button type="submit" class="lock-switch {lock_class}" data-working-label="正在切换账号锁...">
                <span class="lock-track"></span><span>{lock_text}</span>
              </button>
            </form>
          </td>
          <td>
            <div class="account-actions">
            <form action="/accounts/update" method="post" class="account-edit-form" data-submit-lock>
              <input type="hidden" name="account_id" value="{e(account_id)}">
              <div>
                <label>妙手账号名称</label>
                <input name="name" value="{e(account.get('name', account_id))}" required {readonly}>
              </div>
              <div>
                <label>妙手账号</label>
                <input name="shop_id" type="number" value="{e(account.get('shop_id') or '')}" placeholder="留空自动识别" {readonly}>
              </div>
              <div>
                <label>APP ID / App Key</label>
                <input name="app_key" type="password" placeholder="留空不改" autocomplete="new-password" {readonly}>
              </div>
              <div>
                <label>App Secret</label>
                <input name="app_secret" type="password" placeholder="留空不改" autocomplete="new-password" {readonly}>
              </div>
              {template_inputs}
              <div class="actions-row"><button type="submit" class="ghost" data-working-label="正在保存..." {disabled}>保存</button></div>
            </form>
            <form action="/accounts/delete" method="post" onsubmit="return confirm('确认删除这个妙手账号？')">
              <input type="hidden" name="account_id" value="{e(account_id)}">
              <button type="submit" class="danger" {disabled}>删除</button>
            </form>
            </div>
          </td>
        </tr>"""


def render_accounts(username: str, message: str = "", error: str = "") -> bytes:
    config = load_accounts_config()
    accounts = config.get("accounts", {})
    account_ids = all_account_ids(config)
    rows = "".join(
        render_account_row(account_id, account)
        for account_id, account in ((account_id, accounts[account_id]) for account_id in account_ids if account_id in accounts)
    )
    if not rows:
        rows = '<tr><td colspan="5" class="empty-row">还没有妙手账号</td></tr>'
    template_inputs = "\n".join(
        f"""<div>
        <label for="template_{e(name)}">{e(name)}模板 ID</label>
        <input id="template_{e(name)}" name="template_{e(name)}" type="number" placeholder="留空自动识别">
      </div>"""
        for name, data in TEMPLATES.items()
    )
    message_html = f'<div class="alert alert-success">{e(message)}</div>' if message else ""
    error_html = f'<div class="alert alert-error">{e(error)}</div>' if error else ""
    header_right = render_account_menu(username, len(account_ids))
    body = f"""
{render_top_nav("accounts")}
<section>
  <div class="section-head">
    <div>
      <h2>妙手账号管理</h2>
      <p class="section-kicker">一个网页账号可以保存多个妙手账号；上锁后不能修改或删除，适合调试稳定后的账号。</p>
    </div>
  </div>
  {message_html}
  {error_html}
  <div class="table-wrap">
    <table>
      <thead><tr><th>妙手账号名称</th><th>妙手账号</th><th>接口应用</th><th>账号锁</th><th>修改信息</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
</section>
<section>
  <div class="section-head">
    <div>
      <h2>新增妙手账号</h2>
      <p class="section-kicker">保存前会先用 App Key 和 App Secret 识别店铺与模板，确认无误后再写入本地配置。</p>
    </div>
  </div>
  <form action="/accounts/add" method="post" data-submit-lock>
    <div class="form-grid">
      <div class="field-card">
        <label for="name">妙手账号名称</label>
        <input id="name" name="name" required placeholder="例如：小王账号、美国店1号">
        <p class="field-help">只显示在网页下拉框里，方便团队切换。</p>
      </div>
      <div class="field-card">
        <label for="shop_id">妙手账号</label>
        <input id="shop_id" name="shop_id" type="number" placeholder="留空自动识别">
        <p class="field-help">不确定就留空，程序会从妙手接口识别。</p>
      </div>
      <div class="field-card">
        <label for="app_key">APP ID / App Key</label>
        <input id="app_key" name="app_key" type="password" required autocomplete="off">
        <p class="field-help">填妙手开放平台应用列表里的 APP ID。</p>
      </div>
      <div class="field-card">
        <label for="app_secret">App Secret</label>
        <input id="app_secret" name="app_secret" type="password" required autocomplete="off">
        <p class="field-help">保存后页面不会展示明文。</p>
      </div>
      {template_inputs}
      <div class="alert alert-info wide">妙手账号名称只给网页下拉框使用；妙手开放平台里的 APP ID 填到「APP ID / App Key」，App Secret 填到「App Secret」。妙手账号和模板 ID 可留空，程序会按「大地毯、非定制毛毯、定制毛毯」三个关键词自动识别。</div>
    </div>
    <div class="actions"><button type="submit" data-working-label="正在识别账号...">识别并保存</button></div>
  </form>
</section>"""
    return render_page("妙手账号管理", body, header_right=header_right)


def render_account_confirm(username: str, token: str) -> bytes:
    with PENDING_ACCOUNTS_LOCK:
        pending = PENDING_ACCOUNTS.get(token)
    if not pending:
        return render_page("确认已失效", '<section><h2>确认已失效</h2><p><a href="/accounts">返回妙手账号管理</a></p></section>')
    templates = pending.get("templates") or {}
    template_rows = "".join(
        f"<tr><td>{e(name)}</td><td>{e(templates.get(name))}</td></tr>"
        for name in TEMPLATES
    )
    shop_name = pending.get("shop_name") or "妙手接口未返回店铺名称，请核对 shopId"
    body = f"""
{render_top_nav("accounts")}
<section>
  <div class="section-head">
    <div>
      <h2>确认妙手账号</h2>
      <p class="section-kicker">请确认识别结果属于你要保存的妙手账号。确认后才会写入本地配置；取消则不会保存。</p>
    </div>
  </div>
  <div class="table-wrap">
    <table>
      <tbody>
        <tr><th>妙手账号名称</th><td>{e(pending.get("name"))}</td></tr>
        <tr><th>识别到的店铺名称</th><td>{e(shop_name)}</td></tr>
        <tr><th>识别到的 shopId</th><td>{e(pending.get("shop_id"))}</td></tr>
        <tr><th>接口应用</th><td>{e(masked_app_key(pending.get("app_key")))} / Secret 已配置</td></tr>
      </tbody>
    </table>
  </div>
</section>
<section>
  <div class="section-head">
    <div>
      <h2>识别到的模板</h2>
      <p class="section-kicker">模板按“大地毯、非定制毛毯、定制毛毯”关键词识别。</p>
    </div>
  </div>
  <div class="table-wrap">
    <table>
      <thead><tr><th>产品模板</th><th>模板 ID</th></tr></thead>
      <tbody>{template_rows}</tbody>
    </table>
  </div>
  <form action="/accounts/confirm" method="post" class="actions" data-submit-lock>
    <input type="hidden" name="token" value="{e(token)}">
    <button type="submit" name="action" value="save" data-working-label="正在保存账号...">确认保存</button>
    <button type="submit" name="action" value="cancel" class="ghost">取消</button>
  </form>
</section>"""
    return render_page("确认妙手账号", body, header_right=render_account_menu(username, len(all_account_ids())))


def render_home(username: str) -> bytes:
    config = load_accounts_config()
    account_ids = all_account_ids(config)
    accounts = config.get("accounts", {})
    available_accounts = [(account_id, accounts[account_id]) for account_id in account_ids if account_id in accounts]
    if not available_accounts:
        return render_setup_needed()

    account_options = "\n".join(
        f'<option value="{e(account_id)}">{e(account.get("name", account_id))}</option>'
        for account_id, account in available_accounts
    )
    options = "\n".join(
        f'<option value="{e(name)}" {"selected" if name == DEFAULT_TEMPLATE else ""}>{e(name)}</option>'
        for name in TEMPLATES
    )
    with JOBS_LOCK:
        active_pairs = [
            (job_id, job)
            for job_id, job in reversed(list(JOBS.items()))
            if job.get("status") in ACTIVE_STATUSES and job.get("account_id") in account_ids
        ]
        rows = list(JOBS.items())[-10:][::-1]
    locked = len(available_accounts) == 1 and bool(active_pairs)
    disabled = "disabled" if locked else ""
    active_account_ids = {str(job.get("account_id")) for _, job in active_pairs if job.get("account_id")}
    active_account_data = e(",".join(active_account_ids))
    active_notice = ""
    if active_pairs:
        active_items = "".join(
            f"""<p class="hint">账号：{e(job.get("account_name"))}　批次：{e(job.get("batch"))}　<a href="/job?id={e(job_id)}">查看进度</a></p>
  {progress_html(job)}"""
            for job_id, job in active_pairs[:3]
        )
        active_notice = f"""
<section class="alert alert-warn">
  <div class="section-head">
    <div>
      <h2>有妙手账号正在处理</h2>
      <p class="section-kicker">同一个妙手账号完成前不能提交下一批；其他空闲妙手账号可以继续使用。</p>
    </div>
  </div>
  {active_items}
</section>"""
    job_rows = "".join(
        f"""<tr>
          <td><a href="/job?id={e(job_id)}">{e(job.get("batch"))}</a></td>
          <td>{e(job.get("account_name"))}</td>
          <td>{e(job.get("created_by"))}</td>
          <td>{e(job.get("template"))}</td>
          <td>{status_badge(job.get("status"))}</td>
          <td>{e(job_count_text(job))}</td>
          <td class="error-cell">{e(readable_job_error(job))}</td>
          <td>{e(job.get("created_at"))}</td>
        </tr>"""
        for job_id, job in rows
    )
    if not job_rows:
        job_rows = '<tr><td colspan="8" class="empty-row">还没有任务</td></tr>'
    header_right = render_account_menu(username, len(available_accounts))
    body = f"""
{render_top_nav("batch")}
{active_notice}
<section>
  <div class="section-head">
    <div>
      <h2>新建批次</h2>
      <p class="section-kicker">适合标题和图片不同、类目参数相同的模板批量上货。</p>
    </div>
  </div>
  <form id="batchForm" action="/run" method="post" enctype="multipart/form-data" data-submit-lock data-active-accounts="{active_account_data}">
    <fieldset {disabled}>
    <div id="accountBusyMessage" class="alert alert-warn" hidden>这个妙手账号正在处理上一批。请等待完成，或切换到其他空闲妙手账号。</div>
    <div class="form-grid">
      <div class="field-card">
        <label for="account_id">妙手账号</label>
        <select id="account_id" name="account_id">{account_options}</select>
        <p class="field-help">每个妙手账号单独排队，避免同账号批次互相影响。</p>
      </div>
      <div class="field-card">
        <label for="batch">批次名</label>
        <input id="batch" name="batch" required placeholder="只作为任务名称，例如：第1批">
        <p class="field-help">不参与图片匹配，可以按团队习惯自由命名。</p>
      </div>
      <div class="field-card">
        <label for="template">产品模板</label>
        <select id="template" name="template">{options}</select>
        <p class="field-help">固定参数来自已保存的妙手模板。</p>
      </div>
      <div class="field-card">
        <label for="title_file">标题 Excel</label>
        <input id="title_file" name="title_file" type="file" accept=".xlsx,.xlsm" required>
        <p class="field-help">优先按表头识别“序号”和“标题”。</p>
      </div>
      <div class="field-card">
        <label>图片来源</label>
        <div class="upload-choice-row">
          <label class="upload-button" for="batch_image_zip">选择图片 ZIP</label>
          <label class="upload-button" for="batch_image_folder">选择图片文件夹</label>
          <span id="batchImageChoice" class="file-choice-name">未选择任何文件</span>
        </div>
        <input class="hidden-file" id="batch_image_zip" name="image_zip" type="file" accept=".zip">
        <input class="hidden-file" id="batch_image_folder" name="image_folder" type="file" accept="image/*" multiple webkitdirectory directory>
        <p class="field-help">支持 ZIP 或大文件夹；子文件夹名要和 Excel 序号对应。</p>
      </div>
      <div class="field-card">
        <label for="limit">只处理前几个产品</label>
        <input id="limit" name="limit" type="number" min="1" placeholder="留空就是全部">
        <p class="field-help">测试时填 1 或 5；正式跑可留空。</p>
      </div>
      <div class="check-row">
        <input id="upload_to_oss" name="upload_to_oss" type="checkbox" checked>
        <div>
          <label for="upload_to_oss">自动上传图片到 OSS</label>
          <p class="field-help">只需要上传一次 ZIP，程序会先传 OSS 再提交妙手。</p>
        </div>
      </div>
      <div class="check-row">
        <input id="dry_run" name="dry_run" type="checkbox" checked>
        <div>
          <label for="dry_run">先预检，不创建产品</label>
          <p class="field-help">首次测试建议保留勾选，确认匹配后再正式创建。</p>
        </div>
      </div>
      <div class="alert alert-info wide">以本次上传的 Excel 和图片来源为准；匹配只看 Excel 的序号列和图片子文件夹名字。两边都有的序号会处理，缺标题或缺图片的序号会记为失败。勾选自动上传后，程序会用本次图片上传并覆盖 OSS 同路径旧文件。</div>
    </div>
    <div class="actions"><button id="batchSubmit" type="submit" data-working-label="正在创建任务..." {disabled}>{'当前账号处理中' if locked else '开始处理'}</button></div>
    </fieldset>
  </form>
  <script>
    (() => {{
      const form = document.getElementById('batchForm');
      if (!form) return;
      const activeAccounts = new Set((form.dataset.activeAccounts || '').split(',').filter(Boolean));
      const account = document.getElementById('account_id');
      const submit = document.getElementById('batchSubmit');
      const message = document.getElementById('accountBusyMessage');
      const imageZip = document.getElementById('batch_image_zip');
      const imageFolder = document.getElementById('batch_image_folder');
      const imageChoice = document.getElementById('batchImageChoice');
      function setImageChoice(input, otherInput, label) {{
        if (!input || !input.files || !input.files.length) return;
        if (otherInput) otherInput.value = '';
        if (imageChoice) {{
          const count = input.files.length;
          imageChoice.textContent = count === 1 ? input.files[0].name : `${{label}}，共 ${{count}} 个图片文件`;
        }}
      }}
      if (imageZip) imageZip.addEventListener('change', () => setImageChoice(imageZip, imageFolder, '已选择 ZIP'));
      if (imageFolder) imageFolder.addEventListener('change', () => setImageChoice(imageFolder, imageZip, '已选择文件夹'));
      form.addEventListener('submit', (event) => {{
        const hasZip = imageZip && imageZip.files && imageZip.files.length;
        const hasFolder = imageFolder && imageFolder.files && imageFolder.files.length;
        if (!hasZip && !hasFolder) {{
          event.preventDefault();
          event.stopImmediatePropagation();
          alert('请选择图片 ZIP 或图片文件夹');
        }}
      }});
      function updateBatchSubmit() {{
        const busy = account && activeAccounts.has(account.value);
        if (submit) {{
          submit.disabled = !!busy;
          submit.textContent = busy ? '当前账号处理中' : '开始处理';
        }}
        if (message) message.hidden = !busy;
      }}
      if (account) account.addEventListener('change', updateBatchSubmit);
      updateBatchSubmit();
    }})();
  </script>
</section>
<section>
  <div class="section-head">
    <div>
      <h2>最近任务</h2>
      <p class="section-kicker">点击批次名查看进度、失败序号和本地日志路径。</p>
    </div>
  </div>
  <div class="table-wrap">
    <table>
      <thead><tr><th>批次</th><th>妙手账号</th><th>提交人</th><th>模板</th><th>状态</th><th>已处理</th><th>失败原因</th><th>创建时间</th></tr></thead>
      <tbody>{job_rows}</tbody>
    </table>
  </div>
</section>"""
    return render_page("妙手 TikTok 批量上货工具", body, refresh=locked, header_right=header_right)


def render_job(job_id: str, username: str | None = None) -> bytes:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        return render_page("任务不存在", '<section><h2>任务不存在</h2><p><a href="/">返回首页</a></p></section>')
    refresh = job.get("status") in ACTIVE_STATUSES
    summary = job.get("summary") or {}
    rows = "".join(
        f"""<tr>
          <td>{e(item.get("seq"))}</td>
          <td>{status_badge(item.get("status"))}</td>
          <td>{'复用旧产品' if item.get("reused_existing") or item.get("reused_from_log") else '新建' if item.get("status") == "success" else ''}</td>
          <td>{e(item.get("image_count"))}</td>
          <td>{e(item.get("tiktokDetailId"))}</td>
          <td>{e(ai_status_text(item))}</td>
          <td class="error-cell">{e(readable_error_text(item.get("error")))}</td>
        </tr>"""
        for item in job.get("results", [])
    )
    if not rows:
        rows = '<tr><td colspan="7" class="empty-row">等待开始</td></tr>'
    body = f"""
{render_top_nav("batch")}
<section>
  <div class="section-head">
    <div>
      <h2>{e(job.get("batch"))}</h2>
      <p class="section-kicker">妙手账号：{e(job.get("account_name"))}　提交人：{e(job.get("created_by"))}　模板：{e(job.get("template"))}</p>
    </div>
    <div>{status_badge(job.get("status"))}</div>
  </div>
  <p class="hint">已处理：{e(job.get("done_count", 0))}</p>
  {progress_html(job)}
  <div class="alert alert-info">预检失败序号：{e("、".join(str(seq) for seq in job.get("preflight_failed_seqs", [])[:30]) or "无")}<br>日志：{e(job.get("log_path") or summary.get("logPath") or "任务完成后生成")}</div>
  {f'<div class="alert alert-error">{e(readable_job_error(job))}</div>' if readable_job_error(job) else ''}
  <p><a href="/">返回首页</a></p>
</section>
<section>
  <div class="section-head">
    <div>
      <h2>处理结果</h2>
      <p class="section-kicker">失败项会继续保留在本地日志里，方便重新整理后再跑。</p>
    </div>
  </div>
  <div class="table-wrap">
    <table>
      <thead><tr><th>序号</th><th>状态</th><th>处理方式</th><th>图片数</th><th>TikTok ID</th><th>AI状态</th><th>失败原因</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
</section>"""
    account_count = len(all_account_ids()) if username else 0
    header_right = render_account_menu(username, account_count) if username else ""
    return render_page("批次结果", body, refresh=refresh, header_right=header_right)


def render_attr_control(attr: dict) -> str:
    attr_id = str(attr.get("attrId") or "")
    required = is_required_attr(attr)
    required_html = ' <span class="required-mark">*</span>' if required else ""
    required_attr = "required" if required and not attr.get("isCustomized") else ""
    values = attr.get("values") or []
    options = '<option value="">不填写</option>' + "".join(
        f'<option value="{e(item.get("id"))}">{e(item.get("valueNameAlias") or item.get("name") or item.get("id"))} / {e(item.get("name") or item.get("id"))}</option>'
        for item in values
    )
    select_html = f'<select name="attr_{e(attr_id)}" {required_attr}>{options}</select>' if values else ""
    custom_html = ""
    if attr.get("isCustomized") or not values:
        custom_required = "required" if required and not values else ""
        custom_html = f'<input name="attr_custom_{e(attr_id)}" placeholder="英文自定义值" {custom_required}>'
    return f"""
      <div class="field-card">
        <label>{e(attr_label(attr))}{required_html}</label>
        {select_html}
        {custom_html}
      </div>"""


def json_for_html(data: object) -> str:
    return rendering.json_for_html(data)


def selected_category_path(categories: list[dict], cid: str) -> str:
    for row in categories:
        if str(row.get("cid")) == str(cid):
            return str(row.get("path") or "")
    return ""


def render_category_picker(categories: list[dict], cid_text: str) -> str:
    selected_path = selected_category_path(categories, cid_text)
    data = [
        {"cid": row["cid"], "path": row["path"]}
        for row in categories
        if row.get("cid") and row.get("path")
    ]
    return f"""
      <div class="wide">
        <label for="categorySearch">TikTok 美国站类目</label>
        <input id="categorySearch" placeholder="搜索或在下方手动选择类目" value="{e(selected_path)}" autocomplete="off">
        <input id="cid" name="cid" type="hidden" value="{e(cid_text)}" required>
        <div class="category-picker"><div id="categoryColumns" class="category-columns"></div></div>
        <p id="categorySelected" class="hint">{"当前选择：" + e(selected_path) if selected_path else "请选择末级类目"}</p>
      </div>
      <script id="categoryData" type="application/json">{json_for_html(data)}</script>
      <script>
      (() => {{
        const rows = JSON.parse(document.getElementById('categoryData').textContent || '[]');
        const cidInput = document.getElementById('cid');
        const search = document.getElementById('categorySearch');
        const columns = document.getElementById('categoryColumns');
        const selected = document.getElementById('categorySelected');
        let picked = rows.find(row => String(row.cid) === String(cidInput.value));
        let prefix = picked ? picked.path.split(' / ').slice(0, -1) : [];

        function parts(row) {{ return row.path.split(' / '); }}
        function matchesPrefix(row, value) {{
          const p = parts(row);
          return value.every((item, index) => p[index] === item);
        }}
        function setLeaf(row) {{
          cidInput.value = row.cid;
          search.value = row.path;
          selected.textContent = '当前选择：' + row.path;
          picked = row;
          prefix = parts(row).slice(0, -1);
          renderColumns();
        }}
        function renderSearch() {{
          const term = search.value.trim().toLowerCase();
          if (!term || (picked && term === picked.path.toLowerCase())) {{
            renderColumns();
            return;
          }}
          columns.innerHTML = '';
          const col = document.createElement('div');
          col.className = 'category-column';
          rows.filter(row => row.path.toLowerCase().includes(term)).slice(0, 80).forEach(row => {{
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'category-item leaf';
            button.textContent = row.path;
            button.onclick = () => setLeaf(row);
            col.appendChild(button);
          }});
          columns.appendChild(col);
        }}
        function renderColumns() {{
          columns.innerHTML = '';
          let current = [];
          let level = 0;
          while (true) {{
            const choices = new Map();
            for (const row of rows) {{
              const p = parts(row);
              if (p.length <= level || !matchesPrefix(row, current)) continue;
              const label = p[level];
              const old = choices.get(label) || {{ label, cid: '', leaf: true }};
              if (p.length > level + 1) old.leaf = false;
              if (p.length === level + 1) old.cid = row.cid;
              choices.set(label, old);
            }}
            if (!choices.size) break;
            const col = document.createElement('div');
            col.className = 'category-column';
            const levelPrefix = current.slice();
            for (const choice of choices.values()) {{
              const button = document.createElement('button');
              button.type = 'button';
              button.className = 'category-item' + (choice.leaf ? ' leaf' : '');
              if (prefix[level] === choice.label || (picked && choice.cid && String(picked.cid) === String(choice.cid))) button.className += ' active';
              button.textContent = choice.label + (choice.leaf ? '' : ' ›');
              button.onclick = () => {{
                if (choice.leaf) {{
                  const row = rows.find(item => String(item.cid) === String(choice.cid));
                  if (row) setLeaf(row);
                }} else {{
                  const nextPrefix = levelPrefix.concat(choice.label);
                  prefix = nextPrefix;
                  picked = null;
                  cidInput.value = '';
                  search.value = nextPrefix.join(' / ');
                  selected.textContent = '当前选择：' + nextPrefix.join(' / ');
                  renderColumns();
                }}
              }};
              col.appendChild(button);
            }}
            columns.appendChild(col);
            if (!prefix[level]) break;
            current = current.concat(prefix[level]);
            level += 1;
          }}
        }}
        search.addEventListener('input', renderSearch);
        renderColumns();
      }})();
      </script>"""


def render_single(username: str, query: dict[str, list[str]] | None = None, error: str = "") -> bytes:
    query = query or {}
    config = load_accounts_config()
    accounts = config.get("accounts", {})
    account_ids = [account_id for account_id in all_account_ids(config) if account_id in accounts]
    if not account_ids:
        return render_setup_needed()
    selected_account_id = query.get("account_id", [account_ids[0]])[0]
    if selected_account_id not in account_ids:
        selected_account_id = account_ids[0]
    account = accounts[selected_account_id]
    account_options = "\n".join(
        f'<option value="{e(account_id)}" {"selected" if account_id == selected_account_id else ""}>{e(accounts[account_id].get("name", account_id))}</option>'
        for account_id in account_ids
    )

    cid_text = query.get("cid", [""])[0]
    message_html = alert_html("error", error)
    categories: list[dict] = []
    shops: list[dict] = []
    metadata: dict = {}
    try:
        credentials = account_credentials(account)
        shops = get_tiktok_shops(credentials)
        categories = load_categories(credentials)
        if cid_text:
            metadata = get_category_metadata(int(cid_text), credentials, [int(shop["shopId"]) for shop in shops[:3]])
    except Exception as exc:
        message_html += alert_html("error", exc)

    shop_checks = "".join(
        f'<label><input type="checkbox" name="shop_id" value="{e(shop.get("shopId"))}"> {e(shop_display_name(shop))}</label>'
        for shop in shops
    ) or '<p class="hint">当前妙手账号没有返回 TikTok 美国店铺。</p>'

    required_attrs = [attr for attr in metadata_attrs(metadata, "categoryProductAttrList") if is_required_attr(attr)]
    optional_attrs = [attr for attr in metadata_attrs(metadata, "categoryProductAttrList") if not is_required_attr(attr)]
    all_product_attrs = metadata_attrs(metadata, "categoryProductAttrList")
    config_notes = category_required_notes(metadata)
    if required_attrs:
        required_attr_html = "".join(render_attr_control(attr) for attr in required_attrs)
    elif all_product_attrs:
        note_html = "<br>".join(e(note) for note in config_notes)
        required_attr_html = f'<div class="alert alert-info wide">这个类目已读取 {len(all_product_attrs)} 个商品属性，但妙手没有标记必须填写的商品属性。可展开下面的可选属性按需要补充。{("<br>" + note_html) if note_html else ""}</div>'
    elif metadata:
        note_html = "<br>".join(e(note) for note in config_notes)
        required_attr_html = f'<div class="alert alert-warn wide">类目参数已加载，但妙手接口没有返回商品属性列表。可以先确认店铺和类目是否匹配，或换一个末级类目重新加载。{("<br>" + note_html) if note_html else ""}</div>'
    else:
        required_attr_html = '<p class="hint wide">选择类目后会显示必填属性。</p>'
    optional_attr_html = "".join(render_attr_control(attr) for attr in optional_attrs[:30])
    sale_attrs = metadata_attrs(metadata, "categorySaleAttrList")
    default_sale_attr_id = str(sale_attrs[0].get("attrId") or "") if sale_attrs else ""
    spec_name_options = "".join(f'<option value="{e(attr_label(attr))}"></option>' for attr in sale_attrs)
    sale_attr_pairs = [
        {"name": attr_label(attr), "id": str(attr.get("attrId") or "")}
        for attr in sale_attrs
        if attr.get("attrId")
    ]
    sale_attr_pairs_json = json_for_html(sale_attr_pairs)
    sale_attr_note = ""
    if sale_attrs:
        sale_attr_note = '<p class="section-kicker">规格名称可以选择妙手返回的选项，也可以自己输入。页面只需要维护一组销售规格。</p>'
    elif metadata:
        sale_attr_note = '<div class="alert alert-warn wide">当前类目没有返回销售属性，保存 SKU 时可能会被妙手拒绝。建议换一个末级类目重新加载。</div>'

    metadata_form = f"""
<section>
  <h2>选择类目</h2>
  {alert_html("warn", "单产品智能上传仍在开发和完善中。公开给别人试用时，建议优先使用已经跑通的「模板批量上传」。")}
  {message_html}
  <form action="/single" method="get">
    <div class="grid">
      <div>
        <label for="single_account_id">妙手账号</label>
        <select id="single_account_id" name="account_id">{account_options}</select>
      </div>
      {render_category_picker(categories, cid_text)}
    </div>
    <div class="actions"><button type="submit">加载类目参数</button></div>
  </form>
</section>"""

    product_form = ""
    if cid_text and metadata:
        product_form = f"""
<form id="singleProductForm" action="/single/create" method="post" enctype="multipart/form-data" data-submit-lock>
  <input type="hidden" name="account_id" value="{e(selected_account_id)}">
  <input type="hidden" name="cid" value="{e(cid_text)}">
  <input type="hidden" id="ai_suggest_applied" name="ai_suggest_applied" value="0">
  <section>
    <h2>产品基础信息</h2>
    <p class="section-kicker">先填写页面上最核心的信息；类目属性、规格价格、物流包装会在后面分段填写。</p>
    <div class="form-grid">
      <div class="field-card wide">
        <label for="title">英文标题 <span class="required-mark">*</span></label>
        <input id="title" name="title" required minlength="25" maxlength="255">
        <p class="field-help">按妙手限制控制在 25-255 字符。</p>
      </div>
      <div class="field-card wide">
        <label for="notes">英文详情描述</label>
        <textarea id="notes" name="notes" maxlength="10000" placeholder="不填时用标题生成一段英文描述"></textarea>
        <p class="field-help">不填写时会用标题生成基础英文描述。</p>
      </div>
      <div class="alert alert-info wide" id="aiSuggestStatus">
        AI 可以读取标题和前几张产品图片，生成英文描述并尝试填写有明确依据的类目属性；不确定的软参数会保持空白。
      </div>
      <div class="field-card">
        <label for="item_num">产品编号</label>
        <input id="item_num" name="item_num" maxlength="50" placeholder="可不填">
      </div>
    </div>
  </section>
  <section>
    <h2>产品图片</h2>
    <div class="form-grid">
      <div class="field-card wide">
        <label>产品图片</label>
        <div class="upload-actions">
          <label class="upload-button" for="image_upload_files">选择图片或 ZIP</label>
          <label class="upload-button" for="image_upload_folder">选择图片文件夹</label>
        </div>
        <input class="hidden-file" id="image_upload_files" name="image_upload" type="file" accept="image/*,.zip" multiple>
        <input class="hidden-file" id="image_upload_folder" name="image_upload" type="file" accept="image/*" multiple webkitdirectory directory>
        <p class="field-help">同一个上传区支持单张图片、多张图片、图片文件夹或图片 ZIP。</p>
      </div>
      <div class="field-card">
        <label for="main_video">主图视频</label>
        <input id="main_video" name="main_video" type="file" accept="video/mp4,video/quicktime,video/webm,.mp4,.mov,.m4v,.webm">
        <p class="field-help">可选，只用于单产品智能上传。</p>
      </div>
      <div class="alert alert-info wide">按文件名自然排序，只保存上传前 {SINGLE_IMAGE_LIMIT} 张；少于 {SINGLE_IMAGE_LIMIT} 张不会报错。</div>
    </div>
    <div class="actions">
      <button id="aiSuggestButton" type="button" class="ghost" data-working-label="AI 正在识别图片...">AI 生成描述和属性建议</button>
    </div>
  </section>
  <section>
    <h2>类目必填属性</h2>
    <div class="form-grid">{required_attr_html}</div>
  </section>
  <section>
    <h2>可选属性</h2>
    <details>
      <summary>展开可选软参数</summary>
      <div class="form-grid" style="margin-top: 14px;">{optional_attr_html or '<p class="hint wide">这个类目没有更多可选属性。</p>'}</div>
    </details>
  </section>
  <section>
    <h2>规格与价格</h2>
    <input type="hidden" name="sale_attr_id" value="{e(default_sale_attr_id)}">
    {sale_attr_note}
    <div class="form-grid">
      <div class="field-card wide">
        <label for="spec_name">规格名称 <span class="required-mark">*</span></label>
        <input id="spec_name" name="spec_name" list="spec_name_options" placeholder="例如：Bedding Size、Color、Style" required>
        <datalist id="spec_name_options">{spec_name_options}</datalist>
        <p class="field-help">对应妙手页面里的“规格一”，可选择也可手动输入。</p>
      </div>
    </div>
    <div id="skuRows" style="margin-top: 14px;">
      <div class="sku-row">
        <input type="hidden" name="sku_row_id" value="0">
        <div><label>规格值</label><input name="sku_value" placeholder="例如：30x40inch (For Babys)" required></div>
        <div><label>价格 USD</label><input name="sku_price" type="number" min="0.01" step="0.01" required></div>
        <div><label>库存</label><input name="sku_stock" type="number" min="0" step="1" required></div>
        <div><label>规格图</label><input name="sku_image_file_0" type="file" accept="image/*"><span class="hint">不传用第一张主图</span></div>
        <button type="button" class="ghost mini-button" onclick="removeSkuRow(this)">删除</button>
      </div>
    </div>
    <button type="button" class="ghost mini-button" onclick="addSkuRow()">添加规格值</button>
  </section>
  <section>
    <h2>物流/包装信息</h2>
    <p class="section-kicker">这些字段用于创建采集箱产品，不属于标题和类目属性，所以放到靠后的包装分段。</p>
    <div class="form-grid">
      <div class="field-card">
        <label for="weight">重量 kg <span class="required-mark">*</span></label>
        <input id="weight" name="weight" type="number" min="0.001" max="100" step="0.001" required>
      </div>
      <div class="field-card">
        <label for="package_length">包装长度 cm <span class="required-mark">*</span></label>
        <input id="package_length" name="package_length" type="number" min="1" max="1000" step="0.1" required>
      </div>
      <div class="field-card">
        <label for="package_width">包装宽度 cm <span class="required-mark">*</span></label>
        <input id="package_width" name="package_width" type="number" min="1" max="1000" step="0.1" required>
      </div>
      <div class="field-card">
        <label for="package_height">包装高度 cm <span class="required-mark">*</span></label>
        <input id="package_height" name="package_height" type="number" min="1" max="1000" step="0.1" required>
      </div>
    </div>
  </section>
  <section>
    <h2>选择店铺</h2>
    <div class="shop-grid">{shop_checks}</div>
    <div class="actions"><button type="submit" data-working-label="正在保存到妙手...">保存到妙手</button></div>
</section>
</form>
<script>
let skuNextId = 1;
const saleAttrPairs = {sale_attr_pairs_json};
const saleAttrInput = document.querySelector('input[name="sale_attr_id"]');
const specNameInput = document.getElementById('spec_name');
if (specNameInput && saleAttrInput) {{
  specNameInput.addEventListener('input', () => {{
    const picked = saleAttrPairs.find(item => item.name === specNameInput.value);
    if (picked) saleAttrInput.value = picked.id;
  }});
}}
function addSkuRow() {{
  const box = document.getElementById('skuRows');
  const row = box.children[0].cloneNode(true);
  const rowId = String(skuNextId++);
  row.querySelector('input[name="sku_row_id"]').value = rowId;
  row.querySelectorAll('input').forEach(input => {{
    if (input.type === 'hidden') return;
    input.value = '';
    if (input.type === 'file') input.name = 'sku_image_file_' + rowId;
  }});
  box.appendChild(row);
}}
function removeSkuRow(button) {{
  const box = document.getElementById('skuRows');
  if (box.children.length > 1) button.parentElement.remove();
}}
const singleForm = document.getElementById('singleProductForm');
const aiButton = document.getElementById('aiSuggestButton');
const aiStatus = document.getElementById('aiSuggestStatus');
function setAiStatus(message, kind = 'info') {{
  if (!aiStatus) return;
  aiStatus.className = 'alert alert-' + kind + ' wide';
  aiStatus.textContent = message;
}}
function findOptionByText(select, valueName) {{
  const target = String(valueName || '').trim().toLowerCase();
  if (!target) return '';
  for (const option of select.options) {{
    const text = option.textContent.trim().toLowerCase();
    if (text === target || text.includes(target) || target.includes(text.split('/')[0].trim())) {{
      return option.value;
    }}
  }}
  return '';
}}
function applyAiSuggestion(suggestion) {{
  if (!suggestion) return;
  const notes = document.getElementById('notes');
  if (notes && suggestion.description_html) notes.value = suggestion.description_html;
  let filled = 0;
  for (const attr of (suggestion.attributes || [])) {{
    const attrId = attr.attrId;
    const select = singleForm.querySelector(`[name="attr_${{CSS.escape(attrId)}}"]`);
    const custom = singleForm.querySelector(`[name="attr_custom_${{CSS.escape(attrId)}}"]`);
    if (select) {{
      const optionValue = attr.valueId || findOptionByText(select, attr.valueName);
      if (optionValue) {{
        select.value = optionValue;
        filled += 1;
        continue;
      }}
    }}
    if (custom && attr.valueName) {{
      custom.value = attr.valueName;
      filled += 1;
    }}
  }}
  const warnings = (suggestion.warnings || []).filter(Boolean);
  const suffix = warnings.length ? ' 提醒：' + warnings.join('；') : '';
  const applied = document.getElementById('ai_suggest_applied');
  if (applied) applied.value = '1';
  setAiStatus(`AI 已生成英文描述，并填入 ${{filled}} 个可识别属性。${{suffix}}`, 'success');
}}
if (singleForm && aiButton) {{
  aiButton.addEventListener('click', async () => {{
    const title = document.getElementById('title');
    const imageInputs = Array.from(singleForm.querySelectorAll('input[name="image_upload"]'));
    if (!title || !title.value.trim()) {{
      setAiStatus('请先填写英文标题，再让 AI 生成建议。', 'error');
      return;
    }}
    const hasImages = imageInputs.some(input => input.files && input.files.length);
    if (!hasImages) {{
      setAiStatus('请先上传产品图片文件夹、多张图片或图片 ZIP，AI 才能识别。', 'error');
      return;
    }}
    aiButton.disabled = true;
    const oldText = aiButton.textContent;
    aiButton.textContent = aiButton.dataset.workingLabel || '处理中...';
    setAiStatus('AI 正在读取标题和图片，请稍等。', 'info');
    try {{
      const response = await fetch('/single/ai-suggest', {{ method: 'POST', body: new FormData(singleForm) }});
      const payload = await response.json();
      if (!response.ok || !payload.ok) throw new Error(payload.error || 'AI 生成失败');
      applyAiSuggestion(payload.suggestion);
    }} catch (error) {{
      setAiStatus(error.message || String(error), 'error');
    }} finally {{
      aiButton.disabled = false;
      aiButton.textContent = oldText;
    }}
  }});
}}
</script>"""

    body = f"{render_top_nav('single')}{metadata_form}{product_form}"
    return render_page("单产品智能上传", body, header_right=render_account_menu(username, len(account_ids)))


def render_ai_settings(username: str, message: str = "", error: str = "") -> bytes:
    settings = load_ai_settings()
    message_html = alert_html("success", message)
    error_html = alert_html("error", error)
    provider_key = str(settings.get("provider_key") or "deepseek")
    provider_options = "\n".join(
        f'<option value="{e(key)}"{" selected" if key == provider_key else ""}>{e(preset["label"])}</option>'
        for key, preset in AI_PROVIDER_PRESETS.items()
    )
    preset_public = {
        key: {name: preset[name] for name in ("label", "model", "base_url", "help")}
        for key, preset in AI_PROVIDER_PRESETS.items()
    }
    provider_help = AI_PROVIDER_PRESETS.get(provider_key, AI_PROVIDER_PRESETS["custom"])["help"]
    body = f"""
{render_top_nav("ai")}
<section>
  <div class="section-head">
    <div>
      <h2>AI 设置</h2>
      <p class="section-kicker">这里只保存用于图片识别和软参数建议的 AI 配置；页面提示默认中文，提交到妙手的内容仍要求英文。</p>
    </div>
  </div>
  {message_html}
  {error_html}
  <form action="/ai-settings" method="post" data-submit-lock>
    <input type="hidden" id="ai_settings_action" name="action" value="save">
    <div class="form-grid">
      <div class="field-card">
        <label for="provider_key">AI 服务</label>
        <select id="provider_key" name="provider_key">{provider_options}</select>
        <p class="field-help" id="providerHelp">{e(provider_help)}</p>
      </div>
      <div class="field-card">
        <label for="model">视觉模型</label>
        <input id="model" name="model" value="{e(settings.get("model", ""))}">
        <p class="field-help">需要支持图片识别，不能只用纯文本模型。</p>
      </div>
      <div class="field-card wide">
        <label for="base_url">接口地址</label>
        <input id="base_url" name="base_url" value="{e(settings.get("base_url", ""))}">
        <p class="field-help">填写 OpenAI 兼容的 Chat Completions 地址；也可以只填到 /v1，程序会自动补全 /chat/completions。</p>
      </div>
      <div class="field-card wide">
        <label for="api_key">API Key</label>
        <input id="api_key" name="api_key" type="password" placeholder="留空不改" autocomplete="new-password">
        <p class="field-help">保存后不会在页面明文显示，也不要提交到 GitHub。</p>
      </div>
      <div class="alert alert-info wide">页面默认中文；AI 自动填写只作为建议，最终保存到妙手的标题、描述、规格和自定义属性仍要求英文。图片和标题里没有明确证据的软参数应留空。</div>
    </div>
    <div class="actions">
      <button type="submit" data-working-label="正在保存 AI 设置..." onclick="document.getElementById('ai_settings_action').value='save'">保存 AI 设置</button>
      <button type="submit" class="ghost" data-working-label="正在测试 AI 配置..." onclick="document.getElementById('ai_settings_action').value='test'">测试当前配置</button>
    </div>
  </form>
</section>
<script>
const aiPresets = {json_for_html(preset_public)};
const providerSelect = document.getElementById('provider_key');
const modelInput = document.getElementById('model');
const baseUrlInput = document.getElementById('base_url');
const providerHelp = document.getElementById('providerHelp');
providerSelect?.addEventListener('change', () => {{
  const preset = aiPresets[providerSelect.value] || {{}};
  if (preset.model) modelInput.value = preset.model;
  if (preset.base_url) baseUrlInput.value = preset.base_url;
  providerHelp.textContent = preset.help || '';
}});
</script>"""
    account_count = len(all_account_ids())
    return render_page("AI 设置", body, header_right=render_account_menu(username, account_count))


def render_failure_page(title: str, error: object, back_url: str, back_label: str, username: str | None = None) -> bytes:
    account_count = len(all_account_ids()) if username else 0
    header_right = render_account_menu(username, account_count) if username else ""
    detail = readable_error_text(error) or str(error)
    body = f"""
{render_top_nav("batch") if username else ""}
<section>
  <div class="section-head">
    <div>
      <h2>{e(title)}</h2>
      <p class="section-kicker">请按提示修正后重新提交；已经成功保存的本地配置不会被覆盖。</p>
    </div>
  </div>
  {alert_html("error", detail)}
  <p><a href="{e(back_url)}">{e(back_label)}</a></p>
</section>"""
    return render_page(title, body, header_right=header_right)


class Handler(BaseHTTPRequestHandler):
    def current_username(self) -> str | None:
        return DEFAULT_OPERATOR

    def redirect(self, location: str) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        self.end_headers()

    def send_html(self, content: bytes, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def send_json(self, payload: dict, status: int = 200) -> None:
        content = json_io.dumps(payload, compact=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/login":
            self.redirect("/")
            return
        username = DEFAULT_OPERATOR
        if parsed.path == "/":
            self.send_html(render_home(username))
            return
        if parsed.path == "/check":
            self.send_html(render_release_check(username))
            return
        if parsed.path == "/single":
            self.send_html(render_single(username, parse_qs(parsed.query)))
            return
        if parsed.path == "/ai-settings":
            query = parse_qs(parsed.query)
            self.send_html(render_ai_settings(username, query.get("message", [""])[0], query.get("error", [""])[0]))
            return
        if parsed.path == "/accounts":
            query = parse_qs(parsed.query)
            self.send_html(render_accounts(username, query.get("message", [""])[0], query.get("error", [""])[0]))
            return
        if parsed.path == "/accounts/confirm":
            token = parse_qs(parsed.query).get("token", [""])[0]
            self.send_html(render_account_confirm(username, token))
            return
        if parsed.path == "/job":
            job_id = parse_qs(parsed.query).get("id", [""])[0]
            self.send_html(render_job(job_id, username))
            return
        self.send_html(render_page("未找到", '<section><h2>未找到</h2><p><a href="/">返回首页</a></p></section>'), 404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/login":
            self.redirect("/")
            return
        if path == "/logout":
            self.redirect("/")
            return
        if path == "/ai-settings":
            username = DEFAULT_OPERATOR
            try:
                form = cgi.FieldStorage(
                    fp=self.rfile,
                    headers=self.headers,
                    environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": self.headers.get("Content-Type", "")},
                )
                settings = ai_settings_from_form(form)
                if field_text(form, "action", "save") == "test":
                    test_ai_settings(settings_for_ai_test(settings))
                    self.redirect("/ai-settings?message=" + urllib.parse.quote("AI 测试成功：当前配置可以返回图片识别 JSON。"))
                else:
                    save_ai_settings(settings)
                    self.redirect("/ai-settings?message=" + urllib.parse.quote("AI 设置已保存"))
            except Exception as exc:
                self.redirect("/ai-settings?error=" + urllib.parse.quote(str(exc)))
            return
        if path == "/single/ai-suggest":
            try:
                form = cgi.FieldStorage(
                    fp=self.rfile,
                    headers=self.headers,
                    environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": self.headers.get("Content-Type", "")},
                )
                config = load_accounts_config()
                account_id = field_text(form, "account_id")
                account = (config.get("accounts") or {}).get(account_id)
                if not account:
                    raise ValueError("请先选择有效的妙手账号")
                credentials = account_credentials(account)
                title = field_text(form, "title")
                if not title:
                    raise ValueError("请先填写英文标题")
                require_english(title, "英文标题")
                notes = field_text(form, "notes")
                if notes:
                    require_english(notes, "英文详情描述")
                cid = int_field(form, "cid", "类目 ID", 1)
                shop_ids = [int(str(item.value)) for item in field_list(form, "shop_id") if str(item.value or "").isdigit()]
                metadata = get_category_metadata(cid, credentials, shop_ids[:3] if shop_ids else None)
                upload_dir = UPLOAD_ROOT / ("ai-" + datetime.now().strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:8])
                image_files = uploaded_image_files(form, upload_dir)
                if not image_files:
                    raise ValueError("请先上传产品图片，AI 需要图片才能识别软参数")
                suggestion = call_deepseek_ai(title, notes, image_files, metadata)
                self.send_json({"ok": True, "suggestion": suggestion})
            except Exception as exc:
                self.send_json({"ok": False, "error": readable_error_text(exc) or str(exc)}, 400)
            return
        if path == "/single/create":
            username = DEFAULT_OPERATOR
            try:
                form = cgi.FieldStorage(
                    fp=self.rfile,
                    headers=self.headers,
                    environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": self.headers.get("Content-Type", "")},
                )
                config = load_accounts_config()
                account_ids = all_account_ids(config)
                account_id = field_text(form, "account_id")
                if account_id not in account_ids:
                    raise ValueError("未找到这个妙手账号配置")
                account = (config.get("accounts") or {}).get(account_id)
                if not account:
                    raise ValueError("未找到这个妙手账号配置")
                with JOBS_LOCK:
                    active_id = active_job_id_unlocked(account_id)
                if active_id:
                    body = f"""{render_top_nav("single")}<section>{alert_html("warn", "这个妙手账号正在处理上一批。同一个妙手账号完成前不能提交下一批。")}<p><a href="/job?id={e(active_id)}">查看当前任务</a></p></section>"""
                    self.send_html(render_page("这个账号正在处理", body, refresh=True, header_right=render_account_menu(username, len(account_ids))), 409)
                    return

                credentials = account_credentials(account)
                cid = int_field(form, "cid", "类目 ID", 1)
                title = field_text(form, "title")
                if not 25 <= len(title) <= 255:
                    raise ValueError("英文标题长度必须在 25-255 字符")
                require_english(title, "英文标题")
                notes = field_text(form, "notes")
                notes_is_fallback = False
                if notes:
                    require_english(notes, "英文详情描述")
                else:
                    notes = f"<p>{html.escape(title)}</p>"
                    notes_is_fallback = True
                ai_suggest_applied = field_text(form, "ai_suggest_applied") == "1"
                weight = decimal_field(form, "weight", "重量", 0.001, 100)
                package_length = decimal_field(form, "package_length", "包装长度", 1, 1000)
                package_width = decimal_field(form, "package_width", "包装宽度", 1, 1000)
                package_height = decimal_field(form, "package_height", "包装高度", 1, 1000)
                shop_ids = [int(str(item.value)) for item in field_list(form, "shop_id") if str(item.value or "").isdigit()]
                if not shop_ids:
                    raise ValueError("请至少选择一个店铺")
                metadata = get_category_metadata(cid, credentials, shop_ids[:3])
                product_attrs = build_product_attributes(form, metadata)

                job_id = datetime.now().strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:8]
                upload_dir = UPLOAD_ROOT / job_id
                sku_image_paths = uploaded_sku_image_files(form, upload_dir)
                sale_attr_id, spec_name, sku_rows = parse_sku_rows(form, sku_image_paths)
                image_files = uploaded_image_files(form, upload_dir)
                if not image_files:
                    raise ValueError("请上传产品图片文件夹、多张图片或图片 ZIP")
                video_file = uploaded_video_file(form, upload_dir)
                image_prefix = clean_prefix(field_text(form, "image_prefix"))
                if not image_prefix:
                    title_slug = re.sub(r"[^A-Za-z0-9._-]+", "-", title).strip("-")[:80] or "single-product"
                    image_prefix = f"single/{title_slug}"
                item_num = field_text(form, "item_num", f"SINGLE-{datetime.now().strftime('%Y%m%d%H%M%S')}")[:50]

                with JOBS_LOCK:
                    JOBS[job_id] = {
                        "batch": title[:60],
                        "account_id": account_id,
                        "account_name": account.get("name", account_id),
                        "created_by": username,
                        "template": "单产品智能上传",
                        "image_prefix": image_prefix,
                        "status": "queued",
                        "done_count": 0,
                        "uploaded_count": 0,
                        "source_uploaded_count": 0,
                        "total_count": 1,
                        "preflight_failed_count": 0,
                        "preflight_failed_seqs": [],
                        "results": [],
                        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }
                start_single_job(
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
                self.send_response(303)
                self.send_header("Location", f"/job?id={job_id}")
                self.end_headers()
            except Exception as exc:
                self.send_html(render_failure_page("创建单产品任务失败", exc, "/single", "返回单产品上传", username), 400)
            return
        if path in {"/accounts/add", "/accounts/confirm", "/accounts/rename", "/accounts/update", "/accounts/delete", "/accounts/toggle-lock"}:
            username = DEFAULT_OPERATOR
            try:
                form = cgi.FieldStorage(
                    fp=self.rfile,
                    headers=self.headers,
                    environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": self.headers.get("Content-Type", "")},
                )
                config = load_accounts_config()
                accounts = config.setdefault("accounts", {})
                user_accounts = all_account_ids(config)
                if path == "/accounts/confirm":
                    token = field_text(form, "token")
                    action = field_text(form, "action", "save")
                    with PENDING_ACCOUNTS_LOCK:
                        pending = PENDING_ACCOUNTS.pop(token, None)
                    if not pending:
                        raise ValueError("确认已失效，请重新识别")
                    if action != "save":
                        self.redirect("/accounts?message=" + urllib.parse.quote("已取消保存"))
                        return
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
                    self.redirect("/accounts?message=" + urllib.parse.quote("妙手账号已确认并保存"))
                    return

                if path == "/accounts/toggle-lock":
                    account_id = field_text(form, "account_id")
                    if account_id not in user_accounts or account_id not in accounts:
                        raise ValueError("当前用户没有这个妙手账号权限")
                    accounts[account_id]["locked"] = not bool(accounts[account_id].get("locked"))
                    save_accounts_config(config)
                    message = "账号已上锁" if accounts[account_id]["locked"] else "账号已开锁"
                    self.redirect("/accounts?message=" + urllib.parse.quote(message))
                    return

                if path == "/accounts/delete":
                    account_id = field_text(form, "account_id")
                    if account_id not in user_accounts or account_id not in accounts:
                        raise ValueError("当前用户没有这个妙手账号权限")
                    if accounts[account_id].get("locked"):
                        raise ValueError("这个妙手账号已上锁，开锁后才能删除")
                    with JOBS_LOCK:
                        active_id = active_job_id_unlocked(account_id)
                    if active_id:
                        raise ValueError("这个妙手账号正在处理任务，完成后才能删除")
                    accounts.pop(account_id, None)
                    for item in config.get("users", []):
                        item["accounts"] = [value for value in allowed_account_ids(item) if value != account_id]
                    save_accounts_config(config)
                    self.redirect("/accounts?message=" + urllib.parse.quote("妙手账号已删除"))
                    return

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
                        found_shop_id, found_templates, found_shop_name = discover_templates((app_key, accounts[account_id]["app_secret"]), shop_id)
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
                    self.redirect("/accounts?message=" + urllib.parse.quote("账号信息已保存"))
                    return

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
                found_shop_id, found_templates, found_shop_name = discover_templates((app_key, app_secret), shop_id)
                shop_id = shop_id or found_shop_id
                templates = {
                    template_name: requested_templates[template_name] or found_templates[template_name]
                    for template_name in TEMPLATES
                }
                token = secrets.token_urlsafe(24)
                with PENDING_ACCOUNTS_LOCK:
                    PENDING_ACCOUNTS[token] = {
                        "name": name,
                        "shop_id": shop_id,
                        "shop_name": found_shop_name,
                        "app_key": app_key,
                        "app_secret": app_secret,
                        "templates": templates,
                    }
                self.redirect("/accounts/confirm?token=" + urllib.parse.quote(token))
            except Exception as exc:
                self.redirect("/accounts?error=" + urllib.parse.quote(str(exc)))
            return
        if path != "/run":
            self.send_html(render_page("未找到", '<section><h2>未找到</h2></section>'), 404)
            return
        username = DEFAULT_OPERATOR
        try:
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": self.headers.get("Content-Type", "")},
            )
            config = load_accounts_config()
            account_ids = all_account_ids(config)
            account_id = field_text(form, "account_id")
            if account_id not in account_ids:
                raise ValueError("未找到这个妙手账号配置")
            account = (config.get("accounts") or {}).get(account_id)
            if not account:
                raise ValueError("未找到这个妙手账号配置")
            batch = field_text(form, "batch")
            template = field_text(form, "template", DEFAULT_TEMPLATE)
            image_prefix = field_text(form, "image_prefix")
            if not batch:
                raise ValueError("请填写批次名")
            if template not in TEMPLATES:
                raise ValueError("请选择有效的产品模板")
            template_detail_id = int((account.get("templates") or {}).get(template) or 0)
            if not template_detail_id:
                raise ValueError(f"这个妙手账号没有配置「{template}」模板")
            shop_id = int(account.get("shop_id") or SHOP_ID)
            app_key = str(account.get("app_key") or "").strip()
            app_secret = str(account.get("app_secret") or "").strip()
            if ACCOUNTS_PATH.exists() and (not app_key or not app_secret):
                raise ValueError("这个妙手账号缺少 app_key/app_secret，请先补全 accounts.json")
            miaoshou_credentials = (app_key, app_secret) if app_key and app_secret else None
            limit_text = field_text(form, "limit")
            limit = int(limit_text) if limit_text else None
            dry_run = "dry_run" in form
            upload_to_oss = "upload_to_oss" in form

            job_id = datetime.now().strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:8]
            upload_dir = UPLOAD_ROOT / job_id
            title_path = upload_dir / "title.xlsx"
            image_root = upload_dir / "images"
            title_original_name = upload_filename(form, "title_file", "title.xlsx")
            save_upload(form, "title_file", title_path)
            _, image_source_files = stage_batch_images(form, upload_dir, image_root)
            items = read_items(title_path)
            if limit:
                items = items[:limit]
            excel_seqs = [int(item["seq"]) for item in items]
            image_root, image_prefix = resolve_image_layout(image_root, batch, excel_seqs, image_prefix)
            image_seqs = image_seq_dirs(image_root)
            preflight_failures = build_preflight_failures(items, image_root, image_seqs, include_image_only=limit is None)
            items = [item for item in items if int(item["seq"]) in image_seqs]
            process_seqs = [int(item["seq"]) for item in items]
            if not items and not preflight_failures:
                found_text = "、".join(str(seq) for seq in sorted(image_seqs)[:30]) or "没有找到序号文件夹"
                raise ValueError(f"本次图片来源里没有任何能和 Excel 序号对应的图片文件夹。当前识别到的图片序号是：{found_text}")
            total_count = len(items) + len(preflight_failures)

            with JOBS_LOCK:
                active_id = active_job_id_unlocked(account_id)
                if not active_id:
                    JOBS[job_id] = {
                        "batch": batch,
                        "account_id": account_id,
                        "account_name": account.get("name", account_id),
                        "created_by": username,
                        "template": template,
                        "image_prefix": image_prefix,
                        "status": "queued",
                        "done_count": len(preflight_failures),
                        "uploaded_count": 0,
                        "source_uploaded_count": 0,
                        "total_count": total_count,
                        "preflight_failed_count": len(preflight_failures),
                        "preflight_failed_seqs": [item["seq"] for item in preflight_failures],
                        "results": preflight_failures[:],
                        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }
            if active_id:
                body = f"""{render_top_nav("batch")}<section>{alert_html("warn", "这个妙手账号正在处理上一批。同一个妙手账号完成前不能提交下一批，避免标题和图片错配。")}<p><a href="/job?id={e(active_id)}">查看当前批次</a></p></section>"""
                self.send_html(render_page("这个账号正在处理", body, refresh=True, header_right=render_account_menu(username, len(account_ids))), 409)
                return
            params = {
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
                "log_dir": RUN_ROOT,
                "miaoshou_credentials": miaoshou_credentials,
            }
            start_job(job_id, params)
            self.send_response(303)
            self.send_header("Location", f"/job?id={job_id}")
            self.end_headers()
        except Exception as exc:
            self.send_html(render_failure_page("创建任务失败", exc, "/", "返回首页", username), 400)

    def log_message(self, format: str, *args) -> None:
        return


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"打开 http://{args.host}:{args.port}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
