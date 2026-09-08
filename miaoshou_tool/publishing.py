from __future__ import annotations

import cgi
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .ai import require_english
from .config import SITE
from .miaoshou_api import PostFunc, attr_label, expect_miaoshou_success, is_required_attr, metadata_attrs

FieldTextFunc = Callable[[cgi.FieldStorage, str, str], str]
FieldListFunc = Callable[[cgi.FieldStorage, str], list[Any]]


def build_common_single_product(
    item_num: str,
    credentials: tuple[str, str],
    title: str,
    notes: str,
    image_urls: list[str],
    skus: list[dict[str, Any]],
    spec_name: str,
    weight: float,
    package_length: float,
    package_width: float,
    package_height: float,
    post: PostFunc,
    video_url: str = "",
) -> int:
    first_sku = skus[0]
    color_map = {
        sku["value_id"]: {"name": sku["value"], "imgUrl": sku["image_url"], "imgUrls": [sku["image_url"]]}
        for sku in skus
    }
    sku_map = {
        f";{sku['value_id']};": {
            "itemNum": sku["item_num"],
            "price": sku["price"],
            "stock": sku["stock"],
            "weight": weight,
            "packageLength": package_length,
            "packageWidth": package_width,
            "packageHeight": package_height,
            "oriPrice": sku["price"],
            "oriStock": sku["stock"],
        }
        for sku in skus
    }
    body = {
        "title": title,
        "itemNum": item_num,
        "notesText": re.sub(r"<[^>]+>", " ", notes)[:65536],
        "notes": notes,
        "sourceAttrs": [],
        "price": first_sku["price"],
        "stock": sum(sku["stock"] for sku in skus),
        "imgUrls": image_urls,
        "weight": max(weight, 0.01),
        "packageLength": package_length,
        "packageWidth": package_width,
        "packageHeight": package_height,
        "colorPropName": spec_name,
        "colorMap": color_map,
        "skuMap": sku_map,
    }
    if video_url:
        body["mainImgVideoUrl"] = video_url
    response = post("create_common_collect_product", body, credentials)
    data = expect_miaoshou_success(response, "创建公共采集箱产品")
    return int(data["commonCollectBoxDetailId"])


def build_product_attributes(form: cgi.FieldStorage, metadata: dict[str, Any], field_text: FieldTextFunc) -> list[dict[str, Any]]:
    attrs = metadata_attrs(metadata, "categoryProductAttrList")
    result: list[dict[str, Any]] = []
    for attr in attrs:
        attr_id = str(attr.get("attrId") or "")
        if not attr_id:
            continue
        selected = field_text(form, f"attr_{attr_id}", "")
        custom = field_text(form, f"attr_custom_{attr_id}", "")
        if custom:
            require_english(custom, attr_label(attr))
            values = [{"valueName": custom, "valueId": ""}]
        elif selected:
            value_name = selected
            value_id = ""
            for item in attr.get("values") or []:
                if str(item.get("id")) == selected:
                    value_id = str(item.get("id") or "")
                    value_name = str(item.get("name") or item.get("valueNameAlias") or selected)
                    break
            values = [{"valueName": value_name, "valueId": value_id}]
        else:
            if is_required_attr(attr):
                raise ValueError(f"请填写必填属性：{attr_label(attr)}")
            continue
        result.append(
            {
                "attributeId": attr_id,
                "attributeName": str(attr.get("name") or attr.get("attributeName") or ""),
                "attributeNameAlias": str(attr.get("attributeNameAlias") or ""),
                "attributeValues": values,
            }
        )
    return result


def custom_value_id(index: int) -> str:
    return str(900000000000000000 + index)


def get_site_info(detail_id: int, credentials: tuple[str, str], post: PostFunc) -> tuple[str, dict[str, Any]]:
    response = post("get_tk_site_collect_item_info", {"detailId": detail_id, "site": SITE}, credentials)
    data = expect_miaoshou_success(response, "获取 TikTok 站点详情")
    return str(data.get("ossMd5") or ""), data.get("siteCollectItemInfo") or {}


def save_site_product(
    detail_id: int,
    credentials: tuple[str, str],
    site_info: dict[str, Any],
    oss_md5: str,
    title: str,
    notes: str,
    image_urls: list[str],
    cid: int,
    product_attrs: list[dict[str, Any]],
    sale_attr_id: str,
    spec_name: str,
    skus: list[dict[str, Any]],
    shop_ids: list[int],
    weight: float,
    package_length: float,
    package_width: float,
    package_height: float,
    post: PostFunc,
    warehouse_ids: dict[str, str] | None = None,
    video_url: str = "",
) -> None:
    if not oss_md5:
        raise RuntimeError("TikTok 站点详情缺少 ossMd5")
    warehouse_ids = warehouse_ids or {}
    sku_property_list = [
        {
            "attrName": spec_name,
            "attrId": sale_attr_id,
            "attrValueList": [
                {"attrValueId": sku["value_id"], "attrValue": sku["value"], "imgUrl": sku["image_url"]}
                for sku in skus
            ],
        }
    ]
    sku_map = {
        f";{sku['value_id']};": {
            "price": sku["price"],
            "priceIncludeVat": sku["price"],
            "originPrice": sku["price"],
            "stock": sku["stock"],
            "itemNum": sku["item_num"],
            "isDelete": "0",
            "weight": weight,
            "preSale": {"type": "NONE"},
            "shopIdToWarehouseIdAndStockMap": {
                shop_id: {warehouse_id: str(sku["stock"])}
                for shop_id, warehouse_id in warehouse_ids.items()
            },
        }
        for sku in skus
    }
    info = dict(site_info)
    info.pop("sizeChart", None)
    info.pop("sizeChartType", None)
    info.pop("sizeChartTemplateId", None)
    info.pop("collectBoxDetailShopList", None)
    info.pop("shopId", None)
    info.update(
        {
            "site": SITE,
            "detailId": detail_id,
            "title": title,
            "notes": notes,
            "imgUrls": image_urls,
            "weight": weight,
            "packageLength": package_length,
            "packageWidth": package_width,
            "packageHeight": package_height,
            "isCodOpen": "0",
            "cid": str(cid),
            "editModel": "site",
            "deliveryOptionSetType": "default",
            "skuMap": sku_map,
            "skuPropertyList": sku_property_list,
            "productAttributes": product_attrs,
            "collectBoxDetailShopList": [{"shopId": shop_id, "site": SITE} for shop_id in shop_ids],
        }
    )
    if video_url:
        info["mainImgVideoUrl"] = video_url
    response = post(
        "save_tk_site_collect_item_info",
        {"ossMd5": oss_md5, "site": SITE, "detailId": detail_id, "siteCollectItemInfo": info},
        credentials,
    )
    expect_miaoshou_success(response, "保存 TikTok 站点详情")


def claim_tiktok_to_shops(detail_id: int, shop_ids: list[int], credentials: tuple[str, str], post: PostFunc) -> None:
    response = post("claim_tk_collect_to_shop", {"shopIds": shop_ids, "detailIds": [detail_id]}, credentials)
    expect_miaoshou_success(response, "认领预发布店铺")


def claim_common_to_tiktok_single(common_id: int, credentials: tuple[str, str], post: PostFunc) -> int:
    response = post(
        "claim_common_products_to_platform",
        {"detailSerialNumberPlatformList": [{"detailId": common_id, "platform": "tiktok", "serialNumber": 1}]},
        credentials,
    )
    data = expect_miaoshou_success(response, "认领到 TikTok")
    mapping = (data.get("platformCollectBoxDetailIdMap") or {}).get("tiktok") or {}
    detail_id = mapping.get(str(common_id)) or mapping.get(common_id)
    if not detail_id:
        raise RuntimeError(f"认领成功但没有返回 TikTok detailId: {response}")
    return int(detail_id)


def delete_common_collect_products(detail_ids: list[int], credentials: tuple[str, str], post: PostFunc) -> None:
    if not detail_ids:
        return
    response = post("delete_common_collect_products", {"commonCollectBoxDetailIds": detail_ids}, credentials)
    expect_miaoshou_success(response, "删除公共采集箱草稿")


def delete_tiktok_collect_products(detail_ids: list[int], credentials: tuple[str, str], post: PostFunc) -> None:
    if not detail_ids:
        return
    response = post("delete_tk_collect_products", {"detailIds": detail_ids}, credentials)
    expect_miaoshou_success(response, "删除 TikTok 采集箱草稿")


def resolve_skus(sku_rows: list[dict[str, Any]], image_urls: list[str], weight: float) -> list[dict[str, Any]]:
    skus: list[dict[str, Any]] = []
    for row in sku_rows:
        image_url = row.get("image_url") or image_urls[0]
        skus.append(
            {
                "value": row["value"],
                "value_id": custom_value_id(len(skus) + 1),
                "price": row["price"],
                "stock": row["stock"],
                "image_url": image_url,
                "item_num": f"SKU-{datetime.now().strftime('%Y%m%d%H%M%S')}-{len(skus) + 1}",
                "weight": weight,
            }
        )
    return skus


def parse_sku_rows(
    form: cgi.FieldStorage,
    field_text: FieldTextFunc,
    field_list: FieldListFunc,
    sku_image_paths: dict[str, Path] | None = None,
) -> tuple[str, str, list[dict[str, Any]]]:
    sku_image_paths = sku_image_paths or {}
    spec_name = field_text(form, "spec_name", "")
    sale_attr_id = field_text(form, "sale_attr_id", "")
    if not spec_name:
        raise ValueError("请填写规格名称")
    require_english(spec_name, "规格名称")
    row_ids = [str(item.value or "").strip() for item in field_list(form, "sku_row_id")]
    values = [str(item.value or "").strip() for item in field_list(form, "sku_value")]
    prices = [str(item.value or "").strip() for item in field_list(form, "sku_price")]
    stocks = [str(item.value or "").strip() for item in field_list(form, "sku_stock")]
    rows: list[dict[str, Any]] = []
    for index, value in enumerate(values):
        if not value:
            continue
        row_id = row_ids[index] if index < len(row_ids) and row_ids[index] else str(index)
        require_english(value, "规格值")
        try:
            price = float(prices[index]) if index < len(prices) and prices[index] else 0
            stock = int(stocks[index]) if index < len(stocks) and stocks[index] else 0
        except ValueError:
            raise ValueError(f"规格「{value}」价格或库存格式不正确")
        if price <= 0:
            raise ValueError(f"规格「{value}」价格必须大于 0")
        if stock < 0:
            raise ValueError(f"规格「{value}」库存不能小于 0")
        rows.append({"value": value, "price": price, "stock": stock, "image_path": sku_image_paths.get(row_id)})
    if not rows:
        raise ValueError("至少填写一个规格值")
    return sale_attr_id, spec_name, rows
