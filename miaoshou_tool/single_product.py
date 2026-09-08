from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from . import json_io


def cleanup_created_single_product(
    common_id: int | None,
    detail_id: int | None,
    credentials: tuple[str, str],
    delete_tiktok_collect_products,
    delete_common_collect_products,
) -> list[str]:
    errors: list[str] = []
    if detail_id is not None:
        try:
            delete_tiktok_collect_products([detail_id], credentials)
        except Exception as exc:
            errors.append(f"TikTok 草稿删除失败：{exc!r}")
    if common_id is not None:
        try:
            delete_common_collect_products([common_id], credentials)
        except Exception as exc:
            errors.append(f"公共采集箱草稿删除失败：{exc!r}")
    return errors


def run_single_job(job_id: str, params: dict[str, Any], deps: dict[str, Any]) -> None:
    result: dict[str, object] = {"seq": "单品", "status": "started", "image_count": len(params["image_files"])}
    common_id: int | None = None
    detail_id: int | None = None
    try:
        deps["set_job"](job_id, status="uploading")
        image_urls = deps["upload_single_images"](params["image_files"], params["image_prefix"])
        video_url = deps["upload_single_video"](params.get("video_file"), params["image_prefix"])
        for row in params["sku_rows"]:
            sku_image_path = row.get("image_path")
            if sku_image_path:
                row["image_url"] = deps["upload_single_images"]([sku_image_path], f"{params['image_prefix']}/sku")[0]
        deps["set_job"](job_id, uploaded_count=len(image_urls))
        skus = deps["resolve_skus"](params["sku_rows"], image_urls, params["weight"])
        notes = params["notes"]
        product_attrs = list(params["product_attrs"])
        ai_status: dict[str, object] = {"status": "skipped", "reason": "已在页面应用 AI 建议或未请求 AI"}
        if params.get("auto_ai"):
            deps["set_job"](job_id, status="ai_processing")
            try:
                suggestion = deps["call_deepseek_ai"](
                    params["title"],
                    "" if params.get("notes_is_fallback") else notes,
                    params["image_files"],
                    params["metadata"],
                )
                if params.get("notes_is_fallback") and suggestion.get("description_html"):
                    notes = str(suggestion["description_html"])
                product_attrs = deps["merge_ai_attributes"](product_attrs, suggestion.get("attributes") or [], params["metadata"])
                ai_status = {
                    "status": "success",
                    "description": "已生成" if not params.get("notes_is_fallback") else ("已采用" if notes != params["notes"] else "未采用"),
                    "attributeCount": len(suggestion.get("attributes") or []),
                    "warnings": suggestion.get("warnings") or [],
                }
            except Exception as exc:
                ai_status = {"status": "failed", "error": deps["readable_error_text"](exc) or repr(exc)}
                result["ai"] = ai_status
                raise RuntimeError("AI 处理失败：" + ai_status["error"]) from exc
        result["ai"] = ai_status
        deps["set_job"](job_id, status="running")
        common_id = deps["build_common_single_product"](
            params["item_num"],
            params["credentials"],
            params["title"],
            notes,
            image_urls,
            skus,
            params["spec_name"],
            params["weight"],
            params["package_length"],
            params["package_width"],
            params["package_height"],
            video_url,
        )
        detail_id = deps["claim_common_to_tiktok_single"](common_id, params["credentials"])
        oss_md5, site_info = deps["get_site_info"](detail_id, params["credentials"])
        warehouse_ids = deps["get_default_warehouse_ids"](params["shop_ids"], params["credentials"])
        deps["save_site_product"](
            detail_id,
            params["credentials"],
            site_info,
            oss_md5,
            params["title"],
            notes,
            image_urls,
            params["cid"],
            product_attrs,
            params["sale_attr_id"],
            params["spec_name"],
            skus,
            params["shop_ids"],
            params["weight"],
            params["package_length"],
            params["package_width"],
            params["package_height"],
            warehouse_ids,
            video_url,
        )
        deps["claim_tiktok_to_shops"](detail_id, params["shop_ids"], params["credentials"])
        shop_results = []
        for shop_id in params["shop_ids"]:
            try:
                deps["miaoshou_post"]("get_tk_shop_collect_item_info", {"detailId": detail_id, "shopId": shop_id}, params["credentials"])
                shop_results.append({"shopId": shop_id, "status": "success"})
            except Exception as exc:
                shop_results.append({"shopId": shop_id, "status": "failed", "error": repr(exc)})
        result.update(
            {
                "status": "success" if all(item["status"] == "success" for item in shop_results) else "done_with_errors",
                "commonCollectBoxDetailId": common_id,
                "tiktokDetailId": detail_id,
                "shopResults": shop_results,
                "image_count": len(image_urls),
            }
        )
    except Exception as exc:
        result.update({"status": "failed", "error": repr(exc)})
        cleanup_errors = deps["cleanup_created_single_product"](common_id, detail_id, params["credentials"])
        if cleanup_errors:
            result["cleanupErrors"] = cleanup_errors
    log_path = Path(deps["run_root"]) / f"single_{job_id}.json"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    json_io.write(log_path, json_io.job_log(result, [result]))
    deps["set_job"](
        job_id,
        status="done" if result["status"] == "success" else "failed",
        done_count=1,
        total_count=1,
        results=[result],
        summary=result,
        log_path=str(log_path.resolve()),
        finished_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
