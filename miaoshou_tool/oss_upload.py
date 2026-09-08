from __future__ import annotations

import hashlib
import hmac
import mimetypes
import os
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from batch_tiktok_collect import VALID_IMAGE_EXTS

from .accounts import load_local_env
from .config import OSS_BUCKET, OSS_ENDPOINT, OSS_REGION


PutObject = Callable[[Path, str], None]


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


def object_url(object_key: str) -> str:
    return f"https://{OSS_BUCKET}.{OSS_ENDPOINT}/{urllib.parse.quote(object_key, safe='/')}"


def upload_images_to_oss(image_root: Path, image_prefix: str, seqs: list[int], put_object: PutObject = put_oss_object) -> int:
    count = 0
    for seq in seqs:
        folder = image_root / str(seq)
        if not folder.is_dir():
            continue
        for file_path in sorted(folder.iterdir(), key=lambda p: p.name.lower()):
            if not file_path.is_file() or file_path.suffix.lower() not in VALID_IMAGE_EXTS:
                continue
            put_object(file_path, f"{image_prefix}/{seq}/{file_path.name}")
            count += 1
    return count


def upload_source_files_to_oss(image_prefix: str, source_files: list[tuple[Path, str]], put_object: PutObject = put_oss_object) -> int:
    count = 0
    for file_path, original_name in source_files:
        put_object(file_path, f"{image_prefix}/_source/{original_name}")
        count += 1
    return count


def upload_single_images(files: list[Path], object_prefix: str, put_object: PutObject = put_oss_object) -> list[str]:
    def upload_one(file_path: Path) -> str:
        object_key = f"{object_prefix}/{file_path.name}"
        put_object(file_path, object_key)
        return object_url(object_key)

    if len(files) <= 1:
        return [upload_one(file_path) for file_path in files]
    with ThreadPoolExecutor(max_workers=min(4, len(files))) as pool:
        return list(pool.map(upload_one, files))


def upload_single_video(file_path: Path | None, object_prefix: str, put_object: PutObject = put_oss_object) -> str:
    if not file_path:
        return ""
    object_key = f"{object_prefix}/video/{file_path.name}"
    put_object(file_path, object_key)
    return object_url(object_key)

