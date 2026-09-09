from __future__ import annotations

from .rendering import escape as e


def render_page(title: str, body: str, refresh: bool = False, header_right: str = "") -> bytes:
    meta = '<meta http-equiv="refresh" content="3">' if refresh else ""
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  {meta}
  <title>{e(title)}</title>
  <style>
    :root {{
      --ink: #17212b;
      --muted: #627180;
      --line: #d9e1e8;
      --paper: #f7f9fb;
      --panel: #ffffff;
      --blue: #1f64d8;
      --green: #18745a;
      --red: #b42318;
      --amber: #946200;
      --focus: #00a2a8;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Microsoft YaHei", "Segoe UI", Arial, sans-serif;
      color: var(--ink);
      background: var(--paper);
    }}
    header {{
      padding: 22px 32px;
      background: #fff;
      border-bottom: 1px solid var(--line);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
    }}
    h1 {{ margin: 0; font-size: 22px; font-weight: 700; }}
    main {{ max-width: 1080px; margin: 0 auto; padding: 24px; }}
    section {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 20px;
      margin-bottom: 16px;
    }}
    h2 {{ margin: 0 0 16px; font-size: 17px; }}
    fieldset {{ border: 0; margin: 0; padding: 0; }}
    fieldset:disabled {{ opacity: .55; }}
    label {{ display: block; color: var(--muted); font-size: 13px; margin-bottom: 6px; }}
    input, select, textarea {{
      width: 100%;
      min-height: 40px;
      border: 1px solid #b9c5d0;
      border-radius: 6px;
      padding: 8px 10px;
      background: #fff;
      color: var(--ink);
      font: inherit;
    }}
    textarea {{ min-height: 120px; resize: vertical; line-height: 1.5; }}
    input:focus, select:focus, textarea:focus, button:focus {{ outline: 2px solid var(--focus); outline-offset: 2px; }}
    .grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }}
    .grid-three {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }}
    .wide {{ grid-column: 1 / -1; }}
    .row {{ display: flex; align-items: center; gap: 10px; }}
    .row input[type="checkbox"] {{ width: 18px; min-height: 18px; }}
    .inline-form {{ display: grid; grid-template-columns: minmax(140px, 1fr) 120px auto; gap: 8px; align-items: center; }}
    .account-edit-form {{ display: grid; grid-template-columns: repeat(2, minmax(160px, 1fr)); gap: 10px; align-items: end; min-width: 560px; }}
    .account-edit-form .actions-row {{ grid-column: 1 / -1; display: flex; gap: 8px; }}
    .inline-form button {{ min-height: 40px; }}
    .danger {{ background: #fff1f0; color: var(--red); border: 1px solid #f3b4ad; }}
    .account-actions {{ display: grid; gap: 8px; }}
    .lock-switch {{
      min-height: 38px;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      background: #fff;
      color: var(--ink);
      border: 1px solid var(--line);
      font-weight: 600;
    }}
    .lock-track {{
      width: 42px;
      height: 22px;
      border-radius: 999px;
      background: #8a98a8;
      position: relative;
      transition: background .22s ease;
    }}
    .lock-track::after {{
      content: "";
      width: 18px;
      height: 18px;
      border-radius: 50%;
      background: #fff;
      position: absolute;
      left: 2px;
      top: 2px;
      box-shadow: 0 1px 3px rgba(23, 33, 43, .25);
      transition: transform .22s ease;
    }}
    .lock-switch.locked .lock-track {{ background: var(--green); }}
    .lock-switch.locked .lock-track::after {{ transform: translateX(20px); }}
    input[readonly] {{ background: #f2f5f8; color: var(--muted); }}
    .hint {{ color: var(--muted); font-size: 13px; line-height: 1.6; }}
    button {{
      min-height: 42px;
      border: 0;
      border-radius: 6px;
      padding: 0 18px;
      background: var(--blue);
      color: white;
      font-weight: 700;
      cursor: pointer;
    }}
    button:disabled {{ background: #8a98a8; cursor: not-allowed; }}
    .ghost {{ background: #eef3f7; color: var(--ink); border: 1px solid var(--line); }}
    .account {{ position: relative; }}
    .account summary {{ list-style: none; cursor: pointer; }}
    .account summary::-webkit-details-marker {{ display: none; }}
    .avatar {{
      width: 42px;
      height: 42px;
      border-radius: 50%;
      display: grid;
      place-items: center;
      background: #1f64d8;
      color: #fff;
      font-weight: 700;
      box-shadow: 0 2px 8px rgba(31, 100, 216, .22);
    }}
    .account-panel {{
      position: absolute;
      right: 0;
      top: 52px;
      width: 260px;
      padding: 16px;
      background: #fff;
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: 0 12px 32px rgba(23, 33, 43, .14);
      z-index: 10;
    }}
    .account-name {{ margin: 0 0 4px; font-weight: 700; }}
    .account-meta {{ margin: 0 0 14px; color: var(--muted); font-size: 13px; }}
    .account-link {{ display: block; margin: 0 0 12px; }}
    .notice {{ border-left: 4px solid var(--amber); padding-left: 12px; }}
    .progress {{ height: 14px; border: 1px solid var(--line); border-radius: 999px; background: #eef3f7; overflow: hidden; }}
    .bar {{ height: 100%; background: linear-gradient(90deg, var(--blue), var(--focus)); transition: width .2s ease; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ padding: 10px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }}
    th {{ color: var(--muted); font-weight: 600; }}
    a {{ color: var(--blue); text-decoration: none; }}
    .status {{ font-weight: 700; }}
    .done, .dry_run_ok, .success {{ color: var(--green); }}
    .failed, .done_with_errors {{ color: var(--red); }}
    .running, .started, .uploading {{ color: var(--amber); }}
    .actions {{ margin-top: 16px; }}
    .top-nav {{ display: flex; gap: 10px; margin-bottom: 16px; }}
    .top-nav a {{ padding: 10px 12px; border: 1px solid var(--line); border-radius: 6px; background: #fff; }}
    .required-mark {{ color: var(--red); font-weight: 700; }}
    .mini-button {{ min-height: 34px; padding: 0 12px; }}
    .shop-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px 14px; }}
    .shop-grid label {{ display: flex; align-items: center; gap: 8px; color: var(--ink); }}
    .shop-grid input {{ width: 18px; min-height: 18px; }}
    .sku-row {{ display: grid; grid-template-columns: 1.4fr .8fr .8fr 1.4fr auto; gap: 8px; align-items: end; margin-bottom: 8px; }}
    .category-picker {{
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      overflow-x: auto;
      margin-top: 10px;
    }}
    .category-columns {{ display: grid; grid-auto-flow: column; grid-auto-columns: minmax(220px, 1fr); min-height: 220px; }}
    .category-column {{ border-right: 1px solid var(--line); padding: 8px; max-height: 260px; overflow-y: auto; }}
    .category-column:last-child {{ border-right: 0; }}
    .category-item {{
      width: 100%;
      min-height: 34px;
      padding: 6px 8px;
      border: 0;
      border-radius: 4px;
      background: transparent;
      color: var(--ink);
      text-align: left;
      font-weight: 500;
    }}
    .category-item:hover, .category-item.active {{ background: #e8f2ff; color: var(--blue); }}
    .category-item.leaf::before {{ content: "✓ "; color: var(--focus); }}
    @media (max-width: 720px) {{
      header {{ padding: 18px; }}
      main {{ padding: 14px; }}
      .grid, .grid-three, .shop-grid, .sku-row {{ grid-template-columns: 1fr; }}
      table {{ display: block; overflow-x: auto; }}
    }}
    :root {{
      --bg: #f4f7fa;
      --surface: #ffffff;
      --surface-2: #f8fafc;
      --text: #13202c;
      --text-soft: #5d6b78;
      --border: #d7e0e8;
      --border-strong: #b8c6d3;
      --accent: #165dff;
      --accent-strong: #1048c5;
      --accent-soft: #eaf1ff;
      --ok: #0f7a5a;
      --ok-soft: #e9f7f1;
      --warn: #9a6400;
      --warn-soft: #fff6df;
      --bad: #b42318;
      --bad-soft: #fff0ed;
      --shadow-sm: 0 1px 2px rgba(16, 32, 48, .06);
      --shadow-md: 0 16px 42px rgba(16, 32, 48, .12);
    }}
    body {{ background: var(--bg); color: var(--text); font-size: 14px; }}
    header.app-header {{
      position: sticky;
      top: 0;
      z-index: 20;
      padding: 14px 28px;
      background: rgba(255, 255, 255, .96);
      backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--border);
    }}
    .brand {{ display: flex; align-items: center; gap: 12px; min-width: 260px; }}
    .brand-mark {{
      width: 38px;
      height: 38px;
      border-radius: 10px;
      display: grid;
      place-items: center;
      background: #102033;
      color: #fff;
      font-weight: 800;
      letter-spacing: 0;
    }}
    .brand-title {{ display: block; font-size: 18px; line-height: 1.2; }}
    .brand-subtitle {{ display: block; margin-top: 2px; color: var(--text-soft); font-size: 12px; font-weight: 500; }}
    main {{ max-width: 1180px; padding: 24px; }}
    section {{
      border-color: var(--border);
      border-radius: 10px;
      box-shadow: var(--shadow-sm);
    }}
    section h2 {{ font-size: 18px; letter-spacing: 0; }}
    .section-head {{ display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; margin-bottom: 16px; }}
    .section-head h2 {{ margin-bottom: 4px; }}
    .section-kicker {{ margin: 0; color: var(--text-soft); font-size: 13px; line-height: 1.6; }}
    .top-nav {{
      position: sticky;
      top: 67px;
      z-index: 15;
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      padding: 10px 0 14px;
      margin-bottom: 8px;
      background: linear-gradient(var(--bg) 72%, rgba(244, 247, 250, 0));
    }}
    .top-nav a {{
      display: inline-flex;
      align-items: center;
      gap: 7px;
      border-radius: 999px;
      padding: 9px 14px;
      color: var(--text-soft);
      background: var(--surface);
      border-color: var(--border);
      font-weight: 700;
      box-shadow: var(--shadow-sm);
    }}
    .top-nav a.active {{ color: var(--accent); background: var(--accent-soft); border-color: #bad0ff; }}
    .nav-badge {{ padding: 2px 6px; border-radius: 999px; font-size: 11px; line-height: 1.2; font-weight: 800; }}
    .nav-badge.stable {{ color: var(--ok); background: var(--ok-soft); }}
    .nav-badge.beta {{ color: var(--warn); background: var(--warn-soft); }}
    input, select, textarea {{
      border-color: var(--border-strong);
      border-radius: 8px;
      min-height: 42px;
      transition: border-color .16s ease, box-shadow .16s ease, background .16s ease;
    }}
    input:hover, select:hover, textarea:hover {{ border-color: #8797a7; }}
    input:focus, select:focus, textarea:focus, button:focus {{ outline: 3px solid rgba(0, 162, 168, .18); border-color: var(--focus); }}
    label {{ color: #344556; font-weight: 700; }}
    .field-help {{ margin: 6px 0 0; color: var(--text-soft); font-size: 12px; line-height: 1.5; }}
    button {{ border-radius: 8px; background: var(--accent); transition: background .16s ease, transform .16s ease, box-shadow .16s ease; }}
    button:hover:not(:disabled) {{ background: var(--accent-strong); box-shadow: 0 8px 18px rgba(22, 93, 255, .18); transform: translateY(-1px); }}
    .ghost {{ background: #f1f5f9; border-color: var(--border); color: var(--text); }}
    .ghost:hover:not(:disabled) {{ background: #e8eef5; box-shadow: none; }}
    .danger {{ background: var(--bad-soft); color: var(--bad); border-color: #f0b8b1; }}
    .danger:hover:not(:disabled) {{ background: #ffe1dd; box-shadow: none; }}
    .form-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px 16px; }}
    .field-card {{ padding: 12px; border: 1px solid var(--border); border-radius: 9px; background: var(--surface-2); }}
    .upload-choice-row {{ display: flex; align-items: center; flex-wrap: wrap; gap: 10px; margin-top: 8px; }}
    .upload-actions {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 10px; }}
    .upload-button {{ display: inline-flex; align-items: center; justify-content: center; min-height: 38px; padding: 0 14px; border: 1px solid var(--border); border-radius: 8px; background: #fff; color: var(--text); font-weight: 700; cursor: pointer; }}
    .upload-button:hover {{ border-color: var(--accent); color: var(--accent); }}
    .file-choice-name {{ color: var(--text-soft); font-size: 13px; }}
    .hidden-file {{ position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }}
    .check-row {{ display: flex; align-items: flex-start; gap: 10px; padding: 12px; border: 1px solid var(--border); border-radius: 9px; background: var(--surface-2); }}
    .check-row input {{ width: 18px; min-height: 18px; margin-top: 2px; flex: 0 0 auto; }}
    .check-row label {{ margin: 0; color: var(--text); }}
    .alert {{ border: 1px solid var(--border); border-left-width: 4px; border-radius: 8px; padding: 12px 14px; margin: 12px 0; line-height: 1.65; }}
    .alert-info {{ background: #eef6ff; border-color: #bfdcff; color: #183b66; }}
    .alert-warn {{ background: var(--warn-soft); border-color: #f2d288; color: #624100; }}
    .alert-error {{ background: var(--bad-soft); border-color: #f0b8b1; color: var(--bad); }}
    .alert-success {{ background: var(--ok-soft); border-color: #a8dec7; color: var(--ok); }}
    .progress-head {{ display: flex; justify-content: space-between; gap: 12px; margin: 10px 0 6px; color: var(--text-soft); font-size: 13px; }}
    .progress-head strong {{ color: var(--text); }}
    .progress {{ height: 12px; border: 0; background: #e5edf5; }}
    .bar {{ background: linear-gradient(90deg, #165dff, #00a2a8); }}
    .progress-meta {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; color: var(--text-soft); font-size: 12px; }}
    .progress-meta span {{ padding: 3px 8px; border-radius: 999px; background: var(--surface-2); border: 1px solid var(--border); }}
    .badge {{ display: inline-flex; align-items: center; min-height: 24px; padding: 3px 9px; border-radius: 999px; font-weight: 800; font-size: 12px; white-space: nowrap; }}
    .badge.done, .badge.success, .badge.dry_run_ok, .badge.ok {{ color: var(--ok); background: var(--ok-soft); }}
    .badge.running, .badge.started, .badge.uploading, .badge.queued, .badge.warn {{ color: var(--warn); background: var(--warn-soft); }}
    .badge.failed, .badge.done_with_errors, .badge.error {{ color: var(--bad); background: var(--bad-soft); }}
    .table-wrap {{ width: 100%; overflow-x: auto; border: 1px solid var(--border); border-radius: 10px; background: var(--surface); }}
    .table-wrap table {{ min-width: 860px; }}
    th {{ color: #425466; background: #f6f9fc; font-size: 12px; text-transform: none; }}
    td {{ line-height: 1.55; }}
    .error-cell {{ max-width: 360px; word-break: break-word; color: var(--bad); }}
    .empty-row {{ color: var(--text-soft); text-align: center; padding: 20px; }}
    .account summary {{ display: flex; align-items: center; gap: 10px; }}
    .account-summary-text {{ display: grid; gap: 2px; line-height: 1.1; }}
    .account-summary-text strong {{ font-size: 13px; color: var(--text); }}
    .account-summary-text small {{ color: var(--text-soft); font-size: 12px; }}
    .avatar {{ width: 36px; height: 36px; background: #102033; box-shadow: none; }}
    .account-panel {{ width: 286px; border-radius: 12px; box-shadow: var(--shadow-md); }}
    .account-name {{ font-size: 15px; }}
    .account-link {{ padding: 9px 10px; border-radius: 8px; color: var(--text); font-weight: 700; }}
    .account-link:hover {{ background: var(--surface-2); color: var(--accent); }}
    .account-edit-form {{ min-width: 640px; }}
    .template-grid {{ display: grid; grid-template-columns: repeat(3, minmax(150px, 1fr)); gap: 10px; }}
    .template-grid.wide {{ grid-column: 1 / -1; }}
    .lock-switch {{ border-radius: 999px; }}
    .category-picker {{ border-radius: 10px; }}
    .category-column {{ background: var(--surface); }}
    .category-item {{ border-radius: 7px; }}
    .sku-row {{ padding: 10px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface-2); }}
    @media (max-width: 780px) {{
      header.app-header {{ align-items: flex-start; padding: 12px 16px; }}
      .brand {{ min-width: 0; }}
      .brand-title {{ font-size: 16px; }}
      .brand-subtitle {{ display: none; }}
      .account-summary-text {{ display: none; }}
      .top-nav {{ top: 63px; overflow-x: auto; flex-wrap: nowrap; padding-bottom: 10px; }}
      .top-nav a {{ white-space: nowrap; }}
      .section-head {{ display: block; }}
      .form-grid, .grid, .grid-three, .shop-grid, .sku-row, .account-edit-form, .template-grid {{ grid-template-columns: 1fr; min-width: 0; }}
      .account-panel {{ right: -4px; width: min(286px, calc(100vw - 24px)); }}
      .table-wrap table {{ min-width: 760px; }}
    }}
    @media (prefers-reduced-motion: reduce) {{
      *, *::before, *::after {{ transition: none !important; scroll-behavior: auto !important; }}
    }}
  </style>
</head>
<body>
  <header class="app-header">
    <div class="brand">
      <span class="brand-mark">MS</span>
      <h1><span class="brand-title">妙手 TikTok 批量上货工具</span><span class="brand-subtitle">团队运营工作台</span></h1>
    </div>
    {header_right}
  </header>
  <main>{body}</main>
  <script>
    document.querySelectorAll('form[data-submit-lock]').forEach((form) => {{
      form.addEventListener('submit', (event) => {{
        const button = event.submitter || form.querySelector('button[type="submit"]');
        if (button) {{
          button.disabled = true;
          button.textContent = button.dataset.workingLabel || '处理中...';
        }}
      }});
    }});
  </script>
</body>
</html>""".encode("utf-8")
