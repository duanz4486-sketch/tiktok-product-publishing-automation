from __future__ import annotations

import threading
from collections.abc import Callable

from miaoshou_tool import rendering


JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()
ACTIVE_STATUSES = {"queued", "uploading", "ai_processing", "running"}


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
    e = rendering.escape
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


def job_count_text(job: dict) -> str:
    done = int(job.get("done_count") or 0)
    total = int(job.get("total_count") or 0)
    return f"{done} / {total}" if total else str(done)


def start_daemon(target: Callable[[str, dict], None], job_id: str, params: dict) -> None:
    thread = threading.Thread(target=target, args=(job_id, params), daemon=True)
    thread.start()
