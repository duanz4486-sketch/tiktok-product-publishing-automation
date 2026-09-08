from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
UPLOAD_ROOT = ROOT / "uploads"
RUN_ROOT = ROOT / "runs"
ACCOUNTS_PATH = ROOT / "accounts.json"
AI_SETTINGS_PATH = ROOT / "ai_settings.json"

OSS_BUCKET = "duanhah-miaoshou-picture"
OSS_ENDPOINT = "oss-cn-shenzhen.aliyuncs.com"
OSS_REGION = "cn-shenzhen"

SITE = "US"
DEFAULT_OPERATOR = "网页操作"
SINGLE_IMAGE_LIMIT = 9
VALID_VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".webm"}
MIN_AI_DESCRIPTION_CHARS = 1000

