#!/usr/bin/env python3
from __future__ import annotations

import argparse
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning, message="'cgi' is deprecated.*")
import cgi
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

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
from miaoshou_tool import http_context
from miaoshou_tool import http_server
from miaoshou_tool import job_runners
from miaoshou_tool import jobs as job_module
from miaoshou_tool import json_io
from miaoshou_tool import miaoshou_api
from miaoshou_tool import oss_upload
from miaoshou_tool import page_shell
from miaoshou_tool import page_requests
from miaoshou_tool import publishing as publishing_module
from miaoshou_tool import rendering
from miaoshou_tool import self_check
from miaoshou_tool import service_bridge
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
    service_bridge.load_local_env(globals())


def oss_credentials() -> tuple[str, str, str]:
    return service_bridge.oss_credentials(globals())


def put_oss_object(file_path: Path, object_key: str) -> None:
    service_bridge.put_oss_object(file_path, object_key, globals())


def upload_images_to_oss(image_root: Path, image_prefix: str, seqs: list[int]) -> int:
    return service_bridge.upload_images_to_oss(image_root, image_prefix, seqs, globals())


def upload_source_files_to_oss(image_prefix: str, source_files: list[tuple[Path, str]]) -> int:
    return service_bridge.upload_source_files_to_oss(image_prefix, source_files, globals())


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
    return service_bridge.get_tiktok_shops(credentials, globals())


pick_warehouse = miaoshou_api.pick_warehouse


def get_default_warehouse_ids(shop_ids: list[int], credentials: tuple[str, str]) -> dict[str, str]:
    return service_bridge.get_default_warehouse_ids(shop_ids, credentials, globals())


flatten_category_tree = miaoshou_api.flatten_category_tree


def load_categories(credentials: tuple[str, str]) -> list[dict]:
    return service_bridge.load_categories(credentials, globals())


def get_category_metadata(cid: int, credentials: tuple[str, str], shop_ids: list[int] | None = None) -> dict:
    return service_bridge.get_category_metadata(cid, credentials, shop_ids, globals())


save_uploaded_file = file_module.save_uploaded_file
uploaded_image_files = file_module.uploaded_image_files
uploaded_sku_image_files = file_module.uploaded_sku_image_files
uploaded_video_file = file_module.uploaded_video_file


def upload_single_images(files: list[Path], object_prefix: str) -> list[str]:
    return service_bridge.upload_single_images(files, object_prefix, globals())


def upload_single_video(file_path: Path | None, object_prefix: str) -> str:
    return service_bridge.upload_single_video(file_path, object_prefix, globals())


def load_ai_settings() -> dict:
    return service_bridge.load_ai_settings(globals())


def save_ai_settings(settings: dict) -> None:
    service_bridge.save_ai_settings(settings, globals())


image_data_url = ai_module.image_data_url
attr_prompt_rows = ai_module.attr_prompt_rows
ai_suggestion_prompt = ai_module.ai_suggestion_prompt
extract_json_object = ai_module.extract_json_object
ai_provider_label = ai_module.ai_provider_label
normalize_chat_completions_url = ai_module.normalize_chat_completions_url


def call_openai_compatible_chat(settings: dict, content: list[dict], timeout: int = 90) -> str:
    return service_bridge.call_openai_compatible_chat(settings, content, timeout, globals())


def call_deepseek_ai(title: str, notes: str, image_files: list[Path], metadata: dict) -> dict:
    return service_bridge.call_deepseek_ai(title, notes, image_files, metadata, globals())


def test_ai_settings(settings: dict) -> None:
    service_bridge.test_ai_settings(settings, globals())


def ai_settings_from_form(form: cgi.FieldStorage) -> dict:
    return service_bridge.ai_settings_from_form(form, globals())


def settings_for_ai_test(posted: dict) -> dict:
    return service_bridge.settings_for_ai_test(posted, globals())


def ai_configured() -> bool:
    return service_bridge.ai_configured(globals())


def merge_ai_attributes(product_attrs: list[dict], suggestion_attrs: list[dict], metadata: dict) -> list[dict]:
    return service_bridge.merge_ai_attributes(product_attrs, suggestion_attrs, metadata, globals())


def build_common_single_product(item_num: str, credentials: tuple[str, str], title: str, notes: str, image_urls: list[str], skus: list[dict], spec_name: str, weight: float, package_length: float, package_width: float, package_height: float, video_url: str = "") -> int:
    return service_bridge.build_common_single_product(
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
        video_url,
        globals(),
    )


def build_product_attributes(form: cgi.FieldStorage, metadata: dict) -> list[dict]:
    return service_bridge.build_product_attributes(form, metadata, globals())


custom_value_id = publishing_module.custom_value_id


def get_site_info(detail_id: int, credentials: tuple[str, str]) -> tuple[str, dict]:
    return service_bridge.get_site_info(detail_id, credentials, globals())


def save_site_product(detail_id: int, credentials: tuple[str, str], site_info: dict, oss_md5: str, title: str, notes: str, image_urls: list[str], cid: int, product_attrs: list[dict], sale_attr_id: str, spec_name: str, skus: list[dict], shop_ids: list[int], weight: float, package_length: float, package_width: float, package_height: float, warehouse_ids: dict[str, str] | None = None, video_url: str = "") -> None:
    service_bridge.save_site_product(
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
        warehouse_ids,
        video_url,
        globals(),
    )


def claim_tiktok_to_shops(detail_id: int, shop_ids: list[int], credentials: tuple[str, str]) -> None:
    service_bridge.claim_tiktok_to_shops(detail_id, shop_ids, credentials, globals())


def claim_common_to_tiktok_single(common_id: int, credentials: tuple[str, str]) -> int:
    return service_bridge.claim_common_to_tiktok_single(common_id, credentials, globals())


def delete_common_collect_products(detail_ids: list[int], credentials: tuple[str, str]) -> None:
    service_bridge.delete_common_collect_products(detail_ids, credentials, globals())


def delete_tiktok_collect_products(detail_ids: list[int], credentials: tuple[str, str]) -> None:
    service_bridge.delete_tiktok_collect_products(detail_ids, credentials, globals())


def cleanup_created_single_product(common_id: int | None, detail_id: int | None, credentials: tuple[str, str]) -> list[str]:
    return service_bridge.cleanup_created_single_product(common_id, detail_id, credentials, globals())


resolve_skus = publishing_module.resolve_skus


def parse_sku_rows(form: cgi.FieldStorage, sku_image_paths: dict[str, Path] | None = None) -> tuple[str, str, list[dict]]:
    return service_bridge.parse_sku_rows(form, sku_image_paths, globals())


def run_single_job(job_id: str, params: dict) -> None:
    job_runners.run_single_job(job_id, params, globals())


def start_single_job(job_id: str, params: dict) -> None:
    job_runners.start_single_job(job_id, params, globals())


image_seq_dirs = file_module.image_seq_dirs
image_count_for_seq = file_module.image_count_for_seq
build_preflight_failures = file_module.build_preflight_failures
find_image_base = file_module.find_image_base
resolve_image_layout = file_module.resolve_image_layout


set_job = job_module.set_job
active_job_id_unlocked = job_module.active_job_id_unlocked
progress_html = job_module.progress_html


def active_account_job_id(account_id: str) -> str | None:
    return job_runners.active_account_job_id(account_id, globals())


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
    return service_bridge.discover_templates(credentials, requested_shop_id, globals())


def run_job(job_id: str, params: dict) -> None:
    job_runners.run_job(job_id, params, globals())


def start_job(job_id: str, params: dict) -> None:
    job_runners.start_job(job_id, params, globals())


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


def handler_deps() -> dict[str, object]:
    return http_context.route_deps(globals())


Handler = http_server.make_handler(handler_deps, json_io.dumps)


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
