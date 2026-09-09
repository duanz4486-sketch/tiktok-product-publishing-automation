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

`.env` 用来保存 OSS、网页访问保护和可选 AI 配置。

必填：

```env
OSS_BUCKET=your_bucket_name
OSS_ENDPOINT=oss-cn-shenzhen.aliyuncs.com
OSS_REGION=cn-shenzhen
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
WEB_ACCESS_PASSWORD=your_long_private_web_password
WEB_SESSION_SECRET=your_different_long_random_secret
```

说明：

- `OSS_BUCKET` 是阿里云 OSS 的 Bucket 名称，例如 `my-product-images`。
- `OSS_ENDPOINT` 是 Bucket 的外网 Endpoint 域名，不要带 `https://`，例如 `oss-cn-shenzhen.aliyuncs.com`。
- `OSS_REGION` 是 Bucket 所在地域 ID，例如深圳是 `cn-shenzhen`。
- OSS AccessKey 用于把本次上传的图片写入你自己的阿里云 OSS。
- AI 密钥只给开发中的单产品 / 单个链接智能上传入口使用；模板批量上传不依赖 AI。
- `WEB_ACCESS_PASSWORD` 和 `WEB_SESSION_SECRET` 用于保护网页入口。只在服务器或局域网共享时需要，本地自己测试可以不填。
- 如果 `.env` 已经存在，不要用示例文件覆盖真实文件。

## OSS 配置

每个部署者都必须使用自己的 OSS，不要使用别人的 Bucket。

在阿里云 OSS 控制台进入目标 Bucket 后，可以看到：

- Bucket 名称：填入 `OSS_BUCKET`。
- Endpoint / 访问域名：填入 `OSS_ENDPOINT`，只填类似 `oss-cn-shenzhen.aliyuncs.com` 的域名。
- 地域：填入 `OSS_REGION`，例如 `cn-shenzhen`、`cn-hangzhou`。

RAM 用户至少需要对这个 Bucket 有上传 Object 的权限。图片 URL 还需要能被妙手读取；如果妙手读取失败，优先检查 Bucket 读权限、防盗链和图片格式。

## 网页访问保护

如果网页只在自己电脑 `127.0.0.1` 使用，可以不设置访问密码。

如果网页通过服务器 IP、局域网 IP、Tailscale、Cloudflare Tunnel 或其他方式给别人访问，建议必须设置：

```env
WEB_ACCESS_PASSWORD=一串足够长的访问密码
WEB_SESSION_SECRET=另一串足够长的随机字符
```

说明：

- 访问密码只保护这个网页入口，不是妙手账号密码。
- 这两个值只放在服务器 `.env`，不要写进代码、README、截图或 GitHub。
- 两个值必须同时填写；只填一个时系统自检会报错。
- 开源用户下载项目后，可以设置自己的访问密码。

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
