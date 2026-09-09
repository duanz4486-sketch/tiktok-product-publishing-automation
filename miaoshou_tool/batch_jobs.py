from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from . import json_io


def run_batch_job(job_id: str, params: dict[str, Any], deps: dict[str, Any]) -> None:
    def progress(result: dict[str, Any]) -> None:
        with deps["jobs_lock"]:
            job = deps["jobs"][job_id]
            job["done_count"] = job.get("done_count", 0) + 1
            job.setdefault("results", []).append(result)

    try:
        seqs = params.pop("seqs")
        source_files = params.pop("source_files", [])
        preflight_failures = params.pop("preflight_failures", [])
        if params.pop("upload_to_oss", False):
            deps["set_job"](job_id, status="uploading")
            source_uploaded_count = deps["upload_source_files_to_oss"](params["image_prefix"], source_files)
            uploaded_count = deps["upload_images_to_oss"](params["local_image_root"], params["image_prefix"], seqs)
            deps["set_job"](job_id, uploaded_count=uploaded_count, source_uploaded_count=source_uploaded_count)
        if not seqs:
            run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_path = Path(deps["run_root"]) / f"{params['batch']}_{run_id}.json"
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
            deps["set_job"](job_id, status="done_with_errors", summary=summary, log_path=summary["logPath"])
            return
        deps["set_job"](job_id, status="running", started_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        summary = deps["run_batch"](progress=progress, **params)
        if preflight_failures:
            log_path = Path(summary["logPath"])
            data = json_io.read(log_path, {}) or {}
            data["results"] = preflight_failures + (data.get("results") or [])
            summary["total"] = len(data["results"])
            summary["failed"] = preflight_failures + (summary.get("failed") or [])
            data["summary"] = summary
            json_io.write(log_path, data)
        status = "done" if not summary["failed"] else "done_with_errors"
        deps["set_job"](job_id, status=status, summary=summary, log_path=summary["logPath"])
    except Exception as exc:
        deps["set_job"](job_id, status="failed", error=repr(exc))

    deps["set_job"](job_id, finished_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


def start_batch_job(
    start_daemon: Callable[[Callable[[str, dict], None], str, dict], None],
    runner: Callable[[str, dict], None],
    job_id: str,
    params: dict[str, Any],
) -> None:
    start_daemon(runner, job_id, params)
