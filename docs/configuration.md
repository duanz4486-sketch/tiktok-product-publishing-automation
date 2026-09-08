# 配置说明

本项目的真实密钥只保存在本机或服务器，不应该进入 GitHub。

## 必需文件

首次部署时复制示例文件：

```bash
copy .env.example .env
copy accounts.example.json accounts.json
```

Linux 服务器上使用：

```bash
cp .env.example .env
cp accounts.example.json accounts.json
```

## `.env`

`.env` 用来保存 OSS 和可选 AI 配置。

必填：

```env
OSS_ACCESS_KEY_ID=your_access_key_id
OSS_ACCESS_KEY_SECRET=your_access_key_secret
```

可选：

```env
MIAOSHOU_BASE_URL=https://openapi-erp.91miaoshou.com
DEEPSEEK_API_KEY=your_deepseek_key
OPENAI_API_KEY=your_openai_key
DASHSCOPE_API_KEY=your_dashscope_key
ARK_API_KEY=your_volcengine_key
AI_API_KEY=your_custom_openai_compatible_key
```

说明：

- OSS 密钥用于把本次上传的图片写入阿里云 OSS。
- AI 密钥只给开发中的单产品 / 单个链接智能上传入口使用；模板批量上传不依赖 AI。
- 如果 `.env` 已经存在，不要用示例文件覆盖真实文件。

## `accounts.json`

`accounts.json` 保存妙手账号配置。当前网页登录流程已移除，所以示例文件只保留妙手账号配置。

字段说明：

- `name`：网页下拉框显示名称，方便团队快速选择。
- `shop_id`：默认妙手店铺 ID。模板批量上传会使用这个账号绑定的店铺。
- `shop_name`：展示用店铺名称。
- `app_key`：妙手开放平台 App Key / App ID。
- `app_secret`：妙手开放平台 App Secret。
- `locked`：账号锁定状态。锁定后避免误改或误删。
- `templates`：三个模板名称对应的妙手模板产品 detailId。

模板名称固定为：

- `大地毯`
- `非定制毛毯`
- `定制毛毯`

如果模板 ID 留空，网页账号管理页会尝试从妙手中按模板分组关键词自动识别。

## 不要提交的文件

确认这些文件只保存在本地或服务器：

- `.env`
- `accounts.json`
- `ai_settings.json`
- `uploads/`
- `runs/`
- `app.log`
- `app.err`
