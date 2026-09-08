from __future__ import annotations

from typing import Any, Callable

from batch_tiktok_collect import natural_key

from .config import SITE

PostFunc = Callable[[str, dict[str, Any], tuple[str, str] | None], dict[str, Any]]


def expect_miaoshou_success(response: dict[str, Any], label: str) -> dict[str, Any]:
    if response.get("result") != "success":
        raise RuntimeError(f"{label}失败: {response}")
    return response.get("data") or {}


def shop_display_name(shop: dict[str, Any]) -> str:
    name = shop.get("platformShopName") or shop.get("shopNick") or shop.get("shopName") or shop.get("name") or shop.get("shopId")
    site = shop.get("siteName") or shop.get("site") or SITE
    return f"{name} ({site})"


def truthy_flag(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "y", "required", "mandatory"}


def pick_warehouse(warehouses: list[dict[str, Any]]) -> dict[str, Any] | None:
    usable = [warehouse for warehouse in warehouses if warehouse.get("warehouseId")]
    if not usable:
        return None
    for warehouse in usable:
        if truthy_flag(warehouse.get("isDefault")):
            return warehouse
    return usable[0]


def get_tiktok_shops(credentials: tuple[str, str], post: PostFunc) -> list[dict[str, Any]]:
    response = post(
        "get_shop_list",
        {"platform": "tiktok", "site": SITE, "pageNo": 1, "pageSize": 100},
        credentials,
    )
    data = expect_miaoshou_success(response, "获取店铺列表")
    shops = data.get("shopList") or []
    return [shop for shop in shops if str(shop.get("shopId") or "").isdigit()]


def get_default_warehouse_ids(shop_ids: list[int], credentials: tuple[str, str], post: PostFunc) -> dict[str, str]:
    response = post("get_shop_warehouse_list", {"shopIds": shop_ids}, credentials)
    data = expect_miaoshou_success(response, "获取店铺仓库列表")
    result: dict[str, str] = {}
    missing: list[str] = []
    missing_keys: set[str] = set()
    wanted = {str(value) for value in shop_ids}
    for shop in data.get("shopWarehouseList") or []:
        shop_id = str(shop.get("shopId") or "")
        if shop_id not in wanted:
            continue
        warehouse = pick_warehouse(shop.get("warehouseList") or [])
        if warehouse:
            result[shop_id] = str(warehouse["warehouseId"])
        else:
            missing.append(str(shop.get("shopName") or shop_id))
            missing_keys.add(shop_id)
    for shop_id in shop_ids:
        if str(shop_id) not in result and str(shop_id) not in missing_keys:
            missing.append(str(shop_id))
    if missing:
        raise RuntimeError(f"这些店铺没有可用仓库，请先在妙手店铺里设置默认仓库：{', '.join(missing)}")
    return result


def flatten_category_tree(cate_tree: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    def walk(node: dict[str, Any], parents: list[str]) -> None:
        name = str(node.get("nameChinese") or node.get("name") or node.get("cid") or "").strip()
        path = parents + ([name] if name else [])
        children = node.get("children") or {}
        is_leaf = str(node.get("isLastLevel") or "").lower() in {"1", "true", "yes"} or not children
        if is_leaf and node.get("cid") and not node.get("disabled"):
            rows.append(
                {
                    "cid": str(node["cid"]),
                    "name": str(node.get("name") or ""),
                    "nameChinese": str(node.get("nameChinese") or ""),
                    "path": " / ".join(path),
                }
            )
        for child in (children.values() if isinstance(children, dict) else children):
            if isinstance(child, dict):
                walk(child, path)

    for root in (cate_tree.values() if isinstance(cate_tree, dict) else cate_tree):
        if isinstance(root, dict):
            walk(root, [])
    return sorted(rows, key=lambda row: natural_key(row["path"]))


def load_categories(
    credentials: tuple[str, str],
    post: PostFunc,
    cache: dict[str, list[dict[str, str]]],
) -> list[dict[str, str]]:
    cache_key = SITE
    cached = cache.get(cache_key)
    if cached:
        return cached
    response = post("get_tk_category_tree", {"site": SITE}, credentials)
    data = expect_miaoshou_success(response, "获取 TikTok 类目")
    rows = flatten_category_tree((data.get("cateTree") or {}))
    cache[cache_key] = rows
    return rows


def get_category_metadata(
    cid: int,
    credentials: tuple[str, str],
    post: PostFunc,
    shop_ids: list[int] | None = None,
) -> dict[str, Any]:
    body: dict[str, object] = {"cid": cid, "site": SITE}
    if shop_ids:
        body["shopIds"] = shop_ids
    response = post("get_tk_category_metadata", body, credentials)
    data = expect_miaoshou_success(response, "获取类目参数")
    return data.get("categoryMetadata") or {}


def metadata_attrs(metadata: dict[str, Any], key: str) -> list[dict[str, Any]]:
    return [attr for attr in metadata.get(key) or [] if isinstance(attr, dict)]


def attr_label(attr: dict[str, Any]) -> str:
    alias = str(attr.get("attributeNameAlias") or "").strip()
    name = str(attr.get("name") or attr.get("attributeName") or attr.get("attrId") or "").strip()
    return f"{alias} / {name}" if alias and name and alias != name else (alias or name)


def is_required_attr(attr: dict[str, Any]) -> bool:
    required_regions = {str(region or "").strip().upper() for region in (attr.get("requiredRegions") or [])}
    return truthy_flag(attr.get("isMandatory")) or truthy_flag(attr.get("isRequired")) or SITE.upper() in required_regions


def category_required_notes(metadata: dict[str, Any]) -> list[str]:
    config = metadata.get("categoryConfig") or {}
    notes: list[str] = []
    if truthy_flag(config.get("packageDimensionIsRequired")):
        notes.append("平台要求填写包装尺寸和重量，已放在后面的「物流/包装信息」分段。")
    if truthy_flag(config.get("sizeChartIsRequired")) or truthy_flag(config.get("isSizeChartMandatory")):
        notes.append("这个类目要求尺码表，后续需要补充尺码表入口。")
    if truthy_flag(config.get("responsiblePersonIsRequired")):
        notes.append("这个类目要求责任人信息，后续需要补充责任人选择入口。")
    if truthy_flag(config.get("manufacturerIsRequired")):
        notes.append("这个类目要求制造商信息，后续需要补充制造商入口。")
    required_certs = [
        str(cert.get("name") or cert.get("id") or "").strip()
        for cert in (config.get("productCertifications") or [])
        if isinstance(cert, dict) and (truthy_flag(cert.get("isRequired")) or truthy_flag(cert.get("isMandatory")))
    ]
    if required_certs:
        notes.append("这个类目要求产品认证：" + "、".join(required_certs[:5]))
    return notes
