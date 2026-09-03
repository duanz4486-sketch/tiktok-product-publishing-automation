#!/usr/bin/env python3
from __future__ import annotations

import argparse
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning, message="'cgi' is deprecated.*")
import cgi
import hashlib
import hmac
import html
import json
import mimetypes
import os
import re
import secrets
import threading
import urllib.parse
import urllib.request
import uuid
import zipfile
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from batch_tiktok_collect import DEFAULT_TEMPLATE, SHOP_ID, TEMPLATES, VALID_IMAGE_EXTS, post as miaoshou_post, read_items, run_batch

ROOT = Path(__file__).resolve().parent
UPLOAD_ROOT = ROOT / "uploads"
RUN_ROOT = ROOT / "runs"
ACCOUNTS_PATH = ROOT / "accounts.json"
OSS_BUCKET = "duanhah-miaoshou-picture"
OSS_ENDPOINT = "oss-cn-shenzhen.aliyuncs.com"
OSS_REGION = "cn-shenzhen"
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()
ACTIVE_STATUSES = {"queued", "uploading", "running"}
SESSION_COOKIE = "ms_session"
SESSIONS: dict[str, str] = {}
SESSIONS_LOCK = threading.Lock()
PENDING_ACCOUNTS: dict[str, dict] = {}
PENDING_ACCOUNTS_LOCK = threading.Lock()


def e(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def field_text(form: cgi.FieldStorage, name: str, default: str = "") -> str:
    field = form[name] if name in form else None
    if field is None or isinstance(field, list):
        return default
    return str(field.value or default).strip()


def load_accounts_config() -> dict:
    load_local_env()
    if ACCOUNTS_PATH.exists():
        return json.loads(ACCOUNTS_PATH.read_text(encoding="utf-8"))
    password = os.getenv("WEB_PASSWORD", "").strip()
    if not password:
        return {"users": [], "accounts": {}}
    return {
        "users": [{"username": "admin", "password": password, "accounts": ["default"]}],
        "accounts": {
            "default": {
                "name": "默认妙手账号",
                "shop_id": SHOP_ID,
                "templates": {name: data["detail_id"] for name, data in TEMPLATES.items()},
            }
        },
    }


def save_accounts_config(config: dict) -> None:
    ACCOUNTS_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def default_template_ids() -> dict[str, int]:
    return {name: data["detail_id"] for name, data in TEMPLATES.items()}


def user_record(username: str) -> dict | None:
    for user in load_accounts_config().get("users", []):
        if str(user.get("username", "")) == username:
            return user
    return None


def user_record_in_config(config: dict, username: str) -> dict | None:
    for user in config.get("users", []):
        if str(user.get("username", "")) == username:
            return user
    return None


def allowed_account_ids(user: dict) -> list[str]:
    if user.get("accounts"):
        return [str(account_id) for account_id in user["accounts"]]
    if user.get("account_id"):
        return [str(user["account_id"])]
    return []


def verify_password(user: dict, password: str) -> bool:
    saved = str(user.get("password", ""))
    return bool(saved) and hmac.compare_digest(saved, password)


def authenticate(username: str, password: str) -> bool:
    user = user_record(username)
    return bool(user and verify_password(user, password))


def create_session(username: str) -> str:
    token = secrets.token_urlsafe(32)
    with SESSIONS_LOCK:
        SESSIONS[token] = username
    return token


def username_from_cookie(cookie_header: str | None) -> str | None:
    cookie = SimpleCookie(cookie_header or "")
    morsel = cookie.get(SESSION_COOKIE)
    if not morsel:
        return None
    with SESSIONS_LOCK:
        return SESSIONS.get(morsel.value)


def clean_prefix(value: str) -> str:
    return value.strip().replace("\\", "/").strip("/")


def save_upload(form: cgi.FieldStorage, name: str, target: Path) -> None:
    field = form[name] if name in form else None
    if field is None or isinstance(field, list) or not getattr(field, "filename", ""):
        raise ValueError(f"缺少上传文件: {name}")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as out:
        while True:
            chunk = field.file.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)


def extract_zip(zip_path: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    target_root = target.resolve()
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            name = info.filename.replace("\\", "/")
            if not name or name.startswith("/") or "/../" in f"/{name}":
                raise ValueError(f"ZIP 内有不安全路径: {info.filename}")
            output = (target / name).resolve()
            try:
                output.relative_to(target_root)
            except ValueError:
                raise ValueError(f"ZIP 内有不安全路径: {info.filename}")
            if info.is_dir():
                output.mkdir(parents=True, exist_ok=True)
                continue
            output.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as src, output.open("wb") as dst:
                dst.write(src.read())


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


def oss_credentials() -> tuple[str, str, str]:
    load_local_env()
    key_id = os.getenv("OSS_ACCESS_KEY_ID") or os.getenv("ALIYUN_ACCESS_KEY_ID") or os.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID")
    key_secret = os.getenv("OSS_ACCESS_KEY_SECRET") or os.getenv("ALIYUN_ACCESS_KEY_SECRET") or os.getenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET")
    token = os.getenv("OSS_SECURITY_TOKEN") or os.getenv("ALIYUN_SECURITY_TOKEN") or os.getenv("ALIBABA_CLOUD_SECURITY_TOKEN") or ""
    if not key_id or not key_secret:
        raise RuntimeError("未配置 OSS 上传密钥。请在本机 .env 或环境变量里配置 OSS_ACCESS_KEY_ID 和 OSS_ACCESS_KEY_SECRET。")
    return key_id, key_secret, token


def put_oss_object(file_path: Path, object_key: str) -> None:
    key_id, key_secret, token = oss_credentials()
    data = file_path.read_bytes()
    content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    now = datetime.now(timezone.utc)
    oss_date = now.strftime("%Y%m%dT%H%M%SZ")
    scope_date = now.strftime("%Y%m%d")
    canonical_uri = "/" + urllib.parse.quote(f"{OSS_BUCKET}/{object_key}", safe="/~")
    canonical_headers = (
        f"content-type:{content_type}\n"
        "x-oss-content-sha256:UNSIGNED-PAYLOAD\n"
        f"x-oss-date:{oss_date}\n"
    )
    if token:
        canonical_headers += f"x-oss-security-token:{token}\n"
    hashed_request = hashlib.sha256(
        f"PUT\n{canonical_uri}\n\n{canonical_headers}\n\nUNSIGNED-PAYLOAD".encode()
    ).hexdigest()
    scope = f"{scope_date}/{OSS_REGION}/oss/aliyun_v4_request"
    string_to_sign = f"OSS4-HMAC-SHA256\n{oss_date}\n{scope}\n{hashed_request}"
    signing_key = hmac.new(f"aliyun_v4{key_secret}".encode(), scope_date.encode(), hashlib.sha256).digest()
    signing_key = hmac.new(signing_key, OSS_REGION.encode(), hashlib.sha256).digest()
    signing_key = hmac.new(signing_key, b"oss", hashlib.sha256).digest()
    signing_key = hmac.new(signing_key, b"aliyun_v4_request", hashlib.sha256).digest()
    signature = hmac.new(signing_key, string_to_sign.encode(), hashlib.sha256).hexdigest()
    headers = {
        "Authorization": f"OSS4-HMAC-SHA256 Credential={key_id}/{scope},Signature={signature}",
        "Content-Type": content_type,
        "x-oss-content-sha256": "UNSIGNED-PAYLOAD",
        "x-oss-date": oss_date,
    }
    if token:
        headers["x-oss-security-token"] = token
    url = f"https://{OSS_BUCKET}.{OSS_ENDPOINT}/{urllib.parse.quote(object_key, safe='/')}"
    request = urllib.request.Request(url, data=data, headers=headers, method="PUT")
    with urllib.request.urlopen(request, timeout=60) as response:
        if response.status not in {200, 201}:
            raise RuntimeError(f"OSS 上传失败: HTTP {response.status}")


def upload_images_to_oss(image_root: Path, image_prefix: str, seqs: list[int]) -> int:
    count = 0
    for seq in seqs:
        folder = image_root / str(seq)
        if not folder.is_dir():
            continue
        for file_path in sorted(folder.iterdir(), key=lambda p: p.name.lower()):
            if not file_path.is_file() or file_path.suffix.lower() not in VALID_IMAGE_EXTS:
                continue
            put_oss_object(file_path, f"{image_prefix}/{seq}/{file_path.name}")
            count += 1
    return count


def upload_source_files_to_oss(image_prefix: str, source_files: list[tuple[Path, str]]) -> int:
    count = 0
    for file_path, original_name in source_files:
        put_oss_object(file_path, f"{image_prefix}/_source/{original_name}")
        count += 1
    return count


def upload_filename(form: cgi.FieldStorage, name: str, default: str) -> str:
    field = form[name] if name in form else None
    raw_name = getattr(field, "filename", "") if field is not None and not isinstance(field, list) else ""
    clean_name = Path(str(raw_name).replace("\\", "/")).name
    return clean_name or default


def image_seq_dirs(folder: Path) -> set[int]:
    found: set[int] = set()
    for path in folder.iterdir():
        if path.is_dir() and path.name.isdigit():
            found.add(int(path.name))
    return found


def image_count_for_seq(image_root: Path, seq: int) -> int:
    folder = image_root / str(seq)
    if not folder.is_dir():
        return 0
    return sum(1 for path in folder.iterdir() if path.is_file() and path.suffix.lower() in VALID_IMAGE_EXTS)


def build_preflight_failures(items: list[dict], image_root: Path, image_seqs: set[int], include_image_only: bool) -> list[dict]:
    excel_seqs = [int(item["seq"]) for item in items]
    excel_seq_set = set(excel_seqs)
    failures = [
        {"seq": seq, "title": item["title"], "status": "failed", "image_count": 0, "error": "缺少图片文件夹"}
        for item in items
        for seq in [int(item["seq"])]
        if seq not in image_seqs
    ]
    if include_image_only:
        failures.extend(
            {
                "seq": seq,
                "title": "",
                "status": "failed",
                "image_count": image_count_for_seq(image_root, seq),
                "error": "缺少标题",
            }
            for seq in sorted(image_seqs - excel_seq_set)
        )
    return failures


def find_image_base(image_root: Path, seqs: list[int]) -> Path | None:
    needed = set(seqs)
    candidates = [image_root] + [p for p in image_root.rglob("*") if p.is_dir() and p.name != "__MACOSX"]
    best: tuple[int, Path] | None = None
    for folder in candidates:
        score = len(image_seq_dirs(folder) & needed)
        if score and (best is None or score > best[0]):
            best = (score, folder)
        if score == len(needed):
            return folder
    return best[1] if best else None


def resolve_image_layout(image_root: Path, batch: str, seqs: list[int], image_prefix: str = "") -> tuple[Path, str]:
    image_prefix = clean_prefix(image_prefix)
    dirs = [p for p in image_root.iterdir() if p.is_dir() and p.name != "__MACOSX"]
    base = find_image_base(image_root, seqs)
    if not base:
        names = "、".join(p.name for p in dirs[:8]) or "空"
        raise ValueError(f"ZIP 顶层应是一个图片目录，或直接是 1、2、3 这些序号文件夹；当前是：{names}")
    if image_prefix:
        prefix = image_prefix
    elif base == image_root:
        prefix = batch
    else:
        try:
            prefix = base.relative_to(image_root).parts[0]
        except ValueError:
            prefix = batch

    return base, prefix


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
  <div class="progress">
    <div class="bar" style="width: {percent}%"></div>
  </div>
  <p class="hint">进度：{done} / {total or "未知"}，{percent}%　已上传源文件：{e(job.get("source_uploaded_count", 0))}　已上传图片：{e(job.get("uploaded_count", 0))}　预检失败：{e(job.get("preflight_failed_count", 0))}</p>"""


def readable_job_error(job: dict) -> str:
    error = str(job.get("error") or "")
    if not error:
        return ""
    if "appNotFound" in error:
        return "妙手应用不存在或已关闭：检查该妙手账号的 App Key/App Secret 是否正确且应用已启用"
    if "查询 TikTok 详情失败" in error:
        return "查询 TikTok 模板失败：检查妙手账号、模板 ID 是否属于同一个账号"
    if "Miaoshou HTTP" in error:
        return "妙手接口请求失败：" + error[:180]
    return error[:220]


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
            log_path.write_text(json.dumps({"summary": summary, "results": preflight_failures}, ensure_ascii=False, indent=2), encoding="utf-8")
            set_job(job_id, status="done_with_errors", summary=summary, log_path=summary["logPath"])
            return
        set_job(job_id, status="running", started_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        summary = run_batch(progress=progress, **params)
        if preflight_failures:
            log_path = Path(summary["logPath"])
            data = json.loads(log_path.read_text(encoding="utf-8"))
            data["results"] = preflight_failures + (data.get("results") or [])
            summary["total"] = len(data["results"])
            summary["failed"] = preflight_failures + (summary.get("failed") or [])
            data["summary"] = summary
            log_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
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
    input, select {{
      width: 100%;
      min-height: 40px;
      border: 1px solid #b9c5d0;
      border-radius: 6px;
      padding: 8px 10px;
      background: #fff;
      color: var(--ink);
      font: inherit;
    }}
    input:focus, select:focus, button:focus {{ outline: 2px solid var(--focus); outline-offset: 2px; }}
    .grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }}
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
    .menu-logout {{ width: 100%; }}
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
    @media (max-width: 720px) {{
      header {{ padding: 18px; }}
      main {{ padding: 14px; }}
      .grid {{ grid-template-columns: 1fr; }}
      table {{ display: block; overflow-x: auto; }}
    }}
  </style>
</head>
<body>
  <header><h1>妙手 TikTok 批量上货工具</h1>{header_right}</header>
  <main>{body}</main>
</body>
</html>""".encode("utf-8")


def render_account_menu(username: str, account_count: int) -> str:
    avatar = (username[:1] or "?").upper()
    return f"""
<details class="account">
  <summary aria-label="账户"><span class="avatar">{e(avatar)}</span></summary>
  <div class="account-panel">
    <p class="account-name">{e(username)}</p>
    <p class="account-meta">可用妙手账号：{e(account_count)}</p>
    <a class="account-link" href="/accounts">妙手账号管理</a>
    <form action="/logout" method="post"><button type="submit" class="ghost menu-logout">退出登录</button></form>
  </div>
</details>"""


def render_login(error: str = "") -> bytes:
    error_html = f'<p class="failed">{e(error)}</p>' if error else ""
    body = f"""
<section>
  <h2>登录</h2>
  {error_html}
  <form action="/login" method="post">
    <div class="grid">
      <div>
        <label for="username">用户名</label>
        <input id="username" name="username" required autocomplete="username">
      </div>
      <div>
        <label for="password">密码</label>
        <input id="password" name="password" type="password" required autocomplete="current-password">
      </div>
    </div>
    <div class="actions"><button type="submit">登录</button></div>
  </form>
</section>"""
    return render_page("登录", body)


def render_setup_needed() -> bytes:
    body = """
<section>
  <h2>还没有配置团队账号</h2>
  <p class="hint">请在本机创建 accounts.json，或者在 .env 里先配置 WEB_PASSWORD 临时使用单账号模式。真实妙手密钥不要放进 GitHub。</p>
</section>"""
    return render_page("需要配置", body)


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
            <form action="/accounts/toggle-lock" method="post">
              <input type="hidden" name="account_id" value="{e(account_id)}">
              <button type="submit" class="lock-switch {lock_class}">
                <span class="lock-track"></span><span>{lock_text}</span>
              </button>
            </form>
          </td>
          <td>
            <div class="account-actions">
            <form action="/accounts/update" method="post" class="account-edit-form">
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
              <div class="actions-row"><button type="submit" class="ghost" {disabled}>保存</button></div>
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
    user = user_record(username)
    if not user:
        return render_login("登录已失效，请重新登录。")
    accounts = config.get("accounts", {})
    account_ids = allowed_account_ids(user)
    rows = "".join(
        render_account_row(account_id, account)
        for account_id, account in ((account_id, accounts[account_id]) for account_id in account_ids if account_id in accounts)
    )
    if not rows:
        rows = '<tr><td colspan="5" class="hint">还没有妙手账号</td></tr>'
    template_inputs = "\n".join(
        f"""<div>
        <label for="template_{e(name)}">{e(name)}模板 ID</label>
        <input id="template_{e(name)}" name="template_{e(name)}" type="number" placeholder="留空自动识别">
      </div>"""
        for name, data in TEMPLATES.items()
    )
    message_html = f'<p class="done">{e(message)}</p>' if message else ""
    error_html = f'<p class="failed">{e(error)}</p>' if error else ""
    header_right = render_account_menu(username, len(account_ids))
    body = f"""
<section>
  <h2>妙手账号管理</h2>
  {message_html}
  {error_html}
  <p><a href="/">返回上货页面</a></p>
  <table>
    <thead><tr><th>妙手账号名称</th><th>妙手账号</th><th>接口应用</th><th>账号锁</th><th>修改信息</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</section>
<section>
  <h2>新增妙手账号</h2>
  <form action="/accounts/add" method="post">
    <div class="grid">
      <div>
        <label for="name">妙手账号名称</label>
        <input id="name" name="name" required placeholder="例如：小王账号、美国店1号">
      </div>
      <div>
        <label for="shop_id">妙手账号</label>
        <input id="shop_id" name="shop_id" type="number" placeholder="留空自动识别">
      </div>
      <div>
        <label for="app_key">APP ID / App Key</label>
        <input id="app_key" name="app_key" required autocomplete="off">
      </div>
      <div>
        <label for="app_secret">App Secret</label>
        <input id="app_secret" name="app_secret" type="password" required autocomplete="off">
      </div>
      {template_inputs}
      <p class="hint wide">妙手账号名称只给网页下拉框使用；妙手开放平台里的 APP ID 填到「APP ID / App Key」，App Secret 填到「App Secret」。妙手账号和模板 ID 可留空，程序会按「大地毯、非定制毛毯、定制毛毯」三个关键词自动识别。</p>
    </div>
    <div class="actions"><button type="submit">保存妙手账号</button></div>
  </form>
</section>"""
    return render_page("妙手账号管理", body, header_right=header_right)


def render_account_confirm(username: str, token: str) -> bytes:
    with PENDING_ACCOUNTS_LOCK:
        pending = PENDING_ACCOUNTS.get(token)
    if not pending or pending.get("username") != username:
        return render_page("确认已失效", '<section><h2>确认已失效</h2><p><a href="/accounts">返回妙手账号管理</a></p></section>')
    templates = pending.get("templates") or {}
    template_rows = "".join(
        f"<tr><td>{e(name)}</td><td>{e(templates.get(name))}</td></tr>"
        for name in TEMPLATES
    )
    shop_name = pending.get("shop_name") or "妙手接口未返回店铺名称，请核对 shopId"
    body = f"""
<section>
  <h2>确认妙手账号</h2>
  <p class="hint">请确认下面识别结果属于你要保存的妙手账号。确认后才会保存；取消则不会保存。</p>
  <table>
    <tbody>
      <tr><th>妙手账号名称</th><td>{e(pending.get("name"))}</td></tr>
      <tr><th>识别到的店铺名称</th><td>{e(shop_name)}</td></tr>
      <tr><th>识别到的 shopId</th><td>{e(pending.get("shop_id"))}</td></tr>
      <tr><th>接口应用</th><td>{e(masked_app_key(pending.get("app_key")))} / Secret 已配置</td></tr>
    </tbody>
  </table>
  <h2>识别到的模板</h2>
  <table>
    <thead><tr><th>产品模板</th><th>模板 ID</th></tr></thead>
    <tbody>{template_rows}</tbody>
  </table>
  <form action="/accounts/confirm" method="post" class="actions">
    <input type="hidden" name="token" value="{e(token)}">
    <button type="submit" name="action" value="save">确认保存</button>
    <button type="submit" name="action" value="cancel" class="ghost">取消</button>
  </form>
</section>"""
    return render_page("确认妙手账号", body, header_right=render_account_menu(username, len(allowed_account_ids(user_record(username) or {}))))


def render_home(username: str) -> bytes:
    config = load_accounts_config()
    user = user_record(username)
    if not user:
        return render_login("登录已失效，请重新登录。")
    account_ids = allowed_account_ids(user)
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
    active_notice = ""
    if active_pairs:
        active_items = "".join(
            f"""<p class="hint">账号：{e(job.get("account_name"))}　批次：{e(job.get("batch"))}　<a href="/job?id={e(job_id)}">查看进度</a></p>
  {progress_html(job)}"""
            for job_id, job in active_pairs[:3]
        )
        active_notice = f"""
<section class="notice">
  <h2>有账号正在处理</h2>
  <p class="hint">同一个妙手账号完成前不能提交下一批；其他空闲妙手账号可以继续使用。</p>
  {active_items}
</section>"""
    job_rows = "".join(
        f"""<tr>
          <td><a href="/job?id={e(job_id)}">{e(job.get("batch"))}</a></td>
          <td>{e(job.get("account_name"))}</td>
          <td>{e(job.get("created_by"))}</td>
          <td>{e(job.get("template"))}</td>
          <td class="status {e(job.get("status"))}">{e(job.get("status"))}</td>
          <td>{e(job.get("done_count", 0))}</td>
          <td>{e(readable_job_error(job))}</td>
          <td>{e(job.get("created_at"))}</td>
        </tr>"""
        for job_id, job in rows
    )
    if not job_rows:
        job_rows = '<tr><td colspan="8" class="hint">还没有任务</td></tr>'
    header_right = render_account_menu(username, len(available_accounts))
    body = f"""
{active_notice}
<section>
  <h2>新建批次</h2>
  <form action="/run" method="post" enctype="multipart/form-data">
    <fieldset {disabled}>
    <div class="grid">
      <div>
        <label for="account_id">妙手账号</label>
        <select id="account_id" name="account_id">{account_options}</select>
      </div>
      <div>
        <label for="batch">批次名</label>
        <input id="batch" name="batch" required placeholder="只作为任务名称，例如：第1批">
      </div>
      <div>
        <label for="template">产品模板</label>
        <select id="template" name="template">{options}</select>
      </div>
      <div>
        <label for="image_prefix">OSS 图片目录</label>
        <input id="image_prefix" name="image_prefix" placeholder="可不填；ZIP 顶层是图片目录时自动识别">
      </div>
      <div>
        <label for="title_file">标题 Excel</label>
        <input id="title_file" name="title_file" type="file" accept=".xlsx,.xlsm" required>
      </div>
      <div>
        <label for="image_zip">图片 ZIP</label>
        <input id="image_zip" name="image_zip" type="file" accept=".zip" required>
      </div>
      <div>
        <label for="limit">只处理前几个产品</label>
        <input id="limit" name="limit" type="number" min="1" placeholder="留空就是全部">
      </div>
      <div class="row" style="padding-top: 24px;">
        <input id="upload_to_oss" name="upload_to_oss" type="checkbox" checked>
        <label for="upload_to_oss" style="margin: 0;">自动上传图片到 OSS</label>
      </div>
      <div class="row" style="padding-top: 24px;">
        <input id="dry_run" name="dry_run" type="checkbox" checked>
        <label for="dry_run" style="margin: 0;">先预检，不创建产品</label>
      </div>
      <p class="hint wide">以本次上传的 Excel 和图片 ZIP 为准；匹配只看 Excel 的序号列和 ZIP 子文件夹名字。两边都有的序号会处理，缺标题或缺图片的序号会记为失败。勾选自动上传后，程序会用本次 Excel、ZIP 和 ZIP 图片上传并覆盖 OSS 同路径旧文件。</p>
    </div>
    <div class="actions"><button type="submit" {disabled}>{'当前账号处理中' if locked else '开始处理'}</button></div>
    </fieldset>
  </form>
</section>
<section>
  <h2>最近任务</h2>
  <table>
    <thead><tr><th>批次</th><th>妙手账号</th><th>提交人</th><th>模板</th><th>状态</th><th>已处理</th><th>失败原因</th><th>创建时间</th></tr></thead>
    <tbody>{job_rows}</tbody>
  </table>
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
          <td class="status {e(item.get("status"))}">{e(item.get("status"))}</td>
          <td>{'复用旧产品' if item.get("reused_existing") or item.get("reused_from_log") else '新建' if item.get("status") == "success" else ''}</td>
          <td>{e(item.get("image_count"))}</td>
          <td>{e(item.get("tiktokDetailId"))}</td>
          <td>{e(item.get("error"))}</td>
        </tr>"""
        for item in job.get("results", [])
    )
    if not rows:
        rows = '<tr><td colspan="6" class="hint">等待开始</td></tr>'
    body = f"""
<section>
  <h2>{e(job.get("batch"))}</h2>
  <p class="hint">妙手账号：{e(job.get("account_name"))}　提交人：{e(job.get("created_by"))}　模板：{e(job.get("template"))}　OSS 图片目录：{e(job.get("image_prefix"))}　状态：<span class="status {e(job.get("status"))}">{e(job.get("status"))}</span>　已处理：{e(job.get("done_count", 0))}</p>
  {progress_html(job)}
  <p class="hint">预检失败序号：{e("、".join(str(seq) for seq in job.get("preflight_failed_seqs", [])[:30]))}</p>
  <p class="hint">日志：{e(job.get("log_path") or summary.get("logPath") or "")}</p>
  <p class="hint">{e(job.get("error", ""))}</p>
  <p><a href="/">返回首页</a></p>
</section>
<section>
  <h2>处理结果</h2>
  <table>
    <thead><tr><th>序号</th><th>状态</th><th>处理方式</th><th>图片数</th><th>TikTok ID</th><th>失败原因</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</section>"""
    account_count = len(allowed_account_ids(user_record(username) or {})) if username else 0
    header_right = render_account_menu(username, account_count) if username else ""
    return render_page("批次结果", body, refresh=refresh, header_right=header_right)


class Handler(BaseHTTPRequestHandler):
    def current_username(self) -> str | None:
        return username_from_cookie(self.headers.get("Cookie"))

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

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/login":
            self.send_html(render_login())
            return
        username = self.current_username()
        if not username:
            self.redirect("/login")
            return
        if parsed.path == "/":
            self.send_html(render_home(username))
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
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": self.headers.get("Content-Type", "")},
            )
            username = field_text(form, "username")
            password = field_text(form, "password")
            if not authenticate(username, password):
                self.send_html(render_login("用户名或密码不正确"), 401)
                return
            token = create_session(username)
            self.send_response(303)
            self.send_header("Location", "/")
            self.send_header("Set-Cookie", f"{SESSION_COOKIE}={token}; HttpOnly; SameSite=Lax; Path=/")
            self.end_headers()
            return
        if path == "/logout":
            cookie = SimpleCookie(self.headers.get("Cookie", ""))
            morsel = cookie.get(SESSION_COOKIE)
            if morsel:
                with SESSIONS_LOCK:
                    SESSIONS.pop(morsel.value, None)
            self.send_response(303)
            self.send_header("Location", "/login")
            self.send_header("Set-Cookie", f"{SESSION_COOKIE}=; Max-Age=0; HttpOnly; SameSite=Lax; Path=/")
            self.end_headers()
            return
        if path in {"/accounts/add", "/accounts/confirm", "/accounts/rename", "/accounts/update", "/accounts/delete", "/accounts/toggle-lock"}:
            username = self.current_username()
            if not username:
                self.redirect("/login")
                return
            try:
                form = cgi.FieldStorage(
                    fp=self.rfile,
                    headers=self.headers,
                    environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": self.headers.get("Content-Type", "")},
                )
                config = load_accounts_config()
                user = user_record_in_config(config, username)
                if not user:
                    raise ValueError("登录已失效，请重新登录")
                accounts = config.setdefault("accounts", {})
                user_accounts = allowed_account_ids(user)
                if path == "/accounts/confirm":
                    token = field_text(form, "token")
                    action = field_text(form, "action", "save")
                    with PENDING_ACCOUNTS_LOCK:
                        pending = PENDING_ACCOUNTS.pop(token, None)
                    if not pending or pending.get("username") != username:
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
                    user.setdefault("accounts", user_accounts).append(account_id)
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
                        "username": username,
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
        username = self.current_username()
        if not username:
            self.redirect("/login")
            return
        try:
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": self.headers.get("Content-Type", "")},
            )
            config = load_accounts_config()
            user = user_record(username)
            if not user:
                raise ValueError("登录已失效，请重新登录")
            account_id = field_text(form, "account_id")
            if account_id not in allowed_account_ids(user):
                raise ValueError("当前用户没有这个妙手账号权限")
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
            zip_path = upload_dir / "images.zip"
            image_root = upload_dir / "images"
            title_original_name = upload_filename(form, "title_file", "title.xlsx")
            zip_original_name = upload_filename(form, "image_zip", "images.zip")
            save_upload(form, "title_file", title_path)
            save_upload(form, "image_zip", zip_path)
            extract_zip(zip_path, image_root)
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
                raise ValueError(f"本次 ZIP 里没有任何能和 Excel 序号对应的图片文件夹。当前识别到的图片序号是：{found_text}")
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
                self.send_html(render_page("这个账号正在处理", f'<section><h2>这个妙手账号正在处理</h2><p>同一个妙手账号完成前不能提交下一批，避免标题和图片错配。</p><p><a href="/job?id={e(active_id)}">查看当前批次</a></p></section>', refresh=True), 409)
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
                "source_files": [(title_path, title_original_name), (zip_path, zip_original_name)],
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
            self.send_html(render_page("创建任务失败", f'<section><h2>创建任务失败</h2><p>{e(exc)}</p><p><a href="/">返回首页</a></p></section>'), 400)

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
