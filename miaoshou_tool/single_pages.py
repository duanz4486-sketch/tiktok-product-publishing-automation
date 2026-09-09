from __future__ import annotations

from .miaoshou_api import attr_label, is_required_attr
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
