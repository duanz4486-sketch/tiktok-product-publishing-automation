from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import datetime

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


def base_job_record(
    batch: str,
    account_id: str,
    account_name: str,
    created_by: str,
    template: str,
    image_prefix: str,
    total_count: int,
    done_count: int = 0,
    preflight_failures: list[dict] | None = None,
) -> dict:
    failures = preflight_failures or []
    return {
        "batch": batch,
        "account_id": account_id,
        "account_name": account_name,
        "created_by": created_by,
        "template": template,
        "image_prefix": image_prefix,
        "status": "queued",
        "done_count": done_count,
        "uploaded_count": 0,
        "source_uploaded_count": 0,
        "total_count": total_count,
        "preflight_failed_count": len(failures),
        "preflight_failed_seqs": [item["seq"] for item in failures],
        "results": failures[:],
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def single_job_record(batch: str, account_id: str, account_name: str, created_by: str, image_prefix: str) -> dict:
    return base_job_record(batch, account_id, account_name, created_by, "单产品智能上传", image_prefix, 1)


def batch_job_record(
    batch: str,
    account_id: str,
    account_name: str,
    created_by: str,
    template: str,
    image_prefix: str,
    total_count: int,
    preflight_failures: list[dict],
) -> dict:
    return base_job_record(
        batch,
        account_id,
        account_name,
        created_by,
        template,
        image_prefix,
        total_count,
        done_count=len(preflight_failures),
        preflight_failures=preflight_failures,
    )


def start_daemon(target: Callable[[str, dict], None], job_id: str, params: dict) -> None:
    thread = threading.Thread(target=target, args=(job_id, params), daemon=True)
    thread.start()
