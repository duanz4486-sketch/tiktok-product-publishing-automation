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


def test_batch_endpoints_are_declared() -> None:
    required = {
        "create_common_collect_product",
        "claim_common_products_to_platform",
        "search_tk_collect_products",
        "get_tk_shop_collect_item_info",
        "save_tk_shop_collect_item_info",
    }

    assert required <= set(batch_tiktok_collect.ENDPOINTS)


if __name__ == "__main__":
    test_zip_subset_is_used_as_source_of_truth()
    test_saved_account_form_can_edit_key_without_revealing_secret()
    test_discover_templates_uses_template_keywords_and_shop_id()
    test_confirm_page_does_not_render_secrets()
    test_batch_endpoints_are_declared()
    print("ok")
