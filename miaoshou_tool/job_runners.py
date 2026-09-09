from __future__ import annotations

from typing import Any


def _single_deps(namespace: dict[str, Any]) -> dict[str, Any]:
    return {
        "set_job": namespace["set_job"],
        "upload_single_images": namespace["upload_single_images"],
        "upload_single_video": namespace["upload_single_video"],
        "resolve_skus": namespace["resolve_skus"],
        "call_deepseek_ai": namespace["call_deepseek_ai"],
        "merge_ai_attributes": namespace["merge_ai_attributes"],
        "readable_error_text": namespace["readable_error_text"],
        "build_common_single_product": namespace["build_common_single_product"],
        "claim_common_to_tiktok_single": namespace["claim_common_to_tiktok_single"],
        "get_site_info": namespace["get_site_info"],
        "get_default_warehouse_ids": namespace["get_default_warehouse_ids"],
        "save_site_product": namespace["save_site_product"],
        "claim_tiktok_to_shops": namespace["claim_tiktok_to_shops"],
        "miaoshou_post": namespace["miaoshou_post"],
        "cleanup_created_single_product": namespace["cleanup_created_single_product"],
        "run_root": namespace["RUN_ROOT"],
    }


def run_single_job(job_id: str, params: dict, namespace: dict[str, Any]) -> None:
    namespace["single_product_module"].run_single_job(job_id, params, _single_deps(namespace))


def start_single_job(job_id: str, params: dict, namespace: dict[str, Any]) -> None:
    namespace["job_module"].start_daemon(namespace["run_single_job"], job_id, params)


def active_account_job_id(account_id: str, namespace: dict[str, Any]) -> str | None:
    with namespace["JOBS_LOCK"]:
        return namespace["active_job_id_unlocked"](account_id)


def _batch_deps(namespace: dict[str, Any]) -> dict[str, Any]:
    return {
        "jobs": namespace["JOBS"],
        "jobs_lock": namespace["JOBS_LOCK"],
        "set_job": namespace["set_job"],
        "upload_source_files_to_oss": namespace["upload_source_files_to_oss"],
        "upload_images_to_oss": namespace["upload_images_to_oss"],
        "run_batch": namespace["run_batch"],
        "run_root": namespace["RUN_ROOT"],
    }


def run_job(job_id: str, params: dict, namespace: dict[str, Any]) -> None:
    namespace["batch_jobs"].run_batch_job(job_id, params, _batch_deps(namespace))


def start_job(job_id: str, params: dict, namespace: dict[str, Any]) -> None:
    namespace["batch_jobs"].start_batch_job(namespace["job_module"].start_daemon, namespace["run_job"], job_id, params)
