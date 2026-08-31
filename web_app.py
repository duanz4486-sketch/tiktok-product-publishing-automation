#!/usr/bin/env python3
from __future__ import annotations

import argparse
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning, message="'cgi' is deprecated.*")
import cgi
import hashlib
import hmac
import html
import mimetypes
import os
import threading
import urllib.parse
import urllib.request
import uuid
import zipfile
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from batch_tiktok_collect import DEFAULT_TEMPLATE, TEMPLATES, VALID_IMAGE_EXTS, read_items, run_batch

ROOT = Path(__file__).resolve().parent
UPLOAD_ROOT = ROOT / "uploads"
RUN_ROOT = ROOT / "runs"
OSS_BUCKET = "duanhah-miaoshou-picture"
OSS_ENDPOINT = "oss-cn-shenzhen.aliyuncs.com"
OSS_REGION = "cn-shenzhen"
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()
ACTIVE_STATUSES = {"queued", "uploading", "running"}


def e(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def field_text(form: cgi.FieldStorage, name: str, default: str = "") -> str:
    field = form[name] if name in form else None
    if field is None or isinstance(field, list):
        return default
    return str(field.value or default).strip()


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


def resolve_image_layout(image_root: Path, batch: str, seqs: list[int], image_prefix: str = "") -> tuple[Path, str]:
    image_prefix = clean_prefix(image_prefix)
    dirs = [p for p in image_root.iterdir() if p.is_dir() and p.name != "__MACOSX"]
    if all((image_root / str(seq)).is_dir() for seq in seqs):
        base = image_root
        prefix = image_prefix or batch
    elif (image_root / batch).is_dir():
        base = image_root / batch
        prefix = image_prefix or batch
    elif len(dirs) == 1:
        base = dirs[0]
        prefix = image_prefix or dirs[0].name
    else:
        names = "、".join(p.name for p in dirs[:8]) or "空"
        raise ValueError(f"ZIP 顶层应是一个图片目录，或直接是 1、2、3 这些序号文件夹；当前是：{names}")

    missing = [str(seq) for seq in seqs if not (base / str(seq)).is_dir()]
    if missing:
        shown = "、".join(missing[:20])
        more = "..." if len(missing) > 20 else ""
        raise ValueError(f"ZIP 缺少图片子文件夹：{shown}{more}。Excel 序号列必须和 ZIP 子文件夹名一致。")
    return base, prefix


def set_job(job_id: str, **values) -> None:
    with JOBS_LOCK:
        JOBS[job_id].update(values)


def active_job_id_unlocked() -> str | None:
    for job_id, job in reversed(list(JOBS.items())):
        if job.get("status") in ACTIVE_STATUSES:
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
  <p class="hint">进度：{done} / {total or "未知"}，{percent}%　已上传图片：{e(job.get("uploaded_count", 0))}</p>"""


def run_job(job_id: str, params: dict) -> None:
    def progress(result: dict) -> None:
        with JOBS_LOCK:
            job = JOBS[job_id]
            job["done_count"] = job.get("done_count", 0) + 1
            job.setdefault("results", []).append(result)

    try:
        seqs = params.pop("seqs")
        if params.pop("upload_to_oss", False):
            set_job(job_id, status="uploading")
            uploaded_count = upload_images_to_oss(params["local_image_root"], params["image_prefix"], seqs)
            set_job(job_id, uploaded_count=uploaded_count)
        set_job(job_id, status="running", started_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        summary = run_batch(progress=progress, **params)
        status = "done" if not summary["failed"] else "done_with_errors"
        set_job(job_id, status=status, summary=summary, log_path=summary["logPath"])
    except Exception as exc:
        set_job(job_id, status="failed", error=repr(exc))

    set_job(job_id, finished_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


def start_job(job_id: str, params: dict) -> None:
    thread = threading.Thread(target=run_job, args=(job_id, params), daemon=True)
    thread.start()


def render_page(title: str, body: str, refresh: bool = False) -> bytes:
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
  <header><h1>妙手 TikTok 批量上货工具</h1></header>
  <main>{body}</main>
</body>
</html>""".encode("utf-8")


def render_home() -> bytes:
    options = "\n".join(
        f'<option value="{e(name)}" {"selected" if name == DEFAULT_TEMPLATE else ""}>{e(name)}</option>'
        for name in TEMPLATES
    )
    with JOBS_LOCK:
        active_id = active_job_id_unlocked()
        active_job = JOBS.get(active_id) if active_id else None
        rows = list(JOBS.items())[-10:][::-1]
    locked = active_job is not None
    disabled = "disabled" if locked else ""
    active_notice = ""
    if active_job and active_id:
        active_notice = f"""
<section class="notice">
  <h2>当前批次还在处理</h2>
  <p class="hint">批次：{e(active_job.get("batch"))}。完成前不能提交下一批，避免标题和图片错配。</p>
  {progress_html(active_job)}
  <p><a href="/job?id={e(active_id)}">查看当前批次</a></p>
</section>"""
    job_rows = "".join(
        f"""<tr>
          <td><a href="/job?id={e(job_id)}">{e(job.get("batch"))}</a></td>
          <td>{e(job.get("template"))}</td>
          <td class="status {e(job.get("status"))}">{e(job.get("status"))}</td>
          <td>{e(job.get("done_count", 0))}</td>
          <td>{e(job.get("created_at"))}</td>
        </tr>"""
        for job_id, job in rows
    )
    if not job_rows:
        job_rows = '<tr><td colspan="5" class="hint">还没有任务</td></tr>'
    body = f"""
{active_notice}
<section>
  <h2>新建批次</h2>
  <form action="/run" method="post" enctype="multipart/form-data">
    <fieldset {disabled}>
    <div class="grid">
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
      <p class="hint wide">上传文件名、批次名、ZIP 顶层目录不需要互相一致；匹配只看 Excel 的序号列和 ZIP 子文件夹名字。勾选自动上传后，程序会先把 ZIP 里的图片传到 OSS，再检查链接并处理妙手产品。</p>
    </div>
    <div class="actions"><button type="submit" {disabled}>{'处理中，暂不能提交' if locked else '开始处理'}</button></div>
    </fieldset>
  </form>
</section>
<section>
  <h2>最近任务</h2>
  <table>
    <thead><tr><th>批次</th><th>模板</th><th>状态</th><th>已处理</th><th>创建时间</th></tr></thead>
    <tbody>{job_rows}</tbody>
  </table>
</section>"""
    return render_page("妙手 TikTok 批量上货工具", body, refresh=locked)


def render_job(job_id: str) -> bytes:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        return render_page("任务不存在", '<section><h2>任务不存在</h2><p><a href="/">返回首页</a></p></section>')
    refresh = job.get("status") in {"queued", "running"}
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
        rows = '<tr><td colspan="5" class="hint">等待开始</td></tr>'
    body = f"""
<section>
  <h2>{e(job.get("batch"))}</h2>
  <p class="hint">模板：{e(job.get("template"))}　OSS 图片目录：{e(job.get("image_prefix"))}　状态：<span class="status {e(job.get("status"))}">{e(job.get("status"))}</span>　已处理：{e(job.get("done_count", 0))}</p>
  {progress_html(job)}
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
    return render_page("批次结果", body, refresh=refresh)


class Handler(BaseHTTPRequestHandler):
    def send_html(self, content: bytes, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.send_html(render_home())
            return
        if parsed.path == "/job":
            job_id = parse_qs(parsed.query).get("id", [""])[0]
            self.send_html(render_job(job_id))
            return
        self.send_html(render_page("未找到", '<section><h2>未找到</h2><p><a href="/">返回首页</a></p></section>'), 404)

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/run":
            self.send_html(render_page("未找到", '<section><h2>未找到</h2></section>'), 404)
            return
        try:
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": self.headers.get("Content-Type", "")},
            )
            batch = field_text(form, "batch")
            template = field_text(form, "template", DEFAULT_TEMPLATE)
            image_prefix = field_text(form, "image_prefix")
            if not batch:
                raise ValueError("请填写批次名")
            if template not in TEMPLATES:
                raise ValueError("请选择有效的产品模板")
            limit_text = field_text(form, "limit")
            limit = int(limit_text) if limit_text else None
            dry_run = "dry_run" in form
            upload_to_oss = "upload_to_oss" in form

            job_id = datetime.now().strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:8]
            upload_dir = UPLOAD_ROOT / job_id
            title_path = upload_dir / "title.xlsx"
            zip_path = upload_dir / "images.zip"
            image_root = upload_dir / "images"
            save_upload(form, "title_file", title_path)
            save_upload(form, "image_zip", zip_path)
            extract_zip(zip_path, image_root)
            items = read_items(title_path)
            if limit:
                items = items[:limit]
            image_root, image_prefix = resolve_image_layout(image_root, batch, [int(item["seq"]) for item in items], image_prefix)
            total_count = len(items)

            with JOBS_LOCK:
                active_id = active_job_id_unlocked()
                if not active_id:
                    JOBS[job_id] = {
                        "batch": batch,
                        "template": template,
                        "image_prefix": image_prefix,
                        "status": "queued",
                        "done_count": 0,
                        "uploaded_count": 0,
                        "total_count": total_count,
                        "results": [],
                        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }
            if active_id:
                self.send_html(render_page("已有批次处理中", f'<section><h2>已有批次处理中</h2><p>上一批还没完成，暂时不能提交下一批。</p><p><a href="/job?id={e(active_id)}">查看当前批次</a></p></section>', refresh=True), 409)
                return
            params = {
                "batch": batch,
                "title_file": title_path,
                "local_image_root": image_root,
                "image_prefix": image_prefix,
                "template": template,
                "limit": limit,
                "dry_run": dry_run,
                "upload_to_oss": upload_to_oss,
                "seqs": [int(item["seq"]) for item in items],
                "reuse_existing": False,
                "log_dir": RUN_ROOT,
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
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"打开 http://127.0.0.1:{args.port}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
