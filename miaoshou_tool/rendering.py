from __future__ import annotations

import html
from typing import Any

from . import json_io

STATUS_LABELS = {
    "ok": "正常",
    "warn": "提醒",
    "error": "失败",
    "queued": "排队中",
    "uploading": "上传图片",
    "ai_processing": "AI识别中",
    "running": "处理中",
    "started": "已开始",
    "done": "已完成",
    "done_with_errors": "部分失败",
    "failed": "失败",
    "success": "成功",
    "dry_run_ok": "预检通过",
}


def escape(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def alert_html(kind: str, message: object) -> str:
    text = str(message or "").strip()
    return f'<div class="alert alert-{escape(kind)}">{escape(text)}</div>' if text else ""


def status_label(status: object) -> str:
    return STATUS_LABELS.get(str(status or ""), str(status or "未知"))


def status_badge(status: object) -> str:
    raw = str(status or "unknown")
    return f'<span class="badge status {escape(raw)}">{escape(status_label(raw))}</span>'


def json_for_html(data: Any) -> str:
    return json_io.dumps(data, compact=True).replace("</", "<\\/")


def account_menu(account_count: int) -> str:
    display_name = "团队工作台"
    return f"""
<details class="account">
  <summary aria-label="账户">
    <span class="avatar">MS</span>
    <span class="account-summary-text"><strong>{display_name}</strong><small>{escape(account_count)} 个妙手账号</small></span>
  </summary>
  <div class="account-panel">
    <p class="account-name">{display_name}</p>
    <p class="account-meta">可用妙手账号：{escape(account_count)}</p>
    <a class="account-link" href="/">模板批量上传</a>
    <a class="account-link" href="/check">系统自检</a>
    <a class="account-link" href="/single">单产品智能上传</a>
    <a class="account-link" href="/ai-settings">AI 设置</a>
    <a class="account-link" href="/accounts">妙手账号管理</a>
  </div>
</details>"""


def top_nav(current: str = "batch") -> str:
    def nav_class(name: str) -> str:
        return ' class="active"' if current == name else ""

    return f"""
<nav class="top-nav">
  <a href="/"{nav_class("batch")}>模板批量上传</a>
  <a href="/check"{nav_class("check")}>系统自检</a>
  <a href="/single"{nav_class("single")}>单产品智能上传</a>
  <a href="/accounts"{nav_class("accounts")}>妙手账号管理</a>
  <a href="/ai-settings"{nav_class("ai")}>AI 设置</a>
</nav>"""
