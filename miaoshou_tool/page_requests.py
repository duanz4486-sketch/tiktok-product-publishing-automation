from __future__ import annotations

from . import account_pages
from . import ai_pages
from . import batch_pages
from . import job_pages
from . import single_pages
from . import system_pages
from .rendering import alert_html
from .rendering import escape as e


def render_release_check(deps: dict) -> bytes:
    report = deps["run_release_check"](deps["root"], deps["accounts_path"])
    return system_pages.render_release_check(report, len(deps["all_account_ids"]()))


def render_account_row(account_id: str, account: dict, deps: dict) -> str:
    return account_pages.render_account_row(account_id, account, deps["templates"])


def render_accounts(message: str, error: str, deps: dict) -> bytes:
    config = deps["load_accounts_config"]()
    account_ids = deps["all_account_ids"](config)
    return account_pages.render_accounts(config, account_ids, deps["templates"], message, error)


def render_account_confirm(token: str, deps: dict) -> bytes:
    with deps["pending_accounts_lock"]:
        pending = deps["pending_accounts"].get(token)
    return account_pages.render_account_confirm(
        token,
        pending,
        list(deps["templates"]),
        len(deps["all_account_ids"]()),
    )


def render_home(deps: dict) -> bytes:
    config = deps["load_accounts_config"]()
    account_ids = deps["all_account_ids"](config)
    accounts = config.get("accounts", {})
    available_accounts = [(account_id, accounts[account_id]) for account_id in account_ids if account_id in accounts]
    if not available_accounts:
        return system_pages.render_setup_needed()
    with deps["jobs_lock"]:
        job_items = list(deps["jobs"].items())
    return batch_pages.render_home(
        available_accounts,
        account_ids,
        job_items,
        deps["templates"],
        deps["default_template"],
    )


def render_job(job_id: str, username: str | None, deps: dict) -> bytes:
    with deps["jobs_lock"]:
        job = deps["jobs"].get(job_id)
    account_count = len(deps["all_account_ids"]()) if username else 0
    return job_pages.render_job(job_id, job, account_count, bool(username))


def render_single(username: str, query: dict[str, list[str]] | None, error: str, deps: dict) -> bytes:
    query = query or {}
    config = deps["load_accounts_config"]()
    accounts = config.get("accounts", {})
    account_ids = [account_id for account_id in deps["all_account_ids"](config) if account_id in accounts]
    if not account_ids:
        return system_pages.render_setup_needed()
    selected_account_id = query.get("account_id", [account_ids[0]])[0]
    if selected_account_id not in account_ids:
        selected_account_id = account_ids[0]
    account = accounts[selected_account_id]
    account_options = "\n".join(
        f'<option value="{e(account_id)}" {"selected" if account_id == selected_account_id else ""}>{e(accounts[account_id].get("name", account_id))}</option>'
        for account_id in account_ids
    )

    cid_text = query.get("cid", [""])[0]
    message_html = alert_html("error", error)
    categories: list[dict] = []
    shops: list[dict] = []
    metadata: dict = {}
    try:
        credentials = deps["account_credentials"](account)
        shops = deps["get_tiktok_shops"](credentials)
        categories = deps["load_categories"](credentials)
        if cid_text:
            metadata = deps["get_category_metadata"](
                int(cid_text),
                credentials,
                [int(shop["shopId"]) for shop in shops[:3]],
            )
    except Exception as exc:
        message_html += alert_html("error", exc)
    return single_pages.render_single_page(
        username,
        len(account_ids),
        account_options,
        selected_account_id,
        categories,
        cid_text,
        metadata,
        shops,
        message_html,
        deps["single_image_limit"],
    )


def render_ai_settings(message: str, error: str, deps: dict) -> bytes:
    settings = deps["load_ai_settings"]()
    account_count = len(deps["all_account_ids"]())
    return ai_pages.render_ai_settings(settings, deps["ai_provider_presets"], message, error, account_count)


def render_failure_page(
    title: str,
    error: object,
    back_url: str,
    back_label: str,
    username: str | None,
    deps: dict,
) -> bytes:
    account_count = len(deps["all_account_ids"]()) if username else 0
    detail = deps["readable_error_text"](error) or str(error)
    return system_pages.render_failure_page(title, detail, back_url, back_label, bool(username), account_count)
