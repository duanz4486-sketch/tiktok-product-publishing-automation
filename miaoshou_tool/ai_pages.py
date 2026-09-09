from __future__ import annotations

from . import page_shell
from .rendering import account_menu, alert_html, escape as e, json_for_html, top_nav


def render_ai_settings(settings: dict, presets: dict, message: str = "", error: str = "", account_count: int = 0) -> bytes:
    message_html = alert_html("success", message)
    error_html = alert_html("error", error)
    provider_key = str(settings.get("provider_key") or "deepseek")
    provider_options = "\n".join(
        f'<option value="{e(key)}"{" selected" if key == provider_key else ""}>{e(preset["label"])}</option>'
        for key, preset in presets.items()
    )
    preset_public = {
        key: {name: preset[name] for name in ("label", "model", "base_url", "help")}
        for key, preset in presets.items()
    }
    provider_help = presets.get(provider_key, presets["custom"])["help"]
    body = f"""
{top_nav("ai")}
<section>
  <div class="section-head">
    <div>
      <h2>AI 设置</h2>
      <p class="section-kicker">这里只保存用于图片识别和软参数建议的 AI 配置；页面提示默认中文，提交到妙手的内容仍要求英文。</p>
    </div>
  </div>
  {message_html}
  {error_html}
  <form action="/ai-settings" method="post" data-submit-lock>
    <input type="hidden" id="ai_settings_action" name="action" value="save">
    <div class="form-grid">
      <div class="field-card">
        <label for="provider_key">AI 服务</label>
        <select id="provider_key" name="provider_key">{provider_options}</select>
        <p class="field-help" id="providerHelp">{e(provider_help)}</p>
      </div>
      <div class="field-card">
        <label for="model">视觉模型</label>
        <input id="model" name="model" value="{e(settings.get("model", ""))}">
        <p class="field-help">需要支持图片识别，不能只用纯文本模型。</p>
      </div>
      <div class="field-card wide">
        <label for="base_url">接口地址</label>
        <input id="base_url" name="base_url" value="{e(settings.get("base_url", ""))}">
        <p class="field-help">填写 OpenAI 兼容的 Chat Completions 地址；也可以只填到 /v1，程序会自动补全 /chat/completions。</p>
      </div>
      <div class="field-card wide">
        <label for="api_key">API Key</label>
        <input id="api_key" name="api_key" type="password" placeholder="留空不改" autocomplete="new-password">
        <p class="field-help">保存后不会在页面明文显示，也不要提交到 GitHub。</p>
      </div>
      <div class="alert alert-info wide">页面默认中文；AI 自动填写只作为建议，最终保存到妙手的标题、描述、规格和自定义属性仍要求英文。图片和标题里没有明确证据的软参数应留空。</div>
    </div>
    <div class="actions">
      <button type="submit" data-working-label="正在保存 AI 设置..." onclick="document.getElementById('ai_settings_action').value='save'">保存 AI 设置</button>
      <button type="submit" class="ghost" data-working-label="正在测试 AI 配置..." onclick="document.getElementById('ai_settings_action').value='test'">测试当前配置</button>
    </div>
  </form>
</section>
<script>
const aiPresets = {json_for_html(preset_public)};
const providerSelect = document.getElementById('provider_key');
const modelInput = document.getElementById('model');
const baseUrlInput = document.getElementById('base_url');
const providerHelp = document.getElementById('providerHelp');
providerSelect?.addEventListener('change', () => {{
  const preset = aiPresets[providerSelect.value] || {{}};
  if (preset.model) modelInput.value = preset.model;
  if (preset.base_url) baseUrlInput.value = preset.base_url;
  providerHelp.textContent = preset.help || '';
}});
</script>"""
    return page_shell.render_page("AI 设置", body, header_right=account_menu(account_count))
