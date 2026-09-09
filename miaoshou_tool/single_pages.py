from __future__ import annotations

from .miaoshou_api import attr_label, category_required_notes, is_required_attr, metadata_attrs, shop_display_name
from .page_shell import render_page
from .rendering import account_menu, alert_html, top_nav
from .rendering import escape as e
from .rendering import json_for_html


def render_attr_control(attr: dict) -> str:
    attr_id = str(attr.get("attrId") or "")
    required = is_required_attr(attr)
    required_html = ' <span class="required-mark">*</span>' if required else ""
    required_attr = "required" if required and not attr.get("isCustomized") else ""
    values = attr.get("values") or []
    options = '<option value="">不填写</option>' + "".join(
        f'<option value="{e(item.get("id"))}">{e(item.get("valueNameAlias") or item.get("name") or item.get("id"))} / {e(item.get("name") or item.get("id"))}</option>'
        for item in values
    )
    select_html = f'<select name="attr_{e(attr_id)}" {required_attr}>{options}</select>' if values else ""
    custom_html = ""
    if attr.get("isCustomized") or not values:
        custom_required = "required" if required and not values else ""
        custom_html = f'<input name="attr_custom_{e(attr_id)}" placeholder="英文自定义值" {custom_required}>'
    return f"""
      <div class="field-card">
        <label>{e(attr_label(attr))}{required_html}</label>
        {select_html}
        {custom_html}
      </div>"""


def selected_category_path(categories: list[dict], cid: str) -> str:
    for row in categories:
        if str(row.get("cid")) == str(cid):
            return str(row.get("path") or "")
    return ""


def render_category_picker(categories: list[dict], cid_text: str) -> str:
    selected_path = selected_category_path(categories, cid_text)
    data = [
        {"cid": row["cid"], "path": row["path"]}
        for row in categories
        if row.get("cid") and row.get("path")
    ]
    return f"""
      <div class="wide">
        <label for="categorySearch">TikTok 美国站类目</label>
        <input id="categorySearch" placeholder="搜索或在下方手动选择类目" value="{e(selected_path)}" autocomplete="off">
        <input id="cid" name="cid" type="hidden" value="{e(cid_text)}" required>
        <div class="category-picker"><div id="categoryColumns" class="category-columns"></div></div>
        <p id="categorySelected" class="hint">{"当前选择：" + e(selected_path) if selected_path else "请选择末级类目"}</p>
      </div>
      <script id="categoryData" type="application/json">{json_for_html(data)}</script>
      <script>
      (() => {{
        const rows = JSON.parse(document.getElementById('categoryData').textContent || '[]');
        const cidInput = document.getElementById('cid');
        const search = document.getElementById('categorySearch');
        const columns = document.getElementById('categoryColumns');
        const selected = document.getElementById('categorySelected');
        let picked = rows.find(row => String(row.cid) === String(cidInput.value));
        let prefix = picked ? picked.path.split(' / ').slice(0, -1) : [];

        function parts(row) {{ return row.path.split(' / '); }}
        function matchesPrefix(row, value) {{
          const p = parts(row);
          return value.every((item, index) => p[index] === item);
        }}
        function setLeaf(row) {{
          cidInput.value = row.cid;
          search.value = row.path;
          selected.textContent = '当前选择：' + row.path;
          picked = row;
          prefix = parts(row).slice(0, -1);
          renderColumns();
        }}
        function renderSearch() {{
          const term = search.value.trim().toLowerCase();
          if (!term || (picked && term === picked.path.toLowerCase())) {{
            renderColumns();
            return;
          }}
          columns.innerHTML = '';
          const col = document.createElement('div');
          col.className = 'category-column';
          rows.filter(row => row.path.toLowerCase().includes(term)).slice(0, 80).forEach(row => {{
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'category-item leaf';
            button.textContent = row.path;
            button.onclick = () => setLeaf(row);
            col.appendChild(button);
          }});
          columns.appendChild(col);
        }}
        function renderColumns() {{
          columns.innerHTML = '';
          let current = [];
          let level = 0;
          while (true) {{
            const choices = new Map();
            for (const row of rows) {{
              const p = parts(row);
              if (p.length <= level || !matchesPrefix(row, current)) continue;
              const label = p[level];
              const old = choices.get(label) || {{ label, cid: '', leaf: true }};
              if (p.length > level + 1) old.leaf = false;
              if (p.length === level + 1) old.cid = row.cid;
              choices.set(label, old);
            }}
            if (!choices.size) break;
            const col = document.createElement('div');
            col.className = 'category-column';
            const levelPrefix = current.slice();
            for (const choice of choices.values()) {{
              const button = document.createElement('button');
              button.type = 'button';
              button.className = 'category-item' + (choice.leaf ? ' leaf' : '');
              if (prefix[level] === choice.label || (picked && choice.cid && String(picked.cid) === String(choice.cid))) button.className += ' active';
              button.textContent = choice.label + (choice.leaf ? '' : ' ›');
              button.onclick = () => {{
                if (choice.leaf) {{
                  const row = rows.find(item => String(item.cid) === String(choice.cid));
                  if (row) setLeaf(row);
                }} else {{
                  const nextPrefix = levelPrefix.concat(choice.label);
                  prefix = nextPrefix;
                  picked = null;
                  cidInput.value = '';
                  search.value = nextPrefix.join(' / ');
                  selected.textContent = '当前选择：' + nextPrefix.join(' / ');
                  renderColumns();
                }}
              }};
              col.appendChild(button);
            }}
            columns.appendChild(col);
            if (!prefix[level]) break;
            current = current.concat(prefix[level]);
            level += 1;
          }}
        }}
        search.addEventListener('input', renderSearch);
        renderColumns();
      }})();
      </script>"""


def _shop_checks(shops: list[dict]) -> str:
    return "".join(
        f'<label><input type="checkbox" name="shop_id" value="{e(shop.get("shopId"))}"> {e(shop_display_name(shop))}</label>'
        for shop in shops
    ) or '<p class="hint">当前妙手账号没有返回 TikTok 美国店铺。</p>'


def _required_attr_html(metadata: dict) -> str:
    required_attrs = [attr for attr in metadata_attrs(metadata, "categoryProductAttrList") if is_required_attr(attr)]
    all_product_attrs = metadata_attrs(metadata, "categoryProductAttrList")
    config_notes = category_required_notes(metadata)
    if required_attrs:
        return "".join(render_attr_control(attr) for attr in required_attrs)
    note_html = "<br>".join(e(note) for note in config_notes)
    if all_product_attrs:
        return f'<div class="alert alert-info wide">这个类目已读取 {len(all_product_attrs)} 个商品属性，但妙手没有标记必须填写的商品属性。可展开下面的可选属性按需要补充。{("<br>" + note_html) if note_html else ""}</div>'
    if metadata:
        return f'<div class="alert alert-warn wide">类目参数已加载，但妙手接口没有返回商品属性列表。可以先确认店铺和类目是否匹配，或换一个末级类目重新加载。{("<br>" + note_html) if note_html else ""}</div>'
    return '<p class="hint wide">选择类目后会显示必填属性。</p>'


def _sale_attr_context(metadata: dict) -> tuple[str, str, str, str]:
    sale_attrs = metadata_attrs(metadata, "categorySaleAttrList")
    default_sale_attr_id = str(sale_attrs[0].get("attrId") or "") if sale_attrs else ""
    spec_name_options = "".join(f'<option value="{e(attr_label(attr))}"></option>' for attr in sale_attrs)
    sale_attr_pairs = [
        {"name": attr_label(attr), "id": str(attr.get("attrId") or "")}
        for attr in sale_attrs
        if attr.get("attrId")
    ]
    if sale_attrs:
        sale_attr_note = '<p class="section-kicker">规格名称可以选择妙手返回的选项，也可以自己输入。页面只需要维护一组销售规格。</p>'
    elif metadata:
        sale_attr_note = '<div class="alert alert-warn wide">当前类目没有返回销售属性，保存 SKU 时可能会被妙手拒绝。建议换一个末级类目重新加载。</div>'
    else:
        sale_attr_note = ""
    return default_sale_attr_id, spec_name_options, json_for_html(sale_attr_pairs), sale_attr_note


def render_single_page(
    username: str,
    account_count: int,
    account_options: str,
    selected_account_id: str,
    categories: list[dict],
    cid_text: str,
    metadata: dict,
    shops: list[dict],
    message_html: str,
    image_limit: int,
) -> bytes:
    required_attr_html = _required_attr_html(metadata)
    optional_attrs = [attr for attr in metadata_attrs(metadata, "categoryProductAttrList") if not is_required_attr(attr)]
    optional_attr_html = "".join(render_attr_control(attr) for attr in optional_attrs[:30])
    shop_checks = _shop_checks(shops)
    default_sale_attr_id, spec_name_options, sale_attr_pairs_json, sale_attr_note = _sale_attr_context(metadata)

    metadata_form = f"""
<section>
  <h2>选择类目</h2>
  {alert_html("warn", "单产品智能上传仍在开发和完善中。公开给别人试用时，建议优先使用已经跑通的「模板批量上传」。")}
  {message_html}
  <form action="/single" method="get">
    <div class="grid">
      <div>
        <label for="single_account_id">妙手账号</label>
        <select id="single_account_id" name="account_id">{account_options}</select>
      </div>
      {render_category_picker(categories, cid_text)}
    </div>
    <div class="actions"><button type="submit">加载类目参数</button></div>
  </form>
</section>"""

    product_form = ""
    if cid_text and metadata:
        product_form = f"""
<form id="singleProductForm" action="/single/create" method="post" enctype="multipart/form-data" data-submit-lock>
  <input type="hidden" name="account_id" value="{e(selected_account_id)}">
  <input type="hidden" name="cid" value="{e(cid_text)}">
  <input type="hidden" id="ai_suggest_applied" name="ai_suggest_applied" value="0">
  <section>
    <h2>产品基础信息</h2>
    <p class="section-kicker">先填写页面上最核心的信息；类目属性、规格价格、物流包装会在后面分段填写。</p>
    <div class="form-grid">
      <div class="field-card wide">
        <label for="title">英文标题 <span class="required-mark">*</span></label>
        <input id="title" name="title" required minlength="25" maxlength="255">
        <p class="field-help">按妙手限制控制在 25-255 字符。</p>
      </div>
      <div class="field-card wide">
        <label for="notes">英文详情描述</label>
        <textarea id="notes" name="notes" maxlength="10000" placeholder="不填时用标题生成一段英文描述"></textarea>
        <p class="field-help">不填写时会用标题生成基础英文描述。</p>
      </div>
      <div class="alert alert-info wide" id="aiSuggestStatus">
        AI 可以读取标题和前几张产品图片，生成英文描述并尝试填写有明确依据的类目属性；不确定的软参数会保持空白。
      </div>
      <div class="field-card">
        <label for="item_num">产品编号</label>
        <input id="item_num" name="item_num" maxlength="50" placeholder="可不填">
      </div>
    </div>
  </section>
  <section>
    <h2>产品图片</h2>
    <div class="form-grid">
      <div class="field-card wide">
        <label>产品图片</label>
        <div class="upload-actions">
          <label class="upload-button" for="image_upload_files">选择图片或 ZIP</label>
          <label class="upload-button" for="image_upload_folder">选择图片文件夹</label>
        </div>
        <input class="hidden-file" id="image_upload_files" name="image_upload" type="file" accept="image/*,.zip" multiple>
        <input class="hidden-file" id="image_upload_folder" name="image_upload" type="file" accept="image/*" multiple webkitdirectory directory>
        <p class="field-help">同一个上传区支持单张图片、多张图片、图片文件夹或图片 ZIP。</p>
      </div>
      <div class="field-card">
        <label for="main_video">主图视频</label>
        <input id="main_video" name="main_video" type="file" accept="video/mp4,video/quicktime,video/webm,.mp4,.mov,.m4v,.webm">
        <p class="field-help">可选，只用于单产品智能上传。</p>
      </div>
      <div class="alert alert-info wide">按文件名自然排序，只保存上传前 {image_limit} 张；少于 {image_limit} 张不会报错。</div>
    </div>
    <div class="actions">
      <button id="aiSuggestButton" type="button" class="ghost" data-working-label="AI 正在识别图片...">AI 生成描述和属性建议</button>
    </div>
  </section>
  <section>
    <h2>类目必填属性</h2>
    <div class="form-grid">{required_attr_html}</div>
  </section>
  <section>
    <h2>可选属性</h2>
    <details>
      <summary>展开可选软参数</summary>
      <div class="form-grid" style="margin-top: 14px;">{optional_attr_html or '<p class="hint wide">这个类目没有更多可选属性。</p>'}</div>
    </details>
  </section>
  <section>
    <h2>规格与价格</h2>
    <input type="hidden" name="sale_attr_id" value="{e(default_sale_attr_id)}">
    {sale_attr_note}
    <div class="form-grid">
      <div class="field-card wide">
        <label for="spec_name">规格名称 <span class="required-mark">*</span></label>
        <input id="spec_name" name="spec_name" list="spec_name_options" placeholder="例如：Bedding Size、Color、Style" required>
        <datalist id="spec_name_options">{spec_name_options}</datalist>
        <p class="field-help">对应妙手页面里的“规格一”，可选择也可手动输入。</p>
      </div>
    </div>
    <div id="skuRows" style="margin-top: 14px;">
      <div class="sku-row">
        <input type="hidden" name="sku_row_id" value="0">
        <div><label>规格值</label><input name="sku_value" placeholder="例如：30x40inch (For Babys)" required></div>
        <div><label>价格 USD</label><input name="sku_price" type="number" min="0.01" step="0.01" required></div>
        <div><label>库存</label><input name="sku_stock" type="number" min="0" step="1" required></div>
        <div><label>规格图</label><input name="sku_image_file_0" type="file" accept="image/*"><span class="hint">不传用第一张主图</span></div>
        <button type="button" class="ghost mini-button" onclick="removeSkuRow(this)">删除</button>
      </div>
    </div>
    <button type="button" class="ghost mini-button" onclick="addSkuRow()">添加规格值</button>
  </section>
  <section>
    <h2>物流/包装信息</h2>
    <p class="section-kicker">这些字段用于创建采集箱产品，不属于标题和类目属性，所以放到靠后的包装分段。</p>
    <div class="form-grid">
      <div class="field-card">
        <label for="weight">重量 kg <span class="required-mark">*</span></label>
        <input id="weight" name="weight" type="number" min="0.001" max="100" step="0.001" required>
      </div>
      <div class="field-card">
        <label for="package_length">包装长度 cm <span class="required-mark">*</span></label>
        <input id="package_length" name="package_length" type="number" min="1" max="1000" step="0.1" required>
      </div>
      <div class="field-card">
        <label for="package_width">包装宽度 cm <span class="required-mark">*</span></label>
        <input id="package_width" name="package_width" type="number" min="1" max="1000" step="0.1" required>
      </div>
      <div class="field-card">
        <label for="package_height">包装高度 cm <span class="required-mark">*</span></label>
        <input id="package_height" name="package_height" type="number" min="1" max="1000" step="0.1" required>
      </div>
    </div>
  </section>
  <section>
    <h2>选择店铺</h2>
    <div class="shop-grid">{shop_checks}</div>
    <div class="actions"><button type="submit" data-working-label="正在保存到妙手...">保存到妙手</button></div>
</section>
</form>
<script>
let skuNextId = 1;
const saleAttrPairs = {sale_attr_pairs_json};
const saleAttrInput = document.querySelector('input[name="sale_attr_id"]');
const specNameInput = document.getElementById('spec_name');
if (specNameInput && saleAttrInput) {{
  specNameInput.addEventListener('input', () => {{
    const picked = saleAttrPairs.find(item => item.name === specNameInput.value);
    if (picked) saleAttrInput.value = picked.id;
  }});
}}
function addSkuRow() {{
  const box = document.getElementById('skuRows');
  const row = box.children[0].cloneNode(true);
  const rowId = String(skuNextId++);
  row.querySelector('input[name="sku_row_id"]').value = rowId;
  row.querySelectorAll('input').forEach(input => {{
    if (input.type === 'hidden') return;
    input.value = '';
    if (input.type === 'file') input.name = 'sku_image_file_' + rowId;
  }});
  box.appendChild(row);
}}
function removeSkuRow(button) {{
  const box = document.getElementById('skuRows');
  if (box.children.length > 1) button.parentElement.remove();
}}
const singleForm = document.getElementById('singleProductForm');
const aiButton = document.getElementById('aiSuggestButton');
const aiStatus = document.getElementById('aiSuggestStatus');
function setAiStatus(message, kind = 'info') {{
  if (!aiStatus) return;
  aiStatus.className = 'alert alert-' + kind + ' wide';
  aiStatus.textContent = message;
}}
function findOptionByText(select, valueName) {{
  const target = String(valueName || '').trim().toLowerCase();
  if (!target) return '';
  for (const option of select.options) {{
    const text = option.textContent.trim().toLowerCase();
    if (text === target || text.includes(target) || target.includes(text.split('/')[0].trim())) {{
      return option.value;
    }}
  }}
  return '';
}}
function applyAiSuggestion(suggestion) {{
  if (!suggestion) return;
  const notes = document.getElementById('notes');
  if (notes && suggestion.description_html) notes.value = suggestion.description_html;
  let filled = 0;
  for (const attr of (suggestion.attributes || [])) {{
    const attrId = attr.attrId;
    const select = singleForm.querySelector(`[name="attr_${{CSS.escape(attrId)}}"]`);
    const custom = singleForm.querySelector(`[name="attr_custom_${{CSS.escape(attrId)}}"]`);
    if (select) {{
      const optionValue = attr.valueId || findOptionByText(select, attr.valueName);
      if (optionValue) {{
        select.value = optionValue;
        filled += 1;
        continue;
      }}
    }}
    if (custom && attr.valueName) {{
      custom.value = attr.valueName;
      filled += 1;
    }}
  }}
  const warnings = (suggestion.warnings || []).filter(Boolean);
  const suffix = warnings.length ? ' 提醒：' + warnings.join('；') : '';
  const applied = document.getElementById('ai_suggest_applied');
  if (applied) applied.value = '1';
  setAiStatus(`AI 已生成英文描述，并填入 ${{filled}} 个可识别属性。${{suffix}}`, 'success');
}}
if (singleForm && aiButton) {{
  aiButton.addEventListener('click', async () => {{
    const title = document.getElementById('title');
    const imageInputs = Array.from(singleForm.querySelectorAll('input[name="image_upload"]'));
    if (!title || !title.value.trim()) {{
      setAiStatus('请先填写英文标题，再让 AI 生成建议。', 'error');
      return;
    }}
    const hasImages = imageInputs.some(input => input.files && input.files.length);
    if (!hasImages) {{
      setAiStatus('请先上传产品图片文件夹、多张图片或图片 ZIP，AI 才能识别。', 'error');
      return;
    }}
    aiButton.disabled = true;
    const oldText = aiButton.textContent;
    aiButton.textContent = aiButton.dataset.workingLabel || '处理中...';
    setAiStatus('AI 正在读取标题和图片，请稍等。', 'info');
    try {{
      const response = await fetch('/single/ai-suggest', {{ method: 'POST', body: new FormData(singleForm) }});
      const payload = await response.json();
      if (!response.ok || !payload.ok) throw new Error(payload.error || 'AI 生成失败');
      applyAiSuggestion(payload.suggestion);
    }} catch (error) {{
      setAiStatus(error.message || String(error), 'error');
    }} finally {{
      aiButton.disabled = false;
      aiButton.textContent = oldText;
    }}
  }});
}}
</script>"""

    body = f"{top_nav('single')}{metadata_form}{product_form}"
    return render_page("单产品智能上传", body, header_right=account_menu(account_count))
