from __future__ import annotations

from typing import Any

from .rendering import escape as e
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
