from __future__ import annotations


def readable_error_text(error: object) -> str:
    text = str(error or "").strip()
    if not text:
        return ""
    if "缺少图片文件夹" in text:
        return "缺少图片文件夹：检查 ZIP 里是否有对应序号的子文件夹。"
    if "缺少标题" in text:
        return "缺少标题：检查 Excel 里是否有这个序号和标题。"
    if "FileNotFoundError" in text:
        return "本地文件缺失：请重新上传本次 Excel 和图片 ZIP。"
    if "HTTPError 404" in text or "Not Found" in text:
        return "图片链接无法读取：确认本次图片已上传到 OSS，或开启自动上传。"
    if "SignatureDoesNotMatch" in text or "AccessDenied" in text:
        return "OSS 上传权限失败：检查 AccessKey、Bucket 权限和地区配置。"
    if "appNotFound" in text:
        return "妙手应用不存在或未启用：检查 App Key/App Secret 是否对应当前妙手账号。"
    if "AI 服务 HTTP 401" in text or "AI 服务 HTTP 403" in text or "DeepSeek HTTP 401" in text or "DeepSeek HTTP 403" in text:
        return "AI 认证失败：检查 AI 设置里的 API Key 是否正确、是否有权限调用当前视觉模型。"
    if "AI 服务 HTTP 400" in text or "DeepSeek HTTP 400" in text:
        return "AI 请求参数失败：检查接口地址是否为 Chat Completions，模型是否支持图片识别和 JSON 输出。"
    if "AI 服务 HTTP 404" in text:
        return "AI 接口地址错误：检查 AI 设置里的接口地址是否填对。"
    if "AI 服务 HTTP 402" in text or "AI 服务 HTTP 429" in text:
        return "AI 额度或限流问题：检查余额、套餐、调用频率和模型权限。"
    if "AI 服务网络请求失败" in text or "DeepSeek 网络请求失败" in text:
        return "AI 网络请求失败：检查服务器是否能访问当前 AI 服务接口。"
    if "AI 没有返回可解析的 JSON" in text or "AI 服务没有返回建议内容" in text or "AI 测试没有返回 ok=true" in text:
        return "AI 返回格式不正确：检查模型是否支持 JSON 输出，或换一个视觉模型重试。"
    if "create_common_collect_product" in text:
        return "妙手创建公共采集箱产品接口失败：检查接口权限和妙手接口文档路径。"
    if "查询 TikTok 详情失败" in text:
        return "查询 TikTok 模板失败：检查妙手账号、店铺和模板是否属于同一个账号。"
    if "Miaoshou HTTP" in text:
        return "妙手接口请求失败：" + text[:180]
    return text[:220]


def readable_job_error(job: dict) -> str:
    direct = readable_error_text(job.get("error"))
    if direct:
        return direct
    for item in job.get("results") or []:
        if item.get("status") == "failed" and item.get("error"):
            return readable_error_text(item.get("error"))
    return ""


def ai_status_text(item: dict) -> str:
    ai = item.get("ai") or {}
    if not isinstance(ai, dict):
        return ""
    status = str(ai.get("status") or "")
    if status == "success":
        count = int(ai.get("attributeCount") or 0)
        desc = str(ai.get("description") or "")
        return f"成功，属性建议 {count} 个，描述{desc}"
    if status == "failed":
        return "失败：" + readable_error_text(ai.get("error"))
    if status == "skipped":
        return "未启用：" + str(ai.get("reason") or "")
    return status
