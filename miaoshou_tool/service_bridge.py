from __future__ import annotations

from pathlib import Path
from typing import Any


def load_local_env(namespace: dict[str, Any]) -> None:
    namespace["account_module"].load_local_env()


def oss_credentials(namespace: dict[str, Any]) -> tuple[str, str, str]:
    return namespace["oss_upload"].oss_credentials()


def put_oss_object(file_path: Path, object_key: str, namespace: dict[str, Any]) -> None:
    namespace["oss_upload"].put_oss_object(file_path, object_key)


def upload_images_to_oss(image_root: Path, image_prefix: str, seqs: list[int], namespace: dict[str, Any]) -> int:
    return namespace["oss_upload"].upload_images_to_oss(
        image_root,
        image_prefix,
        seqs,
        put_object=namespace["put_oss_object"],
    )


def upload_source_files_to_oss(image_prefix: str, source_files: list[tuple[Path, str]], namespace: dict[str, Any]) -> int:
    return namespace["oss_upload"].upload_source_files_to_oss(
        image_prefix,
        source_files,
        put_object=namespace["put_oss_object"],
    )


def get_tiktok_shops(credentials: tuple[str, str], namespace: dict[str, Any]) -> list[dict]:
    return namespace["miaoshou_api"].get_tiktok_shops(credentials, namespace["miaoshou_post"])


def get_default_warehouse_ids(shop_ids: list[int], credentials: tuple[str, str], namespace: dict[str, Any]) -> dict[str, str]:
    return namespace["miaoshou_api"].get_default_warehouse_ids(shop_ids, credentials, namespace["miaoshou_post"])


def load_categories(credentials: tuple[str, str], namespace: dict[str, Any]) -> list[dict]:
    with namespace["CATEGORY_CACHE_LOCK"]:
        return namespace["miaoshou_api"].load_categories(credentials, namespace["miaoshou_post"], namespace["CATEGORY_CACHE"])


def get_category_metadata(
    cid: int,
    credentials: tuple[str, str],
    shop_ids: list[int] | None,
    namespace: dict[str, Any],
) -> dict:
    return namespace["miaoshou_api"].get_category_metadata(cid, credentials, namespace["miaoshou_post"], shop_ids)


def upload_single_images(files: list[Path], object_prefix: str, namespace: dict[str, Any]) -> list[str]:
    return namespace["oss_upload"].upload_single_images(files, object_prefix, put_object=namespace["put_oss_object"])


def upload_single_video(file_path: Path | None, object_prefix: str, namespace: dict[str, Any]) -> str:
    return namespace["oss_upload"].upload_single_video(file_path, object_prefix, put_object=namespace["put_oss_object"])


def load_ai_settings(namespace: dict[str, Any]) -> dict:
    return namespace["ai_module"].load_ai_settings(namespace["load_local_env"])


def save_ai_settings(settings: dict, namespace: dict[str, Any]) -> None:
    namespace["ai_module"].save_ai_settings(settings, namespace["load_ai_settings"])


def call_openai_compatible_chat(settings: dict, content: list[dict], timeout: int, namespace: dict[str, Any]) -> str:
    return namespace["ai_module"].call_openai_compatible_chat(settings, content, timeout, namespace["urllib"].request.urlopen)


def call_deepseek_ai(title: str, notes: str, image_files: list[Path], metadata: dict, namespace: dict[str, Any]) -> dict:
    return namespace["ai_module"].call_ai(
        title,
        notes,
        image_files,
        metadata,
        namespace["load_ai_settings"](),
        namespace["call_openai_compatible_chat"],
    )


def test_ai_settings(settings: dict, namespace: dict[str, Any]) -> None:
    namespace["ai_module"].test_ai_settings(settings, namespace["call_openai_compatible_chat"])


def ai_settings_from_form(form: Any, namespace: dict[str, Any]) -> dict:
    return namespace["ai_module"].ai_settings_from_form(form, namespace["field_text"])


def settings_for_ai_test(posted: dict, namespace: dict[str, Any]) -> dict:
    return namespace["ai_module"].settings_for_ai_test(posted, namespace["load_ai_settings"]())


def ai_configured(namespace: dict[str, Any]) -> bool:
    return namespace["ai_module"].ai_configured(namespace["load_ai_settings"]())


def merge_ai_attributes(product_attrs: list[dict], suggestion_attrs: list[dict], metadata: dict, namespace: dict[str, Any]) -> list[dict]:
    return namespace["ai_module"].merge_ai_attributes(product_attrs, suggestion_attrs, metadata)


def build_common_single_product(
    item_num: str,
    credentials: tuple[str, str],
    title: str,
    notes: str,
    image_urls: list[str],
    skus: list[dict],
    spec_name: str,
    weight: float,
    package_length: float,
    package_width: float,
    package_height: float,
    video_url: str,
    namespace: dict[str, Any],
) -> int:
    return namespace["publishing_module"].build_common_single_product(
        item_num,
        credentials,
        title,
        notes,
        image_urls,
        skus,
        spec_name,
        weight,
        package_length,
        package_width,
        package_height,
        namespace["miaoshou_post"],
        video_url,
    )


def build_product_attributes(form: Any, metadata: dict, namespace: dict[str, Any]) -> list[dict]:
    return namespace["publishing_module"].build_product_attributes(form, metadata, namespace["field_text"])


def get_site_info(detail_id: int, credentials: tuple[str, str], namespace: dict[str, Any]) -> tuple[str, dict]:
    return namespace["publishing_module"].get_site_info(detail_id, credentials, namespace["miaoshou_post"])


def save_site_product(
    detail_id: int,
    credentials: tuple[str, str],
    site_info: dict,
    oss_md5: str,
    title: str,
    notes: str,
    image_urls: list[str],
    cid: int,
    product_attrs: list[dict],
    sale_attr_id: str,
    spec_name: str,
    skus: list[dict],
    shop_ids: list[int],
    weight: float,
    package_length: float,
    package_width: float,
    package_height: float,
    warehouse_ids: dict[str, str] | None,
    video_url: str,
    namespace: dict[str, Any],
) -> None:
    namespace["publishing_module"].save_site_product(
        detail_id,
        credentials,
        site_info,
        oss_md5,
        title,
        notes,
        image_urls,
        cid,
        product_attrs,
        sale_attr_id,
        spec_name,
        skus,
        shop_ids,
        weight,
        package_length,
        package_width,
        package_height,
        namespace["miaoshou_post"],
        warehouse_ids,
        video_url,
    )


def claim_tiktok_to_shops(detail_id: int, shop_ids: list[int], credentials: tuple[str, str], namespace: dict[str, Any]) -> None:
    namespace["publishing_module"].claim_tiktok_to_shops(detail_id, shop_ids, credentials, namespace["miaoshou_post"])


def claim_common_to_tiktok_single(common_id: int, credentials: tuple[str, str], namespace: dict[str, Any]) -> int:
    return namespace["publishing_module"].claim_common_to_tiktok_single(common_id, credentials, namespace["miaoshou_post"])


def delete_common_collect_products(detail_ids: list[int], credentials: tuple[str, str], namespace: dict[str, Any]) -> None:
    namespace["publishing_module"].delete_common_collect_products(detail_ids, credentials, namespace["miaoshou_post"])


def delete_tiktok_collect_products(detail_ids: list[int], credentials: tuple[str, str], namespace: dict[str, Any]) -> None:
    namespace["publishing_module"].delete_tiktok_collect_products(detail_ids, credentials, namespace["miaoshou_post"])


def cleanup_created_single_product(
    common_id: int | None,
    detail_id: int | None,
    credentials: tuple[str, str],
    namespace: dict[str, Any],
) -> list[str]:
    return namespace["single_product_module"].cleanup_created_single_product(
        common_id,
        detail_id,
        credentials,
        namespace["delete_tiktok_collect_products"],
        namespace["delete_common_collect_products"],
    )


def parse_sku_rows(form: Any, sku_image_paths: dict[str, Path] | None, namespace: dict[str, Any]) -> tuple[str, str, list[dict]]:
    return namespace["publishing_module"].parse_sku_rows(
        form,
        namespace["field_text"],
        namespace["field_list"],
        sku_image_paths,
    )


def discover_templates(credentials: tuple[str, str], requested_shop_id: int | None, namespace: dict[str, Any]) -> tuple[int, dict[str, int], str]:
    return namespace["account_module"].discover_templates(credentials, namespace["miaoshou_post"], requested_shop_id)
