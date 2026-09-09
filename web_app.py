#!/usr/bin/env python3
from __future__ import annotations

import argparse
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning, message="'cgi' is deprecated.*")
import cgi
import html
import re
import threading
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from batch_tiktok_collect import DEFAULT_TEMPLATE, SHOP_ID, TEMPLATES, VALID_IMAGE_EXTS, natural_key, post as miaoshou_post, read_items, run_batch
from miaoshou_tool import account_pages
from miaoshou_tool import accounts as account_module
from miaoshou_tool import ai as ai_module
from miaoshou_tool import ai_pages
from miaoshou_tool import batch_pages
from miaoshou_tool import config as config_module
from miaoshou_tool import errors as error_module
from miaoshou_tool import files as file_module
from miaoshou_tool import forms as form_module
from miaoshou_tool import job_pages
from miaoshou_tool import jobs as job_module
from miaoshou_tool import json_io
from miaoshou_tool import miaoshou_api
from miaoshou_tool import oss_upload
from miaoshou_tool import page_shell
from miaoshou_tool import publishing as publishing_module
from miaoshou_tool import rendering
from miaoshou_tool import self_check
from miaoshou_tool import single_product as single_product_module
from miaoshou_tool import single_pages
from miaoshou_tool import system_pages
from miaoshou_tool import text as text_module

ROOT = config_module.ROOT
UPLOAD_ROOT = config_module.UPLOAD_ROOT
RUN_ROOT = config_module.RUN_ROOT
ACCOUNTS_PATH = config_module.ACCOUNTS_PATH
JOBS = job_module.JOBS
JOBS_LOCK = job_module.JOBS_LOCK
ACTIVE_STATUSES = job_module.ACTIVE_STATUSES
PENDING_ACCOUNTS: dict[str, dict] = {}
PENDING_ACCOUNTS_LOCK = threading.Lock()
CATEGORY_CACHE: dict[str, list[dict]] = {}
CATEGORY_CACHE_LOCK = threading.Lock()
SINGLE_IMAGE_LIMIT = config_module.SINGLE_IMAGE_LIMIT
AI_PROVIDER_PRESETS = ai_module.AI_PROVIDER_PRESETS
DEFAULT_OPERATOR = config_module.DEFAULT_OPERATOR
SITE = config_module.SITE


e = rendering.escape
alert_html = rendering.alert_html


field_text = form_module.field_text


load_accounts_config = account_module.load_accounts_config
all_account_ids = account_module.all_account_ids
user_record = account_module.user_record
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


decimal_field = form_module.decimal_field
int_field = form_module.int_field


contains_cjk = ai_module.contains_cjk
require_english = ai_module.require_english
require_ai_description_policy = ai_module.require_ai_description_policy
account_credentials = account_module.account_credentials
expect_miaoshou_success = miaoshou_api.expect_miaoshou_success


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
    return single_product_module.cleanup_created_single_product(
        common_id,
        detail_id,
        credentials,
        delete_tiktok_collect_products,
        delete_common_collect_products,
    )


resolve_skus = publishing_module.resolve_skus


def parse_sku_rows(form: cgi.FieldStorage, sku_image_paths: dict[str, Path] | None = None) -> tuple[str, str, list[dict]]:
    return publishing_module.parse_sku_rows(form, field_text, field_list, sku_image_paths)


def run_single_job(job_id: str, params: dict) -> None:
    single_product_module.run_single_job(
        job_id,
        params,
        {
            "set_job": set_job,
            "upload_single_images": upload_single_images,
            "upload_single_video": upload_single_video,
            "resolve_skus": resolve_skus,
            "call_deepseek_ai": call_deepseek_ai,
            "merge_ai_attributes": merge_ai_attributes,
            "readable_error_text": readable_error_text,
            "build_common_single_product": build_common_single_product,
            "claim_common_to_tiktok_single": claim_common_to_tiktok_single,
            "get_site_info": get_site_info,
            "get_default_warehouse_ids": get_default_warehouse_ids,
            "save_site_product": save_site_product,
            "claim_tiktok_to_shops": claim_tiktok_to_shops,
            "miaoshou_post": miaoshou_post,
            "cleanup_created_single_product": cleanup_created_single_product,
            "run_root": RUN_ROOT,
        },
    )


def start_single_job(job_id: str, params: dict) -> None:
    job_module.start_daemon(run_single_job, job_id, params)


image_seq_dirs = file_module.image_seq_dirs
image_count_for_seq = file_module.image_count_for_seq
build_preflight_failures = file_module.build_preflight_failures
find_image_base = file_module.find_image_base
resolve_image_layout = file_module.resolve_image_layout


set_job = job_module.set_job
active_job_id_unlocked = job_module.active_job_id_unlocked
progress_html = job_module.progress_html


def active_account_job_id(account_id: str) -> str | None:
    with JOBS_LOCK:
        return active_job_id_unlocked(account_id)


STATUS_LABELS = rendering.STATUS_LABELS
status_label = rendering.status_label
status_badge = rendering.status_badge


readable_error_text = error_module.readable_error_text
readable_job_error = error_module.readable_job_error
ai_status_text = error_module.ai_status_text


job_count_text = job_module.job_count_text


masked_app_key = text_module.masked_app_key
normalized_text = text_module.normalized_text
optional_int = form_module.optional_int


matched_template_name = account_module.matched_template_name
shop_name_from_shops = account_module.shop_name_from_shops


def discover_templates(credentials: tuple[str, str], requested_shop_id: int | None = None) -> tuple[int, dict[str, int], str]:
    return account_module.discover_templates(credentials, miaoshou_post, requested_shop_id)


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
    job_module.start_daemon(run_job, job_id, params)


def render_page(title: str, body: str, refresh: bool = False, header_right: str = "") -> bytes:
    return page_shell.render_page(title, body, refresh, header_right)

def render_account_menu(username: str | None, account_count: int) -> str:
    return rendering.account_menu(account_count)


def render_top_nav(current: str = "batch") -> str:
    return rendering.top_nav(current)


def render_setup_needed() -> bytes:
    return system_pages.render_setup_needed()


def render_release_check(username: str) -> bytes:
    report = self_check.run_release_check(ROOT, ACCOUNTS_PATH)
    return system_pages.render_release_check(report, len(all_account_ids()))


def render_account_row(account_id: str, account: dict) -> str:
    return account_pages.render_account_row(account_id, account, TEMPLATES)


def render_accounts(username: str, message: str = "", error: str = "") -> bytes:
    config = load_accounts_config()
    account_ids = all_account_ids(config)
    return account_pages.render_accounts(config, account_ids, TEMPLATES, message, error)


def render_account_confirm(username: str, token: str) -> bytes:
    with PENDING_ACCOUNTS_LOCK:
        pending = PENDING_ACCOUNTS.get(token)
    return account_pages.render_account_confirm(token, pending, list(TEMPLATES), len(all_account_ids()))


def render_home(username: str) -> bytes:
    config = load_accounts_config()
    account_ids = all_account_ids(config)
    accounts = config.get("accounts", {})
    available_accounts = [(account_id, accounts[account_id]) for account_id in account_ids if account_id in accounts]
    if not available_accounts:
        return render_setup_needed()
    with JOBS_LOCK:
        job_items = list(JOBS.items())
    return batch_pages.render_home(available_accounts, account_ids, job_items, TEMPLATES, DEFAULT_TEMPLATE)


def render_job(job_id: str, username: str | None = None) -> bytes:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    account_count = len(all_account_ids()) if username else 0
    return job_pages.render_job(job_id, job, account_count, bool(username))


def render_attr_control(attr: dict) -> str:
    return single_pages.render_attr_control(attr)


def json_for_html(data: object) -> str:
    return rendering.json_for_html(data)


def selected_category_path(categories: list[dict], cid: str) -> str:
    return single_pages.selected_category_path(categories, cid)


def render_category_picker(categories: list[dict], cid_text: str) -> str:
    return single_pages.render_category_picker(categories, cid_text)


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
    return single_pages.render_single_page(
        username,
        len(account_ids),
        account_options,
        selected_account_id,
        categories,
        cid_text,
        metadata,
        shops,
        message_html,
        SINGLE_IMAGE_LIMIT,
    )


def render_ai_settings(username: str, message: str = "", error: str = "") -> bytes:
    settings = load_ai_settings()
    account_count = len(all_account_ids())
    return ai_pages.render_ai_settings(settings, AI_PROVIDER_PRESETS, message, error, account_count)


def render_failure_page(title: str, error: object, back_url: str, back_label: str, username: str | None = None) -> bytes:
    account_count = len(all_account_ids()) if username else 0
    detail = readable_error_text(error) or str(error)
    return system_pages.render_failure_page(title, detail, back_url, back_label, bool(username), account_count)


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
                    JOBS[job_id] = job_module.single_job_record(
                        title[:60],
                        account_id,
                        account.get("name", account_id),
                        username,
                        image_prefix,
                    )
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
            try:
                form = cgi.FieldStorage(
                    fp=self.rfile,
                    headers=self.headers,
                    environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": self.headers.get("Content-Type", "")},
                )
                config = load_accounts_config()
                location = account_module.handle_account_post(
                    path,
                    form,
                    config,
                    PENDING_ACCOUNTS,
                    PENDING_ACCOUNTS_LOCK,
                    discover_templates,
                    active_account_job_id,
                )
                self.redirect(location)
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
                    JOBS[job_id] = job_module.batch_job_record(
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
