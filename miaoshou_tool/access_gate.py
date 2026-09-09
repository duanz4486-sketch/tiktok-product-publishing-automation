from __future__ import annotations

import hashlib
import hmac
import os
import time
from http.cookies import SimpleCookie
from pathlib import Path

from .rendering import escape as e


COOKIE_NAME = "miaoshou_access"
MAX_AGE_SECONDS = 12 * 60 * 60


def _env_file_values(root: Path) -> dict[str, str]:
    env_path = root / ".env"
    if not env_path.exists():
        return {}
    values: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        values[name.strip()] = value.strip().strip("\"'")
    return values


def _setting(root: Path, name: str) -> str:
    return (os.getenv(name) or _env_file_values(root).get(name) or "").strip()


def settings(root: Path) -> tuple[str, str]:
    return _setting(root, "WEB_ACCESS_PASSWORD"), _setting(root, "WEB_SESSION_SECRET")


def is_enabled(root: Path) -> bool:
    password, secret = settings(root)
    return bool(password and secret)


def is_misconfigured(root: Path) -> bool:
    password, secret = settings(root)
    return bool(password or secret) and not bool(password and secret)


def _signature(timestamp: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), timestamp.encode("utf-8"), hashlib.sha256).hexdigest()


def make_token(secret: str) -> str:
    timestamp = str(int(time.time()))
    return f"{timestamp}.{_signature(timestamp, secret)}"


def valid_token(token: str, secret: str, max_age_seconds: int = MAX_AGE_SECONDS) -> bool:
    try:
        timestamp, signature = token.split(".", 1)
        issued_at = int(timestamp)
    except ValueError:
        return False
    if time.time() - issued_at > max_age_seconds:
        return False
    expected = _signature(timestamp, secret)
    return hmac.compare_digest(signature, expected)


def valid_request(cookie_header: str, root: Path) -> bool:
    password, secret = settings(root)
    if not password or not secret:
        return not password and not secret
    cookies = SimpleCookie()
    cookies.load(cookie_header or "")
    morsel = cookies.get(COOKIE_NAME)
    return bool(morsel and valid_token(morsel.value, secret))


def login_cookie(root: Path) -> str:
    _password, secret = settings(root)
    return f"{COOKIE_NAME}={make_token(secret)}; Path=/; Max-Age={MAX_AGE_SECONDS}; HttpOnly; SameSite=Lax"


def logout_cookie() -> str:
    return f"{COOKIE_NAME}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"


def password_matches(candidate: str, root: Path) -> bool:
    password, _secret = settings(root)
    return bool(password) and hmac.compare_digest(candidate, password)


def render_login(error: str = "") -> bytes:
    error_html = f'<div class="error">{e(error)}</div>' if error else ""
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>访问验证</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      background: #f4f7fa;
      color: #13202c;
      font-family: "Microsoft YaHei", "Segoe UI", Arial, sans-serif;
    }}
    main {{
      width: min(440px, calc(100vw - 32px));
      padding: 28px;
      background: #fff;
      border: 1px solid #d7e0e8;
      border-radius: 10px;
      box-shadow: 0 18px 48px rgba(19, 32, 44, .08);
    }}
    h1 {{ margin: 0 0 8px; font-size: 22px; }}
    p {{ margin: 0 0 20px; color: #5d6b78; line-height: 1.6; }}
    label {{ display: block; margin-bottom: 8px; color: #405160; font-size: 14px; }}
    input {{
      width: 100%;
      min-height: 42px;
      border: 1px solid #b8c6d3;
      border-radius: 6px;
      padding: 8px 10px;
      font: inherit;
    }}
    button {{
      width: 100%;
      min-height: 42px;
      margin-top: 16px;
      border: 0;
      border-radius: 6px;
      background: #165dff;
      color: #fff;
      font-weight: 700;
      cursor: pointer;
    }}
    .error {{
      margin-bottom: 14px;
      padding: 10px 12px;
      border: 1px solid #ffccc7;
      border-radius: 6px;
      background: #fff2f0;
      color: #b42318;
    }}
  </style>
</head>
<body>
  <main>
    <h1>访问验证</h1>
    <p>请输入站点访问密码。这个密码只用于保护网页入口，不是妙手账号密码。</p>
    {error_html}
    <form method="post" action="/access-login">
      <label for="password">访问密码</label>
      <input id="password" name="password" type="password" autocomplete="current-password" required autofocus>
      <button type="submit">进入系统</button>
    </form>
  </main>
</body>
</html>""".encode("utf-8")
