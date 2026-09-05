from pathlib import Path
import tempfile

import batch_tiktok_collect
import web_app


def test_zip_subset_is_used_as_source_of_truth() -> None:
    root = Path(tempfile.mkdtemp())
    for seq in range(1, 6):
        folder = root / "541313" / str(seq)
        folder.mkdir(parents=True)
        (folder / "1.jpg").write_text("x", encoding="utf-8")

    base, prefix = web_app.resolve_image_layout(root, "任意批次", list(range(1, 31)), "")
    process_seqs = [seq for seq in range(1, 31) if seq in web_app.image_seq_dirs(base)]
    items = [{"seq": seq, "title": f"title {seq}"} for seq in range(1, 31)]
    failures = web_app.build_preflight_failures(items, base, web_app.image_seq_dirs(base), include_image_only=True)

    assert base == root / "541313"
    assert prefix == "541313"
    assert process_seqs == [1, 2, 3, 4, 5]
    assert len(failures) == 25
    assert failures[0]["seq"] == 6
    assert failures[0]["error"] == "缺少图片文件夹"


def test_saved_account_form_can_edit_key_without_revealing_secret() -> None:
    app_key = "ak_b123456789f69c"
    html = web_app.render_account_row(
        "miaoshou_test",
        {
            "name": "测试账号",
            "shop_id": 123,
            "app_key": app_key,
            "app_secret": "hidden_secret",
            "templates": {"大地毯": 1, "非定制毛毯": 2, "定制毛毯": 3},
        },
    )

    assert 'name="app_key"' in html
    assert app_key not in html
    assert 'type="password"' in html
    assert 'name="app_secret"' in html
    assert "hidden_secret" not in html
    assert "留空不改" in html
    assert "APP ID / App Key" in html
    assert "Secret 已配置" in html
    assert web_app.masked_app_key("ak_b123456789f69c") == "ak_b...f69c"


def test_discover_templates_uses_template_keywords_and_shop_id() -> None:
    old_post = web_app.miaoshou_post

    def fake_post(endpoint: str, body: dict, credentials: tuple[str, str]) -> dict:
        assert endpoint == "search_tk_collect_products"
        assert credentials == ("key", "secret")
        detail_list = []
        for index, name in enumerate(web_app.TEMPLATES, start=1):
            detail_list.append(
                {
                    "collectBoxDetailId": 1000 + index,
                    "collectGroupName": f"任意账号-{name}-参数",
                    "collectBoxDetailShopList": [{"shopId": 555, "shopName": "Print & Purl"}],
                }
            )
        return {"result": "success", "data": {"detailList": detail_list}}

    try:
        web_app.miaoshou_post = fake_post
        shop_id, templates, shop_name = web_app.discover_templates(("key", "secret"))
    finally:
        web_app.miaoshou_post = old_post

    assert shop_id == 555
    assert shop_name == "Print & Purl"
    assert templates == {"大地毯": 1001, "非定制毛毯": 1002, "定制毛毯": 1003}
    assert web_app.matched_template_name(web_app.normalized_text({"group": "非定制毛毯参数"})) == "非定制毛毯"


def test_confirm_page_does_not_render_secrets() -> None:
    token = "pending-token"
    try:
        with web_app.PENDING_ACCOUNTS_LOCK:
            web_app.PENDING_ACCOUNTS[token] = {
                "username": "duanhaha",
                "name": "测试账号",
                "shop_id": 555,
                "shop_name": "Print & Purl",
                "app_key": "ak_b123456789f69c",
                "app_secret": "hidden_secret",
                "templates": {"大地毯": 1001, "非定制毛毯": 1002, "定制毛毯": 1003},
            }
        html = web_app.render_account_confirm("duanhaha", token).decode("utf-8")
    finally:
        with web_app.PENDING_ACCOUNTS_LOCK:
            web_app.PENDING_ACCOUNTS.pop(token, None)

    assert "Print &amp; Purl" in html
    assert "555" in html
    assert "ak_b123456789f69c" not in html
    assert "hidden_secret" not in html
    assert "ak_b...f69c" in html


def test_status_labels_and_errors_are_user_friendly() -> None:
    assert web_app.status_label("done_with_errors") == "部分失败"
    assert "部分失败" in web_app.status_badge("done_with_errors")
    assert "图片链接无法读取" in web_app.readable_error_text("HTTPError 404: Not Found")
    assert "ZIP" in web_app.readable_error_text("缺少图片文件夹")
    assert "公共采集箱" in web_app.readable_error_text("KeyError('create_common_collect_product')")


def test_home_uses_saved_miaoshou_accounts_without_web_user() -> None:
    original_load = web_app.load_accounts_config
    original_jobs = web_app.JOBS.copy()
    try:
        web_app.load_accounts_config = lambda: {  # type: ignore[assignment]
            "accounts": {
                "acc": {
                    "name": "测试妙手账号",
                    "app_key": "key",
                    "app_secret": "secret",
                    "templates": {"大地毯": 1, "非定制毛毯": 2, "定制毛毯": 3},
                }
            }
        }
        with web_app.JOBS_LOCK:
            web_app.JOBS.clear()
        html = web_app.render_home("anyone").decode("utf-8")

        assert "新建批次" in html
        assert "测试妙手账号" in html
        assert "登录" not in html
        assert "用户名" not in html
    finally:
        web_app.load_accounts_config = original_load  # type: ignore[assignment]
        with web_app.JOBS_LOCK:
            web_app.JOBS.clear()
            web_app.JOBS.update(original_jobs)


def test_batch_endpoints_are_declared() -> None:
    required = {
        "create_common_collect_product",
        "claim_common_products_to_platform",
        "delete_common_collect_products",
        "get_shop_list",
        "get_shop_warehouse_list",
        "get_tk_category_tree",
        "get_tk_category_metadata",
        "search_tk_collect_products",
        "get_tk_site_collect_item_info",
        "save_tk_site_collect_item_info",
        "get_tk_shop_collect_item_info",
        "save_tk_shop_collect_item_info",
        "claim_tk_collect_to_shop",
        "delete_tk_collect_products",
    }

    assert required <= set(batch_tiktok_collect.ENDPOINTS)


def test_flatten_category_tree_keeps_leaf_paths_only() -> None:
    rows = web_app.flatten_category_tree(
        {
            "1": {
                "cid": 1,
                "nameChinese": "箱包",
                "children": {
                    "2": {
                        "cid": 2,
                        "nameChinese": "旅行箱",
                        "children": {
                            "3": {"cid": 3, "nameChinese": "折叠旅行包", "isLastLevel": "1"}
                        },
                    }
                },
            }
        }
    )

    assert rows == [{"cid": "3", "name": "", "nameChinese": "折叠旅行包", "path": "箱包 / 旅行箱 / 折叠旅行包"}]


def test_category_picker_renders_cascading_control_without_big_select() -> None:
    html = web_app.render_category_picker(
        [{"cid": "3", "path": "箱包 / 旅行箱 / 折叠旅行包"}],
        "3",
    )

    assert 'id="categoryColumns"' in html
    assert 'id="cid" name="cid" type="hidden" value="3"' in html
    assert "箱包 / 旅行箱 / 折叠旅行包" in html
    assert "先选择末级类目" not in html


class FakeField:
    def __init__(self, value: str) -> None:
        self.value = value


class FakeForm(dict):
    pass


def test_parse_sku_rows_requires_english_and_keeps_multiple_values() -> None:
    form = FakeForm(
        {
            "spec_name": FakeField("Bedding Size"),
            "sale_attr_id": FakeField("123"),
            "sku_row_id": [FakeField("0"), FakeField("1")],
            "sku_value": [FakeField("30x40inch"), FakeField("50x40inch")],
            "sku_price": [FakeField("16.99"), FakeField("29.88")],
            "sku_stock": [FakeField("10"), FakeField("0")],
        }
    )

    sale_attr_id, spec_name, rows = web_app.parse_sku_rows(form, {"1": Path("sku.jpg")})  # type: ignore[arg-type]

    assert sale_attr_id == "123"
    assert spec_name == "Bedding Size"
    assert rows == [
        {"value": "30x40inch", "price": 16.99, "stock": 10, "image_path": None},
        {"value": "50x40inch", "price": 29.88, "stock": 0, "image_path": Path("sku.jpg")},
    ]


def test_single_form_uses_local_sku_image_upload() -> None:
    originals = (
        web_app.load_accounts_config,
        web_app.user_record,
        web_app.get_tiktok_shops,
        web_app.load_categories,
        web_app.get_category_metadata,
    )
    try:
        web_app.load_accounts_config = lambda: {  # type: ignore[assignment]
            "accounts": {"acc": {"name": "测试账号", "app_key": "key", "app_secret": "secret"}}
        }
        web_app.user_record = lambda username: {"username": username, "accounts": ["acc"]}  # type: ignore[assignment]
        web_app.get_tiktok_shops = lambda credentials: [{"shopId": 1, "shopName": "Test Shop"}]  # type: ignore[assignment]
        web_app.load_categories = lambda credentials: [{"cid": "3", "path": "家纺 / 毛毯"}]  # type: ignore[assignment]
        web_app.get_category_metadata = lambda cid, credentials, shop_ids: {  # type: ignore[assignment]
            "categorySaleAttrList": [{"attrId": "size", "attributeNameAlias": "Size"}],
            "categoryProductAttrList": [],
        }

        html = web_app.render_single("duanhaha", {"account_id": ["acc"], "cid": ["3"]}).decode("utf-8")

        assert 'name="sku_image_file_0"' in html
        assert 'type="file" accept="image/*"' in html
        assert "规格图 URL" not in html
        assert "妙手销售属性" not in html
        assert 'type="hidden" name="sale_attr_id" value="size"' in html
        assert 'list="spec_name_options"' in html
    finally:
        (
            web_app.load_accounts_config,
            web_app.user_record,
            web_app.get_tiktok_shops,
            web_app.load_categories,
            web_app.get_category_metadata,
        ) = originals


def test_common_single_product_uses_visible_spec_as_color_dimension() -> None:
    old_post = web_app.miaoshou_post
    captured = {}

    def fake_post(endpoint: str, body: dict, credentials: tuple[str, str]) -> dict:
        assert endpoint == "create_common_collect_product"
        captured["body"] = body
        return {"result": "success", "data": {"commonCollectBoxDetailId": 12345}}

    try:
        web_app.miaoshou_post = fake_post
        detail_id = web_app.build_common_single_product(
            "ITEM-1",
            ("key", "secret"),
            "Test Product Title",
            "<p>Test description</p>",
            ["https://example.com/1.jpg"],
            [
                {
                    "value": "30x40inch",
                    "value_id": "9001",
                    "item_num": "SKU-1",
                    "price": 16.99,
                    "stock": 10,
                    "image_url": "https://example.com/sku-1.jpg",
                }
            ],
            "Bedding Size",
            0.5,
            30,
            20,
            5,
        )
    finally:
        web_app.miaoshou_post = old_post

    assert detail_id == 12345
    body = captured["body"]
    assert body["colorPropName"] == "Bedding Size"
    assert body["colorMap"] == {
        "9001": {
            "name": "30x40inch",
            "imgUrl": "https://example.com/sku-1.jpg",
            "imgUrls": ["https://example.com/sku-1.jpg"],
        }
    }
    assert "sizePropName" not in body
    assert "sizeMap" not in body
    assert list(body["skuMap"].keys()) == [";9001;"]


def test_save_site_product_drops_inherited_size_chart_when_not_used() -> None:
    old_post = web_app.miaoshou_post
    captured = {}

    def fake_post(endpoint: str, body: dict, credentials: tuple[str, str]) -> dict:
        assert endpoint == "save_tk_site_collect_item_info"
        captured["body"] = body
        return {"result": "success", "data": {}}

    try:
        web_app.miaoshou_post = fake_post
        web_app.save_site_product(
            123,
            ("key", "secret"),
            {
                "sizeChartType": "image",
                "sizeChart": "https://example.com/size.txt",
                "sizeChartTemplateId": "old-template",
            },
            "oss-md5",
            "Test Product Title",
            "<p>Test description</p>",
            ["https://example.com/1.jpg"],
            456,
            [],
            "size",
            "Bedding Size",
            [
                {
                    "value": "30x40inch",
                    "value_id": "9001",
                    "item_num": "SKU-1",
                    "price": 16.99,
                    "stock": 10,
                    "image_url": "https://example.com/sku-1.jpg",
                }
            ],
            [789],
            0.5,
            30,
            20,
            5,
        )
    finally:
        web_app.miaoshou_post = old_post

    info = captured["body"]["siteCollectItemInfo"]
    assert "sizeChart" not in info
    assert "sizeChartType" not in info
    assert "sizeChartTemplateId" not in info


def test_get_default_warehouse_ids_uses_default_then_first_available() -> None:
    old_post = web_app.miaoshou_post
    captured = {}

    def fake_post(endpoint: str, body: dict, credentials: tuple[str, str]) -> dict:
        assert endpoint == "get_shop_warehouse_list"
        captured["body"] = body
        assert credentials == ("key", "secret")
        return {
            "result": "success",
            "data": {
                "shopWarehouseList": [
                    {
                        "shopId": 789,
                        "shopName": "Print & Purl",
                        "warehouseList": [
                            {"warehouseId": "WH-A", "isDefault": "0"},
                            {"warehouseId": "WH-B", "isDefault": "1"},
                        ],
                    },
                    {
                        "shopId": 790,
                        "shopName": "Second Shop",
                        "warehouseList": [{"warehouseId": "WH-C", "isDefault": "0"}],
                    },
                ]
            },
        }

    try:
        web_app.miaoshou_post = fake_post
        result = web_app.get_default_warehouse_ids([789, 790], ("key", "secret"))
    finally:
        web_app.miaoshou_post = old_post

    assert captured["body"] == {"shopIds": [789, 790]}
    assert result == {"789": "WH-B", "790": "WH-C"}


def test_save_site_product_fills_shop_warehouse_stock_map() -> None:
    old_post = web_app.miaoshou_post
    captured = {}

    def fake_post(endpoint: str, body: dict, credentials: tuple[str, str]) -> dict:
        assert endpoint == "save_tk_site_collect_item_info"
        captured["body"] = body
        return {"result": "success", "data": {}}

    try:
        web_app.miaoshou_post = fake_post
        web_app.save_site_product(
            123,
            ("key", "secret"),
            {"collectBoxDetailShopList": [{"shopId": 789, "site": "US"}]},
            "oss-md5",
            "Test Product Title",
            "<p>Test description</p>",
            ["https://example.com/1.jpg"],
            456,
            [],
            "size",
            "Bedding Size",
            [
                {
                    "value": "30x40inch",
                    "value_id": "9001",
                    "item_num": "SKU-1",
                    "price": 16.99,
                    "stock": 10,
                    "image_url": "https://example.com/sku-1.jpg",
                }
            ],
            [789],
            0.5,
            30,
            20,
            5,
            {"789": "WH-1"},
        )
    finally:
        web_app.miaoshou_post = old_post

    info = captured["body"]["siteCollectItemInfo"]
    assert info["collectBoxDetailShopList"] == [{"shopId": 789, "site": web_app.SITE}]
    assert "shopId" not in info
    sku = next(iter(info["skuMap"].values()))
    assert sku["shopIdToWarehouseIdAndStockMap"] == {"789": {"WH-1": "10"}}


def test_single_job_deletes_created_drafts_when_site_save_fails() -> None:
    originals = (
        web_app.upload_single_images,
        web_app.build_common_single_product,
        web_app.claim_common_to_tiktok_single,
        web_app.get_site_info,
        web_app.get_default_warehouse_ids,
        web_app.save_site_product,
        web_app.claim_tiktok_to_shops,
        web_app.miaoshou_post,
        web_app.RUN_ROOT,
    )
    calls: list[tuple[str, dict]] = []
    temp_root = Path(tempfile.mkdtemp())
    job_id = "cleanup-test"
    with web_app.JOBS_LOCK:
        web_app.JOBS[job_id] = {}

    def fake_delete_post(endpoint: str, body: dict, credentials: tuple[str, str]) -> dict:
        calls.append((endpoint, body))
        return {"result": "success", "data": {}}

    try:
        web_app.RUN_ROOT = temp_root
        web_app.upload_single_images = lambda files, prefix: ["https://example.com/1.jpg"]  # type: ignore[assignment]
        web_app.build_common_single_product = lambda *args, **kwargs: 111  # type: ignore[assignment]
        web_app.claim_common_to_tiktok_single = lambda *args, **kwargs: 222  # type: ignore[assignment]
        web_app.get_site_info = lambda *args, **kwargs: ("oss-md5", {})  # type: ignore[assignment]
        web_app.get_default_warehouse_ids = lambda *args, **kwargs: {"789": "WH-1"}  # type: ignore[assignment]
        web_app.save_site_product = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("仓库未选择"))  # type: ignore[assignment]
        web_app.claim_tiktok_to_shops = lambda *args, **kwargs: None  # type: ignore[assignment]
        web_app.miaoshou_post = fake_delete_post

        web_app.run_single_job(
            job_id,
            {
                "credentials": ("key", "secret"),
                "image_files": [Path("1.jpg")],
                "image_prefix": "single/test",
                "sku_rows": [{"value": "30x40inch", "price": 1.0, "stock": 10}],
                "weight": 0.5,
                "item_num": "ITEM-1",
                "title": "Test Product Title For Cleanup",
                "notes": "<p>Test</p>",
                "package_length": 30,
                "package_width": 20,
                "package_height": 5,
                "cid": 123,
                "product_attrs": [],
                "sale_attr_id": "size",
                "spec_name": "Bedding Size",
                "shop_ids": [789],
            },
        )
    finally:
        (
            web_app.upload_single_images,
            web_app.build_common_single_product,
            web_app.claim_common_to_tiktok_single,
            web_app.get_site_info,
            web_app.get_default_warehouse_ids,
            web_app.save_site_product,
            web_app.claim_tiktok_to_shops,
            web_app.miaoshou_post,
            web_app.RUN_ROOT,
        ) = originals
        with web_app.JOBS_LOCK:
            job = web_app.JOBS.pop(job_id, {})

    assert ("delete_tk_collect_products", {"detailIds": [222]}) in calls
    assert ("delete_common_collect_products", {"commonCollectBoxDetailIds": [111]}) in calls
    assert job["status"] == "failed"
    assert "仓库未选择" in job["summary"]["error"]
    assert (temp_root / f"single_{job_id}.json").exists()


def test_single_form_shows_required_category_attrs_before_package_fields() -> None:
    originals = (
        web_app.load_accounts_config,
        web_app.get_tiktok_shops,
        web_app.load_categories,
        web_app.get_category_metadata,
    )
    try:
        web_app.load_accounts_config = lambda: {  # type: ignore[assignment]
            "accounts": {"acc": {"name": "测试账号", "app_key": "key", "app_secret": "secret"}}
        }
        web_app.get_tiktok_shops = lambda credentials: [{"shopId": 1, "shopName": "Test Shop"}]  # type: ignore[assignment]
        web_app.load_categories = lambda credentials: [{"cid": "3", "path": "家纺 / 毛毯"}]  # type: ignore[assignment]
        web_app.get_category_metadata = lambda cid, credentials, shop_ids: {  # type: ignore[assignment]
            "categorySaleAttrList": [{"attrId": "size", "attributeNameAlias": "尺寸", "name": "Size"}],
            "categoryProductAttrList": [
                {
                    "attrId": "material",
                    "attributeNameAlias": "材质",
                    "name": "Material",
                    "isMandatory": "true",
                    "values": [{"id": "polyester", "valueNameAlias": "涤纶", "name": "Polyester"}],
                }
            ],
            "categoryConfig": {"packageDimensionIsRequired": "true"},
        }

        html = web_app.render_single("duanhaha", {"account_id": ["acc"], "cid": ["3"]}).decode("utf-8")

        assert "材质 / Material" in html
        assert "选择类目后会显示必填属性" not in html
        assert html.index("类目必填属性") < html.index("物流/包装信息")
        assert html.index("产品图片") < html.index("类目必填属性")
        assert html.index("物流/包装信息") > html.index("规格与价格")
    finally:
        (
            web_app.load_accounts_config,
            web_app.get_tiktok_shops,
            web_app.load_categories,
            web_app.get_category_metadata,
        ) = originals


if __name__ == "__main__":
    test_zip_subset_is_used_as_source_of_truth()
    test_saved_account_form_can_edit_key_without_revealing_secret()
    test_discover_templates_uses_template_keywords_and_shop_id()
    test_confirm_page_does_not_render_secrets()
    test_status_labels_and_errors_are_user_friendly()
    test_home_uses_saved_miaoshou_accounts_without_web_user()
    test_batch_endpoints_are_declared()
    test_flatten_category_tree_keeps_leaf_paths_only()
    test_category_picker_renders_cascading_control_without_big_select()
    test_parse_sku_rows_requires_english_and_keeps_multiple_values()
    test_single_form_uses_local_sku_image_upload()
    test_common_single_product_uses_visible_spec_as_color_dimension()
    test_save_site_product_drops_inherited_size_chart_when_not_used()
    test_get_default_warehouse_ids_uses_default_then_first_available()
    test_save_site_product_fills_shop_warehouse_stock_map()
    test_single_job_deletes_created_drafts_when_site_save_fails()
    test_single_form_shows_required_category_attrs_before_package_fields()
    print("ok")
