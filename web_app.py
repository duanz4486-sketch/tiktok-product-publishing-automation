#!/usr/bin/env python3
from __future__ import annotations

import argparse
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning, message="'cgi' is deprecated.*")
import cgi
import threading
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from batch_tiktok_collect import DEFAULT_TEMPLATE, SHOP_ID, TEMPLATES, post as miaoshou_post, read_items, run_batch
from miaoshou_tool import accounts as account_module
from miaoshou_tool import ai as ai_module
from miaoshou_tool import ai_requests
from miaoshou_tool import batch_jobs
from miaoshou_tool import batch_requests
from miaoshou_tool import config as config_module
from miaoshou_tool import errors as error_module
from miaoshou_tool import files as file_module
from miaoshou_tool import forms as form_module
from miaoshou_tool import jobs as job_module
from miaoshou_tool import json_io
from miaoshou_tool import miaoshou_api
from miaoshou_tool import oss_upload
from miaoshou_tool import page_shell
from miaoshou_tool import page_requests
from miaoshou_tool import publishing as publishing_module
from miaoshou_tool import rendering
from miaoshou_tool import self_check
from miaoshou_tool import single_product as single_product_module
from miaoshou_tool import single_pages
from miaoshou_tool import single_requests
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
    batch_jobs.run_batch_job(
        job_id,
        params,
        {
            "jobs": JOBS,
            "jobs_lock": JOBS_LOCK,
            "set_job": set_job,
            "upload_source_files_to_oss": upload_source_files_to_oss,
            "upload_images_to_oss": upload_images_to_oss,
            "run_batch": run_batch,
            "run_root": RUN_ROOT,
        },
    )


def start_job(job_id: str, params: dict) -> None:
    batch_jobs.start_batch_job(job_module.start_daemon, run_job, job_id, params)


def render_page(title: str, body: str, refresh: bool = False, header_right: str = "") -> bytes:
    return page_shell.render_page(title, body, refresh, header_right)

def render_account_menu(username: str | None, account_count: int) -> str:
    return rendering.account_menu(account_count)


def render_top_nav(current: str = "batch") -> str:
    return rendering.top_nav(current)


def render_setup_needed() -> bytes:
    return system_pages.render_setup_needed()


def render_release_check(username: str) -> bytes:
    return page_requests.render_release_check(
        {
            "run_release_check": self_check.run_release_check,
            "root": ROOT,
            "accounts_path": ACCOUNTS_PATH,
            "all_account_ids": all_account_ids,
        }
    )


def render_account_row(account_id: str, account: dict) -> str:
    return page_requests.render_account_row(account_id, account, {"templates": TEMPLATES})


def render_accounts(username: str, message: str = "", error: str = "") -> bytes:
    return page_requests.render_accounts(
        message,
        error,
        {
            "load_accounts_config": load_accounts_config,
            "all_account_ids": all_account_ids,
            "templates": TEMPLATES,
        },
    )


def render_account_confirm(username: str, token: str) -> bytes:
    return page_requests.render_account_confirm(
        token,
        {
            "pending_accounts": PENDING_ACCOUNTS,
            "pending_accounts_lock": PENDING_ACCOUNTS_LOCK,
            "templates": TEMPLATES,
            "all_account_ids": all_account_ids,
        },
    )


def render_home(username: str) -> bytes:
    return page_requests.render_home(
        {
            "load_accounts_config": load_accounts_config,
            "all_account_ids": all_account_ids,
            "jobs": JOBS,
            "jobs_lock": JOBS_LOCK,
            "templates": TEMPLATES,
            "default_template": DEFAULT_TEMPLATE,
        }
    )


def render_job(job_id: str, username: str | None = None) -> bytes:
    return page_requests.render_job(
        job_id,
        username,
        {
            "jobs": JOBS,
            "jobs_lock": JOBS_LOCK,
            "all_account_ids": all_account_ids,
        },
    )


def render_attr_control(attr: dict) -> str:
    return single_pages.render_attr_control(attr)


def json_for_html(data: object) -> str:
    return rendering.json_for_html(data)


def selected_category_path(categories: list[dict], cid: str) -> str:
    return single_pages.selected_category_path(categories, cid)


def render_category_picker(categories: list[dict], cid_text: str) -> str:
    return single_pages.render_category_picker(categories, cid_text)


def render_single(username: str, query: dict[str, list[str]] | None = None, error: str = "") -> bytes:
    return page_requests.render_single(
        username,
        query,
        error,
        {
            "load_accounts_config": load_accounts_config,
            "all_account_ids": all_account_ids,
            "account_credentials": account_credentials,
            "get_tiktok_shops": get_tiktok_shops,
            "load_categories": load_categories,
            "get_category_metadata": get_category_metadata,
            "single_image_limit": SINGLE_IMAGE_LIMIT,
        },
    )


def render_ai_settings(username: str, message: str = "", error: str = "") -> bytes:
    return page_requests.render_ai_settings(
        message,
        error,
        {
            "load_ai_settings": load_ai_settings,
            "all_account_ids": all_account_ids,
            "ai_provider_presets": AI_PROVIDER_PRESETS,
        },
    )


def render_failure_page(title: str, error: object, back_url: str, back_label: str, username: str | None = None) -> bytes:
    return page_requests.render_failure_page(
        title,
        error,
        back_url,
        back_label,
        username,
        {
            "all_account_ids": all_account_ids,
            "readable_error_text": readable_error_text,
        },
    )


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
            try:
                form = cgi.FieldStorage(
                    fp=self.rfile,
                    headers=self.headers,
                    environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": self.headers.get("Content-Type", "")},
                )
                self.redirect(
                    ai_requests.handle_ai_settings_form(
                        form,
                        {
                            "ai_settings_from_form": ai_settings_from_form,
                            "field_text": field_text,
                            "test_ai_settings": test_ai_settings,
                            "settings_for_ai_test": settings_for_ai_test,
                            "save_ai_settings": save_ai_settings,
                        },
                    )
                )
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
                suggestion = ai_requests.suggest_single_product(
                    form,
                    {
                        "load_accounts_config": load_accounts_config,
                        "field_text": field_text,
                        "field_list": field_list,
                        "int_field": int_field,
                        "account_credentials": account_credentials,
                        "require_english": require_english,
                        "get_category_metadata": get_category_metadata,
                        "uploaded_image_files": uploaded_image_files,
                        "upload_root": UPLOAD_ROOT,
                        "call_deepseek_ai": call_deepseek_ai,
                    },
                )
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
                result = single_requests.create_single_job(
                    form,
                    username,
                    {
                        "load_accounts_config": load_accounts_config,
                        "all_account_ids": all_account_ids,
                        "field_text": field_text,
                        "field_list": field_list,
                        "int_field": int_field,
                        "decimal_field": decimal_field,
                        "account_credentials": account_credentials,
                        "require_english": require_english,
                        "get_category_metadata": get_category_metadata,
                        "build_product_attributes": build_product_attributes,
                        "uploaded_sku_image_files": uploaded_sku_image_files,
                        "parse_sku_rows": parse_sku_rows,
                        "uploaded_image_files": uploaded_image_files,
                        "uploaded_video_file": uploaded_video_file,
                        "clean_prefix": clean_prefix,
                        "upload_root": UPLOAD_ROOT,
                        "jobs": JOBS,
                        "jobs_lock": JOBS_LOCK,
                        "active_job_id_unlocked": active_job_id_unlocked,
                        "single_job_record": job_module.single_job_record,
                        "start_single_job": start_single_job,
                    },
                )
                if result["status"] == "active":
                    active_id = result["active_id"]
                    account_count = int(result["account_count"])
                    body = f"""{render_top_nav("single")}<section>{alert_html("warn", "这个妙手账号正在处理上一批。同一个妙手账号完成前不能提交下一批。")}<p><a href="/job?id={e(active_id)}">查看当前任务</a></p></section>"""
                    self.send_html(render_page("这个账号正在处理", body, refresh=True, header_right=render_account_menu(username, account_count)), 409)
                    return
                self.send_response(303)
                self.send_header("Location", f"/job?id={result['job_id']}")
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
            result = batch_requests.create_batch_job(
                form,
                username,
                {
                    "load_accounts_config": load_accounts_config,
                    "all_account_ids": all_account_ids,
                    "field_text": field_text,
                    "upload_filename": upload_filename,
                    "save_upload": save_upload,
                    "stage_batch_images": stage_batch_images,
                    "read_items": read_items,
                    "resolve_image_layout": resolve_image_layout,
                    "image_seq_dirs": image_seq_dirs,
                    "build_preflight_failures": build_preflight_failures,
                    "upload_root": UPLOAD_ROOT,
                    "run_root": RUN_ROOT,
                    "accounts_path": ACCOUNTS_PATH,
                    "jobs": JOBS,
                    "jobs_lock": JOBS_LOCK,
                    "active_job_id_unlocked": active_job_id_unlocked,
                    "batch_job_record": job_module.batch_job_record,
                    "start_job": start_job,
                    "templates": TEMPLATES,
                    "default_template": DEFAULT_TEMPLATE,
                    "default_shop_id": SHOP_ID,
                },
            )
            if result["status"] == "active":
                active_id = result["active_id"]
                account_count = int(result["account_count"])
                body = f"""{render_top_nav("batch")}<section>{alert_html("warn", "这个妙手账号正在处理上一批。同一个妙手账号完成前不能提交下一批，避免标题和图片错配。")}<p><a href="/job?id={e(active_id)}">查看当前批次</a></p></section>"""
                self.send_html(render_page("这个账号正在处理", body, refresh=True, header_right=render_account_menu(username, account_count)), 409)
                return
            self.send_response(303)
            self.send_header("Location", f"/job?id={result['job_id']}")
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
