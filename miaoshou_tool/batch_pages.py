from __future__ import annotations

from typing import Any

from .errors import readable_job_error
from .jobs import ACTIVE_STATUSES, job_count_text, progress_html
from .page_shell import render_page
from .rendering import account_menu, escape as e, status_badge, top_nav


def render_home(
    available_accounts: list[tuple[str, dict[str, Any]]],
    account_ids: list[str],
    jobs: list[tuple[str, dict[str, Any]]],
    templates: dict[str, Any],
    default_template: str,
) -> bytes:
    account_options = "\n".join(
        f'<option value="{e(account_id)}">{e(account.get("name", account_id))}</option>'
        for account_id, account in available_accounts
    )
    template_options = "\n".join(
        f'<option value="{e(name)}" {"selected" if name == default_template else ""}>{e(name)}</option>'
        for name in templates
    )
    active_pairs = [
        (job_id, job)
        for job_id, job in reversed(jobs)
        if job.get("status") in ACTIVE_STATUSES and job.get("account_id") in account_ids
    ]
    recent_jobs = jobs[-10:][::-1]
    locked = len(available_accounts) == 1 and bool(active_pairs)
    disabled = "disabled" if locked else ""
    active_account_ids = {str(job.get("account_id")) for _, job in active_pairs if job.get("account_id")}
    active_account_data = e(",".join(active_account_ids))
    active_notice = _active_notice(active_pairs)
    job_rows = _recent_job_rows(recent_jobs)
    body = f"""
{top_nav("batch")}
{active_notice}
<section>
  <div class="section-head">
    <div>
      <h2>新建批次</h2>
      <p class="section-kicker">适合标题和图片不同、类目参数相同的模板批量上货。</p>
    </div>
  </div>
  <form id="batchForm" action="/run" method="post" enctype="multipart/form-data" data-submit-lock data-active-accounts="{active_account_data}">
    <fieldset {disabled}>
    <div id="accountBusyMessage" class="alert alert-warn" hidden>这个妙手账号正在处理上一批。请等待完成，或切换到其他空闲妙手账号。</div>
    <div class="form-grid">
      <div class="field-card">
        <label for="account_id">妙手账号</label>
        <select id="account_id" name="account_id">{account_options}</select>
        <p class="field-help">每个妙手账号单独排队，避免同账号批次互相影响。</p>
      </div>
      <div class="field-card">
        <label for="batch">批次名</label>
        <input id="batch" name="batch" required placeholder="只作为任务名称，例如：第1批">
        <p class="field-help">不参与图片匹配，可以按团队习惯自由命名。</p>
      </div>
      <div class="field-card">
        <label for="template">产品模板</label>
        <select id="template" name="template">{template_options}</select>
        <p class="field-help">固定参数来自已保存的妙手模板。</p>
      </div>
      <div class="field-card">
        <label for="title_file">标题 Excel</label>
        <input id="title_file" name="title_file" type="file" accept=".xlsx,.xlsm" required>
        <p class="field-help">优先按表头识别“序号”和“标题”。</p>
      </div>
      <div class="field-card">
        <label>图片来源</label>
        <div class="upload-choice-row">
          <label class="upload-button" for="batch_image_zip">选择图片 ZIP</label>
          <label class="upload-button" for="batch_image_folder">选择图片文件夹</label>
          <span id="batchImageChoice" class="file-choice-name">未选择任何文件</span>
        </div>
        <input class="hidden-file" id="batch_image_zip" name="image_zip" type="file" accept=".zip">
        <input class="hidden-file" id="batch_image_folder" name="image_folder" type="file" accept="image/*" multiple webkitdirectory directory>
        <p class="field-help">支持 ZIP 或大文件夹；子文件夹名要和 Excel 序号对应。</p>
      </div>
      <div class="field-card">
        <label for="limit">只处理前几个产品</label>
        <input id="limit" name="limit" type="number" min="1" placeholder="留空就是全部">
        <p class="field-help">测试时填 1 或 5；正式跑可留空。</p>
      </div>
      <div class="check-row">
        <input id="upload_to_oss" name="upload_to_oss" type="checkbox" checked>
        <div>
          <label for="upload_to_oss">自动上传图片到 OSS</label>
          <p class="field-help">只需要上传一次 ZIP，程序会先传 OSS 再提交妙手。</p>
        </div>
      </div>
      <div class="check-row">
        <input id="dry_run" name="dry_run" type="checkbox" checked>
        <div>
          <label for="dry_run">先预检，不创建产品</label>
          <p class="field-help">首次测试建议保留勾选，确认匹配后再正式创建。</p>
        </div>
      </div>
      <div class="alert alert-info wide">以本次上传的 Excel 和图片来源为准；匹配只看 Excel 的序号列和图片子文件夹名字。两边都有的序号会处理，缺标题或缺图片的序号会记为失败。勾选自动上传后，程序会用本次图片上传并覆盖 OSS 同路径旧文件。</div>
    </div>
    <div class="actions"><button id="batchSubmit" type="submit" data-working-label="正在创建任务..." {disabled}>{'当前账号处理中' if locked else '开始处理'}</button></div>
    </fieldset>
  </form>
  <script>
    (() => {{
      const form = document.getElementById('batchForm');
      if (!form) return;
      const activeAccounts = new Set((form.dataset.activeAccounts || '').split(',').filter(Boolean));
      const account = document.getElementById('account_id');
      const submit = document.getElementById('batchSubmit');
      const message = document.getElementById('accountBusyMessage');
      const imageZip = document.getElementById('batch_image_zip');
      const imageFolder = document.getElementById('batch_image_folder');
      const imageChoice = document.getElementById('batchImageChoice');
      function setImageChoice(input, otherInput, label) {{
        if (!input || !input.files || !input.files.length) return;
        if (otherInput) otherInput.value = '';
        if (imageChoice) {{
          const count = input.files.length;
          imageChoice.textContent = count === 1 ? input.files[0].name : `${{label}}，共 ${{count}} 个图片文件`;
        }}
      }}
      if (imageZip) imageZip.addEventListener('change', () => setImageChoice(imageZip, imageFolder, '已选择 ZIP'));
      if (imageFolder) imageFolder.addEventListener('change', () => setImageChoice(imageFolder, imageZip, '已选择文件夹'));
      form.addEventListener('submit', (event) => {{
        const hasZip = imageZip && imageZip.files && imageZip.files.length;
        const hasFolder = imageFolder && imageFolder.files && imageFolder.files.length;
        if (!hasZip && !hasFolder) {{
          event.preventDefault();
          event.stopImmediatePropagation();
          alert('请选择图片 ZIP 或图片文件夹');
        }}
      }});
      function updateBatchSubmit() {{
        const busy = account && activeAccounts.has(account.value);
        if (submit) {{
          submit.disabled = !!busy;
          submit.textContent = busy ? '当前账号处理中' : '开始处理';
        }}
        if (message) message.hidden = !busy;
      }}
      if (account) account.addEventListener('change', updateBatchSubmit);
      updateBatchSubmit();
    }})();
  </script>
</section>
<section>
  <div class="section-head">
    <div>
      <h2>最近任务</h2>
      <p class="section-kicker">点击批次名查看进度、失败序号和本地日志路径。</p>
    </div>
  </div>
  <div class="table-wrap">
    <table>
      <thead><tr><th>批次</th><th>妙手账号</th><th>提交人</th><th>模板</th><th>状态</th><th>已处理</th><th>失败原因</th><th>创建时间</th></tr></thead>
      <tbody>{job_rows}</tbody>
    </table>
  </div>
</section>"""
    return render_page("妙手 TikTok 批量上货工具", body, refresh=locked, header_right=account_menu(len(available_accounts)))


def _active_notice(active_pairs: list[tuple[str, dict[str, Any]]]) -> str:
    if not active_pairs:
        return ""
    active_items = "".join(
        f"""<p class="hint">账号：{e(job.get("account_name"))}　批次：{e(job.get("batch"))}　<a href="/job?id={e(job_id)}">查看进度</a></p>
  {progress_html(job)}"""
        for job_id, job in active_pairs[:3]
    )
    return f"""
<section class="alert alert-warn">
  <div class="section-head">
    <div>
      <h2>有妙手账号正在处理</h2>
      <p class="section-kicker">同一个妙手账号完成前不能提交下一批；其他空闲妙手账号可以继续使用。</p>
    </div>
  </div>
  {active_items}
</section>"""


def _recent_job_rows(jobs: list[tuple[str, dict[str, Any]]]) -> str:
    rows = "".join(
        f"""<tr>
          <td><a href="/job?id={e(job_id)}">{e(job.get("batch"))}</a></td>
          <td>{e(job.get("account_name"))}</td>
          <td>{e(job.get("created_by"))}</td>
          <td>{e(job.get("template"))}</td>
          <td>{status_badge(job.get("status"))}</td>
          <td>{e(job_count_text(job))}</td>
          <td class="error-cell">{e(readable_job_error(job))}</td>
          <td>{e(job.get("created_at"))}</td>
        </tr>"""
        for job_id, job in jobs
    )
    return rows or '<tr><td colspan="8" class="empty-row">还没有任务</td></tr>'
