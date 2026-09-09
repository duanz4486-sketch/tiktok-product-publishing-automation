from __future__ import annotations

import cgi
import urllib.parse
from urllib.parse import parse_qs, urlparse


ACCOUNT_POST_PATHS = {
    "/accounts/add",
    "/accounts/confirm",
    "/accounts/rename",
    "/accounts/update",
    "/accounts/delete",
    "/accounts/toggle-lock",
}


def _read_form(handler) -> cgi.FieldStorage:
    return cgi.FieldStorage(
        fp=handler.rfile,
        headers=handler.headers,
        environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": handler.headers.get("Content-Type", "")},
    )


def _redirect_to_job(handler, job_id: str) -> None:
    handler.send_response(303)
    handler.send_header("Location", f"/job?id={job_id}")
    handler.end_headers()


def _send_active_job(handler, current: str, message: str, active_id: str, account_count: int, username: str, deps: dict) -> None:
    body = (
        f'{deps["render_top_nav"](current)}'
        f'<section>{deps["alert_html"]("warn", message)}'
        f'<p><a href="/job?id={deps["e"](active_id)}">查看当前{"批次" if current == "batch" else "任务"}</a></p></section>'
    )
    handler.send_html(
        deps["render_page"](
            "这个账号正在处理",
            body,
            refresh=True,
            header_right=deps["render_account_menu"](username, account_count),
        ),
        409,
    )


def handle_get(handler, deps: dict) -> None:
    parsed = urlparse(handler.path)
    if parsed.path == "/login":
        handler.redirect("/")
        return
    username = deps["DEFAULT_OPERATOR"]
    if parsed.path == "/":
        handler.send_html(deps["render_home"](username))
        return
    if parsed.path == "/check":
        handler.send_html(deps["render_release_check"](username))
        return
    if parsed.path == "/single":
        handler.send_html(deps["render_single"](username, parse_qs(parsed.query)))
        return
    if parsed.path == "/ai-settings":
        query = parse_qs(parsed.query)
        handler.send_html(deps["render_ai_settings"](username, query.get("message", [""])[0], query.get("error", [""])[0]))
        return
    if parsed.path == "/accounts":
        query = parse_qs(parsed.query)
        handler.send_html(deps["render_accounts"](username, query.get("message", [""])[0], query.get("error", [""])[0]))
        return
    if parsed.path == "/accounts/confirm":
        token = parse_qs(parsed.query).get("token", [""])[0]
        handler.send_html(deps["render_account_confirm"](username, token))
        return
    if parsed.path == "/job":
        job_id = parse_qs(parsed.query).get("id", [""])[0]
        handler.send_html(deps["render_job"](job_id, username))
        return
    handler.send_html(deps["render_page"]("未找到", '<section><h2>未找到</h2><p><a href="/">返回首页</a></p></section>'), 404)


def handle_post(handler, deps: dict) -> None:
    path = urlparse(handler.path).path
    if path == "/login":
        handler.redirect("/")
        return
    if path == "/logout":
        handler.redirect("/")
        return
    if path == "/ai-settings":
        try:
            form = _read_form(handler)
            handler.redirect(
                deps["ai_requests"].handle_ai_settings_form(
                    form,
                    {
                        "ai_settings_from_form": deps["ai_settings_from_form"],
                        "field_text": deps["field_text"],
                        "test_ai_settings": deps["test_ai_settings"],
                        "settings_for_ai_test": deps["settings_for_ai_test"],
                        "save_ai_settings": deps["save_ai_settings"],
                    },
                )
            )
        except Exception as exc:
            handler.redirect("/ai-settings?error=" + urllib.parse.quote(str(exc)))
        return
    if path == "/single/ai-suggest":
        try:
            form = _read_form(handler)
            suggestion = deps["ai_requests"].suggest_single_product(
                form,
                {
                    "load_accounts_config": deps["load_accounts_config"],
                    "field_text": deps["field_text"],
                    "field_list": deps["field_list"],
                    "int_field": deps["int_field"],
                    "account_credentials": deps["account_credentials"],
                    "require_english": deps["require_english"],
                    "get_category_metadata": deps["get_category_metadata"],
                    "uploaded_image_files": deps["uploaded_image_files"],
                    "upload_root": deps["UPLOAD_ROOT"],
                    "call_deepseek_ai": deps["call_deepseek_ai"],
                },
            )
            handler.send_json({"ok": True, "suggestion": suggestion})
        except Exception as exc:
            handler.send_json({"ok": False, "error": deps["readable_error_text"](exc) or str(exc)}, 400)
        return
    if path == "/single/create":
        username = deps["DEFAULT_OPERATOR"]
        try:
            form = _read_form(handler)
            result = deps["single_requests"].create_single_job(
                form,
                username,
                {
                    "load_accounts_config": deps["load_accounts_config"],
                    "all_account_ids": deps["all_account_ids"],
                    "field_text": deps["field_text"],
                    "field_list": deps["field_list"],
                    "int_field": deps["int_field"],
                    "decimal_field": deps["decimal_field"],
                    "account_credentials": deps["account_credentials"],
                    "require_english": deps["require_english"],
                    "get_category_metadata": deps["get_category_metadata"],
                    "build_product_attributes": deps["build_product_attributes"],
                    "uploaded_sku_image_files": deps["uploaded_sku_image_files"],
                    "parse_sku_rows": deps["parse_sku_rows"],
                    "uploaded_image_files": deps["uploaded_image_files"],
                    "uploaded_video_file": deps["uploaded_video_file"],
                    "clean_prefix": deps["clean_prefix"],
                    "upload_root": deps["UPLOAD_ROOT"],
                    "jobs": deps["JOBS"],
                    "jobs_lock": deps["JOBS_LOCK"],
                    "active_job_id_unlocked": deps["active_job_id_unlocked"],
                    "single_job_record": deps["job_module"].single_job_record,
                    "start_single_job": deps["start_single_job"],
                },
            )
            if result["status"] == "active":
                _send_active_job(
                    handler,
                    "single",
                    "这个妙手账号正在处理上一批。同一个妙手账号完成前不能提交下一批。",
                    result["active_id"],
                    int(result["account_count"]),
                    username,
                    deps,
                )
                return
            _redirect_to_job(handler, result["job_id"])
        except Exception as exc:
            handler.send_html(deps["render_failure_page"]("创建单产品任务失败", exc, "/single", "返回单产品上传", username), 400)
        return
    if path in ACCOUNT_POST_PATHS:
        try:
            form = _read_form(handler)
            config = deps["load_accounts_config"]()
            location = deps["account_module"].handle_account_post(
                path,
                form,
                config,
                deps["PENDING_ACCOUNTS"],
                deps["PENDING_ACCOUNTS_LOCK"],
                deps["discover_templates"],
                deps["active_account_job_id"],
            )
            handler.redirect(location)
        except Exception as exc:
            handler.redirect("/accounts?error=" + urllib.parse.quote(str(exc)))
        return
    if path != "/run":
        handler.send_html(deps["render_page"]("未找到", "<section><h2>未找到</h2></section>"), 404)
        return
    username = deps["DEFAULT_OPERATOR"]
    try:
        form = _read_form(handler)
        result = deps["batch_requests"].create_batch_job(
            form,
            username,
            {
                "load_accounts_config": deps["load_accounts_config"],
                "all_account_ids": deps["all_account_ids"],
                "field_text": deps["field_text"],
                "upload_filename": deps["upload_filename"],
                "save_upload": deps["save_upload"],
                "stage_batch_images": deps["stage_batch_images"],
                "read_items": deps["read_items"],
                "resolve_image_layout": deps["resolve_image_layout"],
                "image_seq_dirs": deps["image_seq_dirs"],
                "build_preflight_failures": deps["build_preflight_failures"],
                "upload_root": deps["UPLOAD_ROOT"],
                "run_root": deps["RUN_ROOT"],
                "accounts_path": deps["ACCOUNTS_PATH"],
                "jobs": deps["JOBS"],
                "jobs_lock": deps["JOBS_LOCK"],
                "active_job_id_unlocked": deps["active_job_id_unlocked"],
                "batch_job_record": deps["job_module"].batch_job_record,
                "start_job": deps["start_job"],
                "templates": deps["TEMPLATES"],
                "default_template": deps["DEFAULT_TEMPLATE"],
                "default_shop_id": deps["SHOP_ID"],
            },
        )
        if result["status"] == "active":
            _send_active_job(
                handler,
                "batch",
                "这个妙手账号正在处理上一批。同一个妙手账号完成前不能提交下一批，避免标题和图片错配。",
                result["active_id"],
                int(result["account_count"]),
                username,
                deps,
            )
            return
        _redirect_to_job(handler, result["job_id"])
    except Exception as exc:
        handler.send_html(deps["render_failure_page"]("创建任务失败", exc, "/", "返回首页", username), 400)
