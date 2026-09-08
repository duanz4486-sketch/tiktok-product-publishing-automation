from __future__ import annotations

import base64
import cgi
import mimetypes
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from .config import AI_SETTINGS_PATH, MIN_AI_DESCRIPTION_CHARS, SINGLE_IMAGE_LIMIT
from .json_io import dumps, loads, read, write
from .miaoshou_api import attr_label, is_required_attr, metadata_attrs, truthy_flag

FieldTextFunc = Callable[[cgi.FieldStorage, str, str], str]

AI_PROVIDER_PRESETS = {
    "deepseek": {
        "label": "DeepSeek",
        "model": "deepseek-v4-flash-vision-exp",
        "base_url": "https://api.deepseek.com/chat/completions",
        "env": "DEEPSEEK_API_KEY",
        "help": "适合当前流程，已支持 OpenAI 兼容和图片输入。",
    },
    "openai": {
        "label": "OpenAI",
        "model": "gpt-4.1-mini",
        "base_url": "https://api.openai.com/v1/chat/completions",
        "env": "OPENAI_API_KEY",
        "help": "需要服务器能访问 OpenAI，并选择支持图片识别的模型。",
    },
    "dashscope": {
        "label": "阿里云百炼 / 通义千问",
        "model": "qwen-vl-max",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        "env": "DASHSCOPE_API_KEY",
        "help": "API Key 必须和接口地域匹配；如使用专属工作空间，请改接口地址。",
    },
    "volcengine": {
        "label": "火山方舟 / 豆包",
        "model": "doubao-1.5-vision-pro-32k",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
        "env": "ARK_API_KEY",
        "help": "通常需要填写火山方舟实际模型名或推理接入点 ID。",
    },
    "custom": {
        "label": "自定义 OpenAI 兼容接口",
        "model": "",
        "base_url": "",
        "env": "AI_API_KEY",
        "help": "用于第三方中转或其他兼容服务，需自行填写接口地址和模型名。",
    },
}

BANNED_AI_DESCRIPTION_PATTERNS = [
    (re.compile(r"\bkids?\b", re.I), "kid/kids"),
    (re.compile(r"\bchild(?:ren)?\b", re.I), "child/children"),
    (re.compile(r"\bbab(?:y|ies)\b", re.I), "baby/babies"),
    (re.compile(r"\binfants?\b", re.I), "infant/infants"),
    (re.compile(r"\btoddlers?\b", re.I), "toddler/toddlers"),
    (re.compile(r"\bnewborns?\b", re.I), "newborn/newborns"),
    (re.compile(r"\bteens?\b", re.I), "teen/teens"),
    (re.compile(r"\bpets?\b", re.I), "pet/pets"),
]


def contains_cjk(value: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", value or ""))


def require_english(value: str, label: str) -> None:
    if contains_cjk(value):
        raise ValueError(f"{label}需要填写英文，不能包含中文")


def require_ai_description_policy(value: str) -> None:
    text = re.sub(r"<[^>]+>", " ", value or "")
    banned = [label for pattern, label in BANNED_AI_DESCRIPTION_PATTERNS if pattern.search(text)]
    if banned:
        raise RuntimeError("AI 英文详情描述包含禁用词：" + "、".join(banned))


def load_ai_settings(load_env: Callable[[], None]) -> dict[str, Any]:
    load_env()
    settings = read(AI_SETTINGS_PATH, {}) or {}
    provider_key = str(settings.get("provider_key") or "").strip().lower()
    if not provider_key:
        provider_text = str(settings.get("provider") or "DeepSeek").strip().lower()
        if "deepseek" in provider_text:
            provider_key = "deepseek"
        elif "openai" in provider_text:
            provider_key = "openai"
        elif "dashscope" in provider_text or "通义" in provider_text or "百炼" in provider_text or "qwen" in provider_text:
            provider_key = "dashscope"
        elif "volc" in provider_text or "火山" in provider_text or "豆包" in provider_text:
            provider_key = "volcengine"
        else:
            provider_key = "custom"
    if provider_key not in AI_PROVIDER_PRESETS:
        provider_key = "custom"
    preset = AI_PROVIDER_PRESETS[provider_key]
    settings["provider_key"] = provider_key
    settings["provider"] = preset["label"]
    settings.setdefault("model", preset["model"])
    settings.setdefault("language", "zh-CN")
    settings.setdefault("base_url", preset["base_url"])
    if str(settings.get("model") or "").lower() == "deepseek-v4-flash-vision-exp":
        settings["model"] = "deepseek-v4-flash-vision-exp"
    if not settings.get("api_key"):
        settings["api_key"] = os.getenv(preset["env"], "").strip() or os.getenv("AI_API_KEY", "").strip()
    return settings


def save_ai_settings(settings: dict[str, Any], load_current: Callable[[], dict[str, Any]]) -> None:
    current = load_current()
    settings = dict(settings)
    api_key = settings.pop("api_key", "")
    provider_key = str(settings.get("provider_key") or current.get("provider_key") or "deepseek").strip().lower()
    if provider_key not in AI_PROVIDER_PRESETS:
        provider_key = "custom"
    settings["provider_key"] = provider_key
    settings["provider"] = AI_PROVIDER_PRESETS[provider_key]["label"]
    if api_key:
        current["api_key"] = api_key
    elif provider_key != current.get("provider_key"):
        current["api_key"] = ""
    current.update(settings)
    write(AI_SETTINGS_PATH, current)


def image_data_url(file_path: Path) -> str:
    content_type = mimetypes.guess_type(file_path.name)[0] or "image/jpeg"
    data = base64.b64encode(file_path.read_bytes()).decode("ascii")
    return f"data:{content_type};base64,{data}"


def attr_prompt_rows(attrs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for attr in attrs:
        attr_id = str(attr.get("attrId") or "")
        if not attr_id:
            continue
        rows.append(
            {
                "attrId": attr_id,
                "label": attr_label(attr),
                "required": is_required_attr(attr),
                "options": [
                    {
                        "id": str(item.get("id") or ""),
                        "name": str(item.get("name") or item.get("valueNameAlias") or ""),
                    }
                    for item in (attr.get("values") or [])[:80]
                    if isinstance(item, dict)
                ],
                "customAllowed": truthy_flag(attr.get("isCustomized")) or not attr.get("values"),
            }
        )
    return rows


def ai_suggestion_prompt(title: str, notes: str, metadata: dict[str, Any]) -> str:
    attrs = attr_prompt_rows(metadata_attrs(metadata, "categoryProductAttrList"))
    return (
        "你是跨境电商 TikTok 商品资料助手。页面提示用中文，但输出到妙手的内容必须是英文。\n"
        "请根据用户标题、用户描述和产品图片生成可确认的商品建议。\n"
        "严格规则：\n"
        "1. 只能填写图片或标题/描述中能明确判断的信息；材质、防滑、机洗、克重、认证等不能确定就留空。\n"
        "2. 不要编造品牌、认证、安全承诺、功能或材质。\n"
        "3. description_html 严禁出现 kid、kids、child、children、baby、babies、infant、toddler、newborn、teen、teens、pet、pets；boy、girl、teenager、animal 可以使用。\n"
        f"4. description_html 必须是英文 HTML；去掉 HTML 标签后至少 {MIN_AI_DESCRIPTION_CHARS} 个英文字符，分成 4-6 个 <p> 段落。\n"
        "5. attributes 只返回能确定的属性。能匹配 options 时返回 valueId；不能匹配但允许自定义时返回英文 valueName。\n"
        "6. 只返回 JSON，不要 Markdown，不要解释。\n\n"
        "JSON 格式："
        '{"description_html":"<p>English description</p>","attributes":[{"attrId":"...","valueId":"...","valueName":"...","reason":"中文依据"}],"warnings":["中文提醒"]}\n\n'
        f"用户标题：{title}\n"
        f"用户描述：{notes or '未填写'}\n"
        "类目属性清单：\n"
        f"{dumps(attrs[:80], compact=True)}"
    )


def extract_json_object(text: str) -> dict[str, Any]:
    content = text.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("AI 没有返回可解析的 JSON")
    return loads(content[start : end + 1])


def ai_provider_label(settings: dict[str, Any]) -> str:
    key = str(settings.get("provider_key") or "").strip().lower()
    if key in AI_PROVIDER_PRESETS:
        return AI_PROVIDER_PRESETS[key]["label"]
    return str(settings.get("provider") or "OpenAI 兼容接口").strip() or "OpenAI 兼容接口"


def normalize_chat_completions_url(base_url: str) -> str:
    url = str(base_url or "").strip()
    if not url:
        return ""
    return url.rstrip("/") if url.rstrip("/").endswith("/chat/completions") else url.rstrip("/") + "/chat/completions"


def call_openai_compatible_chat(
    settings: dict[str, Any],
    content: list[dict[str, Any]],
    timeout: int = 90,
    urlopen: Callable[..., Any] = urllib.request.urlopen,
) -> str:
    provider = ai_provider_label(settings)
    api_key = str(settings.get("api_key") or "").strip()
    if not api_key:
        raise RuntimeError(f"还没有配置 {provider} API Key，请先到 AI 设置页面保存。")
    model = str(settings.get("model") or "").strip()
    if not model:
        raise RuntimeError(f"{provider} 模型名称为空，请到 AI 设置页面填写支持图片识别的模型。")
    base_url = normalize_chat_completions_url(str(settings.get("base_url") or ""))
    if not base_url:
        raise RuntimeError(f"{provider} 接口地址为空，请到 AI 设置页面填写 Chat Completions 地址。")
    body = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        base_url,
        data=dumps(body, compact=True).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"AI 服务 HTTP {exc.code}（{provider}）: {detail[:300]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"AI 服务网络请求失败（{provider}）: {exc.reason}") from exc
    data = loads(payload)
    message = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
    if not message:
        raise RuntimeError(f"AI 服务没有返回建议内容（{provider}）: {payload[:300]}")
    return message


def call_ai(
    title: str,
    notes: str,
    image_files: list[Path],
    metadata: dict[str, Any],
    settings: dict[str, Any],
    chat: Callable[[dict[str, Any], list[dict[str, Any]], int], str],
) -> dict[str, Any]:
    content: list[dict[str, Any]] = [{"type": "text", "text": ai_suggestion_prompt(title, notes, metadata)}]
    for file_path in image_files[: min(3, SINGLE_IMAGE_LIMIT)]:
        content.append({"type": "image_url", "image_url": {"url": image_data_url(file_path), "detail": "low"}})
    suggestion = extract_json_object(chat(settings, content, 90))
    description = str(suggestion.get("description_html") or "").strip()
    if description:
        require_english(description, "AI 英文详情描述")
        require_ai_description_policy(description)
        if len(re.sub(r"<[^>]+>", " ", description)) < MIN_AI_DESCRIPTION_CHARS:
            raise RuntimeError(f"AI 英文详情描述少于 {MIN_AI_DESCRIPTION_CHARS} 字符，请重新生成。")
    cleaned_attrs: list[dict[str, str]] = []
    known_attrs = {str(attr.get("attrId") or ""): attr for attr in metadata_attrs(metadata, "categoryProductAttrList")}
    for item in suggestion.get("attributes") or []:
        if not isinstance(item, dict):
            continue
        attr_id = str(item.get("attrId") or "").strip()
        if attr_id not in known_attrs:
            continue
        value_id = str(item.get("valueId") or "").strip()
        value_name = str(item.get("valueName") or "").strip()
        if not value_id and value_name:
            require_english(value_name, attr_label(known_attrs[attr_id]))
        if value_id or value_name:
            cleaned_attrs.append(
                {
                    "attrId": attr_id,
                    "valueId": value_id,
                    "valueName": value_name,
                    "reason": str(item.get("reason") or "").strip(),
                }
            )
    return {
        "description_html": description,
        "attributes": cleaned_attrs,
        "warnings": [str(item) for item in (suggestion.get("warnings") or []) if str(item).strip()],
    }


def test_ai_settings(
    settings: dict[str, Any],
    chat: Callable[[dict[str, Any], list[dict[str, Any]], int], str],
) -> None:
    png_data_url = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
    )
    content = [
        {
            "type": "text",
            "text": '请确认你能读取图片并严格只返回 JSON：{"ok":true,"summary":"short English image summary"}',
        },
        {"type": "image_url", "image_url": {"url": png_data_url, "detail": "low"}},
    ]
    result = extract_json_object(chat(settings, content, 45))
    if not result.get("ok"):
        raise RuntimeError("AI 测试没有返回 ok=true，请检查模型是否支持图片识别和 JSON 输出。")


def ai_settings_from_form(form: cgi.FieldStorage, field_text: FieldTextFunc) -> dict[str, Any]:
    provider_key = field_text(form, "provider_key", "deepseek").lower()
    if provider_key not in AI_PROVIDER_PRESETS:
        provider_key = "custom"
    preset = AI_PROVIDER_PRESETS[provider_key]
    return {
        "provider_key": provider_key,
        "provider": preset["label"],
        "model": field_text(form, "model", preset["model"]),
        "base_url": field_text(form, "base_url", preset["base_url"]),
        "language": "zh-CN",
        "api_key": field_text(form, "api_key"),
    }


def settings_for_ai_test(posted: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    if not posted.get("api_key") and posted.get("provider_key") == current.get("provider_key"):
        posted = dict(posted)
        posted["api_key"] = current.get("api_key", "")
    return posted


def ai_configured(settings: dict[str, Any]) -> bool:
    return bool(str(settings.get("api_key") or "").strip())


def merge_ai_attributes(product_attrs: list[dict[str, Any]], suggestion_attrs: list[dict[str, Any]], metadata: dict[str, Any]) -> list[dict[str, Any]]:
    result = list(product_attrs)
    existing_ids = {str(item.get("attributeId") or "") for item in result}
    metadata_by_id = {str(attr.get("attrId") or ""): attr for attr in metadata_attrs(metadata, "categoryProductAttrList")}
    for item in suggestion_attrs:
        attr_id = str(item.get("attrId") or "").strip()
        if not attr_id or attr_id in existing_ids or attr_id not in metadata_by_id:
            continue
        attr = metadata_by_id[attr_id]
        value_id = str(item.get("valueId") or "").strip()
        value_name = str(item.get("valueName") or "").strip()
        if value_id:
            for option in attr.get("values") or []:
                if str(option.get("id") or "") == value_id:
                    value_name = str(option.get("name") or option.get("valueNameAlias") or value_name or value_id)
                    break
        if not value_name:
            continue
        require_english(value_name, attr_label(attr))
        result.append(
            {
                "attributeId": attr_id,
                "attributeName": str(attr.get("name") or attr.get("attributeName") or ""),
                "attributeNameAlias": str(attr.get("attributeNameAlias") or ""),
                "attributeValues": [{"valueName": value_name, "valueId": value_id}],
            }
        )
        existing_ids.add(attr_id)
    return result
