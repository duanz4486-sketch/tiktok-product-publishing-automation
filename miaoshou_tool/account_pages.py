from __future__ import annotations

from typing import Any

from .page_shell import render_page
from .rendering import account_menu, escape as e, top_nav
from .text import masked_app_key


def render_account_row(account_id: str, account: dict[str, Any], templates: dict[str, Any]) -> str:
    locked = bool(account.get("locked"))
    readonly = "readonly" if locked else ""
    disabled = "disabled" if locked else ""
    lock_class = "locked" if locked else "unlocked"
    lock_text = "已上锁，点击开锁" if locked else "未上锁，点击上锁"
    shop_label = e(account.get("shop_id") or "")
    if account.get("shop_name"):
        shop_label += f"<br><span class=\"hint\">{e(account.get('shop_name'))}</span>"
    saved_templates = account.get("templates") or {}
    template_inputs = "".join(
        f"""<div>
                <label>{e(name)}模板 ID</label>
                <input name="template_{e(name)}" type="number" value="{e(saved_templates.get(name) or '')}" placeholder="留空自动识别" {readonly}>
              </div>"""
        for name in templates
    )
    return f"""<tr>
          <td>{e(account.get("name", account_id))}</td>
          <td>{shop_label}</td>
          <td>{e(masked_app_key(account.get("app_key")))} / {'Secret 已配置' if account.get("app_secret") else '缺少 Secret'}</td>
          <td>
            <form action="/accounts/toggle-lock" method="post" data-submit-lock>
              <input type="hidden" name="account_id" value="{e(account_id)}">
              <button type="submit" class="lock-switch {lock_class}" data-working-label="正在切换账号锁...">
                <span class="lock-track"></span><span>{lock_text}</span>
              </button>
            </form>
          </td>
          <td>
            <div class="account-actions">
            <form action="/accounts/update" method="post" class="account-edit-form" data-submit-lock>
              <input type="hidden" name="account_id" value="{e(account_id)}">
              <div>
                <label>妙手账号名称</label>
                <input name="name" value="{e(account.get('name', account_id))}" required {readonly}>
              </div>
              <div>
                <label>妙手账号</label>
                <input name="shop_id" type="number" value="{e(account.get('shop_id') or '')}" placeholder="留空自动识别" {readonly}>
              </div>
              <div>
                <label>APP ID / App Key</label>
                <input name="app_key" type="password" placeholder="留空不改" autocomplete="new-password" {readonly}>
              </div>
              <div>
                <label>App Secret</label>
                <input name="app_secret" type="password" placeholder="留空不改" autocomplete="new-password" {readonly}>
              </div>
              {template_inputs}
              <div class="actions-row"><button type="submit" class="ghost" data-working-label="正在保存..." {disabled}>保存</button></div>
            </form>
            <form action="/accounts/delete" method="post" onsubmit="return confirm('确认删除这个妙手账号？')">
              <input type="hidden" name="account_id" value="{e(account_id)}">
              <button type="submit" class="danger" {disabled}>删除</button>
            </form>
            </div>
          </td>
        </tr>"""


def render_accounts(config: dict[str, Any], account_ids: list[str], templates: dict[str, Any], message: str = "", error: str = "") -> bytes:
    accounts = config.get("accounts", {})
    rows = "".join(
        render_account_row(account_id, account, templates)
        for account_id, account in ((account_id, accounts[account_id]) for account_id in account_ids if account_id in accounts)
    )
    if not rows:
        rows = '<tr><td colspan="5" class="empty-row">还没有妙手账号</td></tr>'
    template_inputs = "\n".join(
        f"""<div>
        <label for="template_{e(name)}">{e(name)}模板 ID</label>
        <input id="template_{e(name)}" name="template_{e(name)}" type="number" placeholder="留空自动识别">
      </div>"""
        for name in templates
    )
    message_html = f'<div class="alert alert-success">{e(message)}</div>' if message else ""
    error_html = f'<div class="alert alert-error">{e(error)}</div>' if error else ""
    body = f"""
{top_nav("accounts")}
<section>
  <div class="section-head">
    <div>
      <h2>妙手账号管理</h2>
      <p class="section-kicker">一个网页账号可以保存多个妙手账号；上锁后不能修改或删除，适合调试稳定后的账号。</p>
    </div>
  </div>
  {message_html}
  {error_html}
  <div class="table-wrap">
    <table>
      <thead><tr><th>妙手账号名称</th><th>妙手账号</th><th>接口应用</th><th>账号锁</th><th>修改信息</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
</section>
<section>
  <div class="section-head">
    <div>
      <h2>新增妙手账号</h2>
      <p class="section-kicker">保存前会先用 App Key 和 App Secret 识别店铺与模板，确认无误后再写入本地配置。</p>
    </div>
  </div>
  <form action="/accounts/add" method="post" data-submit-lock>
    <div class="form-grid">
      <div class="field-card">
        <label for="name">妙手账号名称</label>
        <input id="name" name="name" required placeholder="例如：小王账号、美国店1号">
        <p class="field-help">只显示在网页下拉框里，方便团队切换。</p>
      </div>
      <div class="field-card">
        <label for="shop_id">妙手账号</label>
        <input id="shop_id" name="shop_id" type="number" placeholder="留空自动识别">
        <p class="field-help">不确定就留空，程序会从妙手接口识别。</p>
      </div>
      <div class="field-card">
        <label for="app_key">APP ID / App Key</label>
        <input id="app_key" name="app_key" type="password" required autocomplete="off">
        <p class="field-help">填妙手开放平台应用列表里的 APP ID。</p>
      </div>
      <div class="field-card">
        <label for="app_secret">App Secret</label>
        <input id="app_secret" name="app_secret" type="password" required autocomplete="off">
        <p class="field-help">保存后页面不会展示明文。</p>
      </div>
      {template_inputs}
      <div class="alert alert-info wide">妙手账号名称只给网页下拉框使用；妙手开放平台里的 APP ID 填到「APP ID / App Key」，App Secret 填到「App Secret」。妙手账号和模板 ID 可留空，程序会按「大地毯、非定制毛毯、定制毛毯」三个关键词自动识别。</div>
    </div>
    <div class="actions"><button type="submit" data-working-label="正在识别账号...">识别并保存</button></div>
  </form>
</section>"""
    return render_page("妙手账号管理", body, header_right=account_menu(len(account_ids)))


def render_account_confirm(token: str, pending: dict[str, Any] | None, template_names: list[str], account_count: int) -> bytes:
    if not pending:
        return render_page("确认已失效", '<section><h2>确认已失效</h2><p><a href="/accounts">返回妙手账号管理</a></p></section>')
    templates = pending.get("templates") or {}
    template_rows = "".join(
        f"<tr><td>{e(name)}</td><td>{e(templates.get(name))}</td></tr>"
        for name in template_names
    )
    shop_name = pending.get("shop_name") or "妙手接口未返回店铺名称，请核对 shopId"
    body = f"""
{top_nav("accounts")}
<section>
  <div class="section-head">
    <div>
      <h2>确认妙手账号</h2>
      <p class="section-kicker">请确认识别结果属于你要保存的妙手账号。确认后才会写入本地配置；取消则不会保存。</p>
    </div>
  </div>
  <div class="table-wrap">
    <table>
      <tbody>
        <tr><th>妙手账号名称</th><td>{e(pending.get("name"))}</td></tr>
        <tr><th>识别到的店铺名称</th><td>{e(shop_name)}</td></tr>
        <tr><th>识别到的 shopId</th><td>{e(pending.get("shop_id"))}</td></tr>
        <tr><th>接口应用</th><td>{e(masked_app_key(pending.get("app_key")))} / Secret 已配置</td></tr>
      </tbody>
    </table>
  </div>
</section>
<section>
  <div class="section-head">
    <div>
      <h2>识别到的模板</h2>
      <p class="section-kicker">模板按“大地毯、非定制毛毯、定制毛毯”关键词识别。</p>
    </div>
  </div>
  <div class="table-wrap">
    <table>
      <thead><tr><th>产品模板</th><th>模板 ID</th></tr></thead>
      <tbody>{template_rows}</tbody>
    </table>
  </div>
  <form action="/accounts/confirm" method="post" class="actions" data-submit-lock>
    <input type="hidden" name="token" value="{e(token)}">
    <button type="submit" name="action" value="save" data-working-label="正在保存账号...">确认保存</button>
    <button type="submit" name="action" value="cancel" class="ghost">取消</button>
  </form>
</section>"""
    return render_page("确认妙手账号", body, header_right=account_menu(account_count))
