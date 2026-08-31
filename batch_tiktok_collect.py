#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

MIAOSHOU_MCP_DIR = Path(r"C:\Users\Admin\Documents\ChatGPT\codex\miaoshou_mcp")
sys.path.insert(0, str(MIAOSHOU_MCP_DIR))
import server  # type: ignore  # noqa: E402

TITLE_ROOT = Path(r"D:\图片\标题\最终标题")
LOCAL_IMAGE_ROOT = Path(r"D:\图片")
OSS_BASE_URL = "https://duanhah-miaoshou-picture.oss-cn-shenzhen.aliyuncs.com"
SHOP_ID = 13781675
TEMPLATE_TITLE = "tiktok chan pin mo ban"
TEMPLATE_DETAIL_ID = 3325026487
VALID_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def post(endpoint_key: str, body: dict[str, Any]) -> dict[str, Any]:
    for attempt in range(4):
        response = server._post_to_miaoshou(server.ENDPOINTS[endpoint_key], body)
        if response.get("code") != "accountApiQpsRateLimit":
            return response
        time.sleep(2 + attempt * 2)
    return response


def natural_key(value: str) -> list[Any]:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", value)]


def batch_from_title_file(path: Path) -> str:
    name = path.stem
    return name.removeprefix("最终标题_")


def title_file_for_batch(batch: str) -> Path:
    return TITLE_ROOT / f"最终标题_{batch}.xlsx"


def read_items(title_file: Path) -> list[dict[str, Any]]:
    wb = load_workbook(title_file, data_only=True)
    ws = wb.active
    items: list[dict[str, Any]] = []
    for row in range(2, ws.max_row + 1):
        seq = ws.cell(row, 1).value
        title = ws.cell(row, 3).value
        if seq in (None, "") and title in (None, ""):
            continue
        if not isinstance(seq, (int, float)) or int(seq) != seq:
            raise ValueError(f"row {row}: A列序号不是整数")
        title_text = str(title or "").strip()
        if not 25 <= len(title_text) <= 255:
            raise ValueError(f"seq {int(seq)}: 标题长度 {len(title_text)} 不在 25-255 范围")
        items.append({"seq": int(seq), "title": title_text, "excel_row": row})
    return items


def image_urls(batch: str, seq: int) -> list[str]:
    folder = LOCAL_IMAGE_ROOT / batch / str(seq)
    if not folder.exists():
        raise FileNotFoundError(f"缺少图片文件夹: {folder}")
    files = sorted(
        [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in VALID_IMAGE_EXTS],
        key=lambda p: natural_key(p.name),
    )
    if not files:
        raise ValueError(f"图片文件夹为空: {folder}")
    if len(files) > 15:
        raise ValueError(f"seq {seq}: 图片数量 {len(files)} 超过妙手限制 15 张")
    return [
        f"{OSS_BASE_URL}/{urllib.parse.quote(f'{batch}/{seq}/{file.name}', safe='/')}"
        for file in files
    ]


def check_url(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(request, timeout=15, context=ssl.create_default_context()) as response:
        return {
            "status": response.status,
            "content_type": response.headers.get("Content-Type"),
            "content_length": int(response.headers.get("Content-Length") or 0),
        }


def find_template_detail_id(template_title: str, shop_id: int) -> int:
    for page in range(1, 6):
        response = post(
            "search_tk_collect_products",
            {"pageNo": page, "pageSize": 100, "status": "notPublished", "title": template_title},
        )
        for item in (response.get("data") or {}).get("detailList") or []:
            shops = item.get("collectBoxDetailShopList") or []
            if item.get("title") == template_title and any(str(s.get("shopId")) == str(shop_id) for s in shops):
                return int(item["collectBoxDetailId"])
    raise RuntimeError(f"未找到 TikTok 模板产品: {template_title}")


def get_tk_info(detail_id: int, shop_id: int) -> tuple[str, dict[str, Any]]:
    response = post("get_tk_shop_collect_item_info", {"detailId": detail_id, "shopId": shop_id})
    if response.get("result") != "success":
        raise RuntimeError(f"查询 TikTok 详情失败: {response}")
    data = response.get("data") or {}
    oss_md5 = data.get("ossMd5")
    info = data.get("shopCollectItemInfo")
    if not oss_md5 or not isinstance(info, dict):
        raise RuntimeError(f"TikTok 详情缺少 ossMd5/shopCollectItemInfo: {response}")
    return str(oss_md5), info


def create_common_product(title: str, urls: list[str], template_info: dict[str, Any], item_num: str) -> int:
    body = {
        "title": title,
        "itemNum": item_num[:50],
        "notesText": "Area rug batch product.",
        "notes": template_info.get("notes") or "<p>Area rug batch product.</p>",
        "sourceAttrs": [],
        "price": first_template_price(template_info),
        "stock": 0,
        "imgUrls": urls,
        "weight": template_info.get("weight") or 8,
        "packageLength": template_info.get("packageLength") or 50,
        "packageWidth": template_info.get("packageWidth") or 45,
        "packageHeight": template_info.get("packageHeight") or 40,
    }
    response = post("create_common_collect_product", body)
    if response.get("result") != "success":
        raise RuntimeError(f"创建公共采集箱产品失败: {response}")
    return int((response.get("data") or {})["commonCollectBoxDetailId"])


def first_template_price(template_info: dict[str, Any]) -> float:
    sku_map = template_info.get("skuMap") or {}
    for sku in sku_map.values():
        price = sku.get("priceIncludeVat") or sku.get("price") or sku.get("originPrice")
        if price:
            return float(price)
    return 79.49


def claim_to_tiktok(common_id: int) -> int:
    body = {
        "detailSerialNumberPlatformList": [
            {"detailId": common_id, "platform": "tiktok", "serialNumber": 1}
        ]
    }
    response = server._post_to_miaoshou(server.ENDPOINTS["claim_common_products_to_platform"], body)
    if response.get("result") != "success":
        raise RuntimeError(f"认领到 TikTok 失败: {response}")
    mapping = ((response.get("data") or {}).get("platformCollectBoxDetailIdMap") or {}).get("tiktok") or {}
    if str(common_id) not in mapping:
        raise RuntimeError(f"认领成功但未返回 TikTok detailId: {response}")
    return int(mapping[str(common_id)])


def find_existing_by_title(title: str, shop_id: int) -> dict[str, Any] | None:
    for page in range(1, 6):
        response = post(
            "search_tk_collect_products",
            {"pageNo": page, "pageSize": 100, "status": "notPublished", "title": title},
        )
        for item in (response.get("data") or {}).get("detailList") or []:
            shops = item.get("collectBoxDetailShopList") or []
            if item.get("title") == title and any(str(s.get("shopId")) == str(shop_id) for s in shops):
                return item
    return None


def save_from_template(
    detail_id: int,
    shop_id: int,
    title: str,
    urls: list[str],
    template_info: dict[str, Any],
) -> dict[str, Any]:
    oss_md5, _ = get_tk_info(detail_id, shop_id)
    info = copy.deepcopy(template_info)
    info.update(
        {
            "detailId": detail_id,
            "shopId": shop_id,
            "title": title,
            "oriTitle": title,
            "imgUrls": urls,
            "deliveryOptionSetType": "default",
        }
    )
    if not info.get("sizeChart"):
        info.pop("sizeChart", None)
        info.pop("sizeChartType", None)
    for shop in info.get("collectBoxDetailShopList") or []:
        shop["shopId"] = shop_id
        shop.setdefault("site", info.get("site", "US"))
        shop.setdefault("deliveryOptionSetType", "default")
    response = post(
        "save_tk_shop_collect_item_info",
        {"ossMd5": oss_md5, "detailId": detail_id, "shopId": shop_id, "shopCollectItemInfo": info},
    )
    if response.get("result") != "success":
        raise RuntimeError(f"保存 TikTok 详情失败: {response}")
    return response


def verify_product(detail_id: int, shop_id: int, title: str, urls: list[str], template_info: dict[str, Any]) -> dict[str, Any]:
    _, info = get_tk_info(detail_id, shop_id)
    sizes = [
        value.get("attrValue")
        for prop in info.get("skuPropertyList") or []
        if prop.get("attrName") == "Size"
        for value in prop.get("attrValueList") or []
    ]
    return {
        "title_ok": info.get("title") == title,
        "images_ok": (info.get("imgUrls") or []) == urls,
        "image_count": len(info.get("imgUrls") or []),
        "cid_ok": info.get("cid") == template_info.get("cid"),
        "sku_count": len(info.get("skuMap") or {}),
        "sizes": sizes,
    }


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def previous_successes(batch: str) -> dict[int, dict[str, Any]]:
    runs = sorted(Path("runs").glob(f"{batch}_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    found: dict[int, dict[str, Any]] = {}
    for path in runs:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for item in data.get("results") or []:
            if item.get("status") == "success" and item.get("tiktokDetailId") and item.get("seq") not in found:
                found[int(item["seq"])] = item
    return found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", default="万圣节测试")
    parser.add_argument("--title-file")
    parser.add_argument("--shop-id", type=int, default=SHOP_ID)
    parser.add_argument("--template-title", default=TEMPLATE_TITLE)
    parser.add_argument("--template-detail-id", type=int, default=TEMPLATE_DETAIL_ID)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    title_file = Path(args.title_file) if args.title_file else title_file_for_batch(args.batch)
    batch = batch_from_title_file(title_file)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = Path("runs") / f"{batch}_{run_id}.json"

    items = read_items(title_file)
    if args.limit:
        items = items[: args.limit]

    template_detail_id = args.template_detail_id or find_template_detail_id(args.template_title, args.shop_id)
    _, template_info = get_tk_info(template_detail_id, args.shop_id)
    previous = {} if args.dry_run else previous_successes(batch)

    results: list[dict[str, Any]] = []
    for item in items:
        seq = item["seq"]
        result: dict[str, Any] = {"seq": seq, "title": item["title"], "status": "started"}
        try:
            urls = image_urls(batch, seq)
            result["image_count"] = len(urls)
            result["ignored_files"] = ["Thumbs.db"]
            result["url_checks"] = [check_url(url) for url in urls]
            if args.dry_run:
                result["status"] = "dry_run_ok"
                results.append(result)
                continue

            existing = previous.get(seq)
            if existing:
                detail_id = int(existing["tiktokDetailId"])
                common_id = int(existing.get("commonCollectBoxDetailId") or 0)
                result["reused_from_log"] = True
                try:
                    get_tk_info(detail_id, args.shop_id)
                except Exception as exc:
                    result["stale_logged_detail"] = {"detailId": detail_id, "error": repr(exc)}
                    existing = None
            else:
                result["reused_from_log"] = False

            if not existing:
                searched = find_existing_by_title(item["title"], args.shop_id)
                if searched:
                    detail_id = int(searched["collectBoxDetailId"])
                    common_id = int(searched.get("commonCollectBoxDetailId") or 0)
                    result["reused_existing"] = True
                else:
                    common_id = create_common_product(
                        item["title"],
                        urls,
                        template_info,
                        f"MSBATCH-{batch}-{seq}",
                    )
                    detail_id = claim_to_tiktok(common_id)
                    result["reused_existing"] = False
                result.setdefault("reused_from_log", False)

            save_from_template(detail_id, args.shop_id, item["title"], urls, template_info)
            verification = verify_product(detail_id, args.shop_id, item["title"], urls, template_info)
            result.update(
                {
                    "status": "success" if all(
                        [
                            verification["title_ok"],
                            verification["images_ok"],
                            verification["cid_ok"],
                            verification["sku_count"] == len(template_info.get("skuMap") or {}),
                        ]
                    ) else "verify_failed",
                    "commonCollectBoxDetailId": common_id,
                    "tiktokDetailId": detail_id,
                    "shopId": args.shop_id,
                    "verification": verification,
                }
            )
        except Exception as exc:
            result.update({"status": "failed", "error": repr(exc)})
        results.append(result)
        write_json(log_path, {"batch": batch, "templateDetailId": template_detail_id, "results": results})
        time.sleep(1.2)

    ok_statuses = {"success", "dry_run_ok"}
    summary = {
        "batch": batch,
        "titleFile": str(title_file),
        "templateTitle": args.template_title,
        "templateDetailId": template_detail_id,
        "shopId": args.shop_id,
        "total": len(results),
        "success": sum(1 for r in results if r["status"] == "success"),
        "failed": [r for r in results if r["status"] not in ok_statuses],
        "logPath": str(log_path.resolve()),
    }
    write_json(log_path, {"summary": summary, "results": results})
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not summary["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
