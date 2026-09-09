# Agent 使用说明

这份文档给 Codex、Claude Code 或类似 coding agent 使用。目标是让 agent 清楚知道这个 Skill 对应的网页工具是什么、怎么启动、怎么打开、怎么协助用户完成稳定流程。

## 这个 Skill 是什么

这是「妙手 TikTok 批量上货工具」的操作 Skill。它不是一个远程 SaaS 账号，也不自带可公开使用的网址。agent 应该根据用户当前环境做三件事：

1. 帮第一次使用的人按 `docs/first-time-setup.md` 完成部署和配置。
2. 找到或启动这个仓库里的网页程序。
3. 打开用户自己的本地或服务器网址。
4. 按稳定流程指导用户上传 Excel 和图片，处理结果和错误。

当前稳定能力是「模板批量上传」。单产品智能上传、AI 自动补软参数、不同类目自由上货还在开发和完善中，除非用户明确要求测试，否则不要当作稳定功能介绍。

## Agent 应该怎么调用网站

如果用户已经有网址：

1. 使用用户提供的网址。
2. 如果有浏览器控制工具，打开该网址并检查页面是否能访问。
3. 如果启用了访问密码，让用户在网页里输入，不要让用户把密码发到聊天里。

如果用户在本机运行：

```bash
python -m pip install -r requirements.txt
python scripts/check_setup.py
python web_app.py --host 127.0.0.1 --port 8002
```

然后打开：

```text
http://127.0.0.1:8002/
```

Windows 也可以使用：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_local.ps1
```

如果用户在服务器运行：

1. 先按 `docs/first-time-setup.md` 和 `docs/deployment.md` 部署。
2. 确认云服务器安全组和系统防火墙开放实际端口。
3. 确认 `.env` 里设置了 `WEB_ACCESS_PASSWORD` 和 `WEB_SESSION_SECRET`。
4. 用服务器公网 IP 或用户自己的域名访问。

## 稳定上传流程

1. 打开 `/check` 做系统自检。
2. 打开 `/accounts` 检查妙手账号是否已配置。
3. 回到首页 `/`。
4. 选择妙手账号。
5. 选择产品模板：`大地毯`、`非定制毛毯`、`定制毛毯`。
6. 上传标题 Excel。
7. 上传图片 ZIP 或图片文件夹。
8. 首次运行保留「先预检，不创建产品」。
9. 检查 Excel 序号和图片子文件夹序号是否匹配。
10. 预检通过后再执行真实上传。

## 匹配规则

本工具只按序号匹配。

- Excel 第 `1` 行标题匹配图片子文件夹 `1`。
- Excel 第 `2` 行标题匹配图片子文件夹 `2`。
- 批次名、Excel 文件名、ZIP 文件名、OSS 目录名都不参与匹配。
- Excel 有、图片没有：记录为缺少图片。
- 图片有、Excel 没有：记录为缺少标题。
- 当前上传的 Excel 和图片源永远优先于历史 OSS 内容。

## 安全规则

agent 不能把以下文件内容展示给用户、写入 README、提交到 GitHub，或复制到公开日志：

- `.env`
- `accounts.json`
- `ai_settings.json`
- `runs/`
- `uploads/`
- `data/*.db`
- `app.log`
- `app.err`
- `tunnel*.log`

如果发现这些文件被 Git 跟踪，应先停止发布流程，提醒用户清理后再继续。公开仓库只能包含示例配置，例如 `.env.example`、`accounts.example.json`、`ai_settings.example.json`。

## 常见诊断

网页打不开：

- 本机地址只能在同一台电脑访问。
- 团队访问需要服务器公网 IP、内网穿透，或同一专用网络。
- 检查程序是否运行、端口是否一致、防火墙和安全组是否放行。

Excel 或图片匹配失败：

- 检查 Excel 是否有序号列和标题列。
- 检查图片 ZIP 或文件夹里是否有按序号命名的子文件夹。
- 不要要求 Excel 文件名、ZIP 文件名和批次名一致。

OSS 上传失败：

- 检查 `.env` 里的 `OSS_BUCKET`、`OSS_ENDPOINT`、`OSS_REGION`、`OSS_ACCESS_KEY_ID`、`OSS_ACCESS_KEY_SECRET` 是否存在。
- 确认这些 OSS 配置属于当前部署者自己的阿里云账号，不要沿用公开仓库作者的配置。
- 检查 AccessKey 权限是否有 OSS 写入权限。
- 检查 Bucket、Endpoint、目录配置是否正确。

妙手接口失败：

- 先看网页错误原因。
- 再看本地 `runs/` 里的任务 JSON。
- 常见原因包括 App Key/App Secret 错误、账号不匹配、模板 ID 失效、店铺/仓库/类目参数缺失。

## 发布前检查

公开 GitHub 前运行：

```bash
python scripts/check_public_release.py
python scripts/check_setup.py
python test_web_app.py
```

`check_public_release.py` 必须通过后再公开仓库。
