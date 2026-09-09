from __future__ import annotations

from .errors import ai_status_text, readable_error_text, readable_job_error
from .jobs import ACTIVE_STATUSES, progress_html
from .page_shell import render_page
from .rendering import account_menu, escape as e, status_badge, top_nav


def render_job(job_id: str, job: dict | None, account_count: int = 0, show_account_menu: bool = False) -> bytes:
    if not job:
        return render_page("任务不存在", '<section><h2>任务不存在</h2><p><a href="/">返回首页</a></p></section>')

    refresh = job.get("status") in ACTIVE_STATUSES
    summary = job.get("summary") or {}
    rows = "".join(
        f"""<tr>
          <td>{e(item.get("seq"))}</td>
          <td>{status_badge(item.get("status"))}</td>
          <td>{'复用旧产品' if item.get("reused_existing") or item.get("reused_from_log") else '新建' if item.get("status") == "success" else ''}</td>
          <td>{e(item.get("image_count"))}</td>
          <td>{e(item.get("tiktokDetailId"))}</td>
          <td>{e(ai_status_text(item))}</td>
          <td class="error-cell">{e(readable_error_text(item.get("error")))}</td>
        </tr>"""
        for item in job.get("results", [])
    )
    if not rows:
        rows = '<tr><td colspan="7" class="empty-row">等待开始</td></tr>'

    job_error = readable_job_error(job)
    body = f"""
{top_nav("batch")}
<section>
  <div class="section-head">
    <div>
      <h2>{e(job.get("batch"))}</h2>
      <p class="section-kicker">妙手账号：{e(job.get("account_name"))}　提交人：{e(job.get("created_by"))}　模板：{e(job.get("template"))}</p>
    </div>
    <div>{status_badge(job.get("status"))}</div>
  </div>
  <p class="hint">已处理：{e(job.get("done_count", 0))}</p>
  {progress_html(job)}
  <div class="alert alert-info">预检失败序号：{e("、".join(str(seq) for seq in job.get("preflight_failed_seqs", [])[:30]) or "无")}<br>日志：{e(job.get("log_path") or summary.get("logPath") or "任务完成后生成")}</div>
  {f'<div class="alert alert-error">{e(job_error)}</div>' if job_error else ''}
  <p><a href="/">返回首页</a></p>
</section>
<section>
  <div class="section-head">
    <div>
      <h2>处理结果</h2>
      <p class="section-kicker">失败项会继续保留在本地日志里，方便重新整理后再跑。</p>
    </div>
  </div>
  <div class="table-wrap">
    <table>
      <thead><tr><th>序号</th><th>状态</th><th>处理方式</th><th>图片数</th><th>TikTok ID</th><th>AI状态</th><th>失败原因</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
</section>"""
    header_right = account_menu(account_count) if show_account_menu else ""
    return render_page("批次结果", body, refresh=refresh, header_right=header_right)
