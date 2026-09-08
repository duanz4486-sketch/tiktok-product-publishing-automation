# TikTok 产品发布自动化

这是一个面向跨境电商团队的妙手 TikTok 批量上货工具。当前稳定入口是「模板批量上传」：用已经在妙手里保存好的产品参数模板，批量替换每个产品的标题和图片，再保存到 TikTok 采集箱。

> 单产品 / 单个链接智能上传入口仍在开发和完善中，当前公开说明先不把它作为正式可用流程。

## 当前稳定能力

- 通过网页上传标题 Excel 和图片 ZIP / 图片文件夹。
- 按 Excel 里的「序号」和图片子文件夹名称匹配产品。
- 自动忽略 `Thumbs.db` 等无用文件。
- 可把本次上传的图片写入 OSS，同名对象会按本次上传内容覆盖。
- 调用妙手 OpenAPI 创建公共采集箱产品、认领到 TikTok 采集箱，并套用保存好的模板参数。
- 支持三个模板类型：`大地毯`、`非定制毛毯`、`定制毛毯`。
- 生成本地任务结果和失败日志。

## 不适合的场景

- 还不建议直接用于完全不同类目、不同参数的全自动上货。
- 还不建议开放给陌生公网用户使用。
- 当前默认面向 TikTok 美国站。

## 目录

- [配置说明](docs/configuration.md)
- [模板批量上传使用说明](docs/template-batch-upload.md)
- [部署说明](docs/deployment.md)
- [常见问题](docs/troubleshooting.md)
- [公开发布前检查清单](docs/release-checklist.md)
- [Codex Skill 说明](SKILL.md)

## 快速开始

1. 安装 Python 3.10 或更新版本。
2. 安装依赖：

```bash
python -m pip install -r requirements.txt
```

3. 复制示例配置：

```bash
copy .env.example .env
copy accounts.example.json accounts.json
```

4. 按 [配置说明](docs/configuration.md) 填写 OSS 和妙手账号信息。
5. 启动网页：

```bash
python web_app.py --host 127.0.0.1 --port 8002
```

Windows 也可以直接运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_local.ps1
```

6. 浏览器打开：

```text
http://127.0.0.1:8002/
```

7. 先打开「系统自检」，确认没有红色失败项，再使用「模板批量上传」。

也可以在命令行运行自检：

```bash
python scripts/check_setup.py
```

服务器部署时请参考 [部署说明](docs/deployment.md)。

## 安全提醒

不要把这些文件提交到 GitHub：

- `.env`
- `accounts.json`
- `ai_settings.json`
- `runs/`
- `uploads/`
- `app.log`
- `app.err`

仓库里的 `.gitignore` 已经默认排除了这些文件。公开仓库只应提交示例配置和代码。
