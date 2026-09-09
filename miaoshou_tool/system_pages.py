from __future__ import annotations

from . import page_shell
from .rendering import account_menu, alert_html, escape as e, status_badge, top_nav


def render_setup_needed() -> bytes:
    body = """
<section>
  <h2>还没有配置妙手账号</h2>
  <p class="hint">请先进入「妙手账号管理」新增妙手账号。真实妙手密钥只保存在本机 accounts.json，不要放进 GitHub。</p>
  <p><a href="/accounts">去配置妙手账号</a>　<a href="/check">查看系统自检</a></p>
</section>"""
    return page_shell.render_page("需要配置", body)


def render_release_check(report: dict, account_count: int) -> bytes:
    summary = report["summary"]
    rows = "".join(
        f"""<tr>
          <td>{status_badge(item["status"])}</td>
          <td>{e(item["label"])}</td>
          <td>{e(item["message"])}</td>
          <td>{e(item.get("fix") if item["status"] != "ok" and item.get("fix") else "无需处理")}</td>
        </tr>"""
        for item in report["checks"]
    )
    overall = "success" if report["ok"] else "error"
    overall_text = "基础配置可以运行模板批量上传。" if report["ok"] else "还有必需配置未完成，请先处理红色失败项。"
    body = f"""
{top_nav("check")}
<section>
  <div class="section-head">
    <div>
      <h2>系统自检</h2>
      <p class="section-kicker">用于公开部署或换电脑部署后，快速确认模板批量上传入口是否准备好。</p>
    </div>
  </div>
  {alert_html(overall, overall_text)}
  <div class="progress-meta">
    <span>正常 {e(summary["ok"])}</span>
    <span>提醒 {e(summary["warn"])}</span>
    <span>失败 {e(summary["error"])}</span>
  </div>
</section>
<section>
  <div class="section-head">
    <div>
      <h2>检查结果</h2>
      <p class="section-kicker">自检只检查配置是否齐全，不会调用妙手创建产品，也不会显示任何密钥明文。</p>
    </div>
  </div>
  <div class="table-wrap">
    <table>
      <thead><tr><th>状态</th><th>项目</th><th>结果</th><th>处理方式</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
</section>"""
    return page_shell.render_page("系统自检", body, header_right=account_menu(account_count))


def render_failure_page(title: str, detail: str, back_url: str, back_label: str, with_nav: bool = False, account_count: int = 0) -> bytes:
    header_right = account_menu(account_count) if with_nav else ""
    body = f"""
{top_nav("batch") if with_nav else ""}
<section>
  <div class="section-head">
    <div>
      <h2>{e(title)}</h2>
      <p class="section-kicker">请按提示修正后重新提交；已经成功保存的本地配置不会被覆盖。</p>
    </div>
  </div>
  {alert_html("error", detail)}
  <p><a href="{e(back_url)}">{e(back_label)}</a></p>
</section>"""
    return page_shell.render_page(title, body, header_right=header_right)
