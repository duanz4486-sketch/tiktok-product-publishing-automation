# 首次部署和使用

这份文档给第一次从 GitHub 下载本项目的人使用。目标是：部署到本机或服务器后，填写自己的 OSS 和妙手密钥，就能使用当前稳定的「模板批量上传」入口。

## 你需要准备什么

- Python 3.10 或更新版本。
- 一个阿里云 OSS Bucket，用来保存商品图片。
- OSS AccessKey，必须能向你的 Bucket 上传文件。
- 妙手开放平台 App Key / App Secret。
- 妙手里已经保存好的三个模板产品：`大地毯`、`非定制毛毯`、`定制毛毯`。
- 标题 Excel 和对应的图片 ZIP 或图片文件夹。

公开仓库不会包含任何可用密钥。每个部署者都要填写自己的 `.env` 和妙手账号配置。

## 1. 下载项目

```bash
git clone https://github.com/duanz4486-sketch/tiktok-product-publishing-automation.git
cd tiktok-product-publishing-automation
```

如果你不是用 Git，也可以在 GitHub 页面点击 `Code`，下载 ZIP 后解压。

## 2. 安装依赖

```bash
python -m pip install -r requirements.txt
```

如果服务器下载 Python 包很慢，可以换成国内镜像：

```bash
python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

## 3. 创建配置文件

Windows：

```bat
copy .env.example .env
copy accounts.example.json accounts.json
```

Linux / 宝塔服务器：

```bash
cp .env.example .env
cp accounts.example.json accounts.json
```

如果这些真实配置文件已经存在，不要覆盖。

## 4. 填写 OSS 配置

打开 `.env`，至少填写：

```env
OSS_BUCKET=你的Bucket名称
OSS_ENDPOINT=oss-cn-shenzhen.aliyuncs.com
OSS_REGION=cn-shenzhen
OSS_ACCESS_KEY_ID=你的OSS AccessKey ID
OSS_ACCESS_KEY_SECRET=你的OSS AccessKey Secret
```

注意：

- `OSS_ENDPOINT` 不要带 `https://`。
- `OSS_REGION` 要和 Bucket 地域一致。
- OSS 图片 URL 必须能被妙手读取。
- 如果同名图片已经存在，程序会按本次上传内容覆盖。

## 5. 填写妙手账号

推荐先启动网页后，在「妙手账号管理」页面新增账号。需要填写：

- 显示名称：网页下拉框里看到的名字。
- 妙手账号：妙手接口认可的账号或店铺编号。
- App Key / App ID。
- App Secret。
- 三个模板 ID，或让系统按模板关键词识别。

模板关键词固定为：

- `大地毯`
- `非定制毛毯`
- `定制毛毯`

如果账号已经调试好，可以在账号管理页上锁，避免误改或误删。

## 6. 本地启动

```bash
python scripts/check_setup.py
python web_app.py --host 127.0.0.1 --port 8002
```

Windows 也可以运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_local.ps1
```

浏览器打开：

```text
http://127.0.0.1:8002/
```

`127.0.0.1` 只能在当前电脑访问。团队成员不能直接打开你电脑上的这个本地地址。

## 7. 服务器 / 宝塔部署

如果要给团队两三个人共用，建议部署到云服务器。

基本步骤：

1. 把项目上传到服务器目录，例如 `/www/wwwroot/miaoshou`。
2. 在宝塔或 SSH 终端进入项目目录。
3. 安装依赖。
4. 配置 `.env` 和 `accounts.json`。
5. 开放端口 `8002`。
6. 启动网页。

宝塔常用命令示例：

```bash
cd /www/wwwroot/miaoshou
/www/server/python_manager/versions/3.10.0/bin/python3 -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
/www/server/python_manager/versions/3.10.0/bin/python3 scripts/check_setup.py
nohup /www/server/python_manager/versions/3.10.0/bin/python3 web_app.py --host 0.0.0.0 --port 8002 > app.log 2>&1 &
```

然后访问：

```text
http://服务器公网IP:8002/
```

服务器使用时，建议在 `.env` 里设置：

```env
WEB_ACCESS_PASSWORD=一串足够长的访问密码
WEB_SESSION_SECRET=另一串足够长的随机字符
```

## 8. 使用模板批量上传

1. 打开网页首页。
2. 选择妙手账号。
3. 选择模板类型：`大地毯`、`非定制毛毯`、`定制毛毯`。
4. 填写批次名。批次名只方便查找，不参与匹配。
5. 上传标题 Excel。
6. 上传图片 ZIP 或图片文件夹。
7. 首次建议勾选「先预检，不创建产品」。
8. 预检通过后，再取消预检正式上传。

匹配规则只看序号：

```text
Excel 序号 1 -> 图片子文件夹 1
Excel 序号 2 -> 图片子文件夹 2
Excel 序号 3 -> 图片子文件夹 3
```

Excel 文件名、ZIP 文件名、批次名、OSS 目录名都不参与匹配。

## 9. 常见错误快速判断

网页打不开：

- 程序没有启动。
- 访问端口写错。
- 阿里云安全组没有放行 TCP `8002`。
- 宝塔系统防火墙没有放行 TCP `8002`。

系统自检失败：

- `.env` 没有配置完整。
- `accounts.json` 不存在。
- 妙手账号缺模板 ID。

图片匹配失败：

- Excel 没有 `序号` 或 `标题` 列。
- 图片子文件夹没有按序号命名。
- Excel 有序号但图片没有对应文件夹。
- 图片有序号但 Excel 没有对应标题。

OSS 上传失败：

- OSS AccessKey 错误。
- RAM 用户没有 OSS 上传权限。
- Bucket、Endpoint 或 Region 填错。
- 图片 URL 不能被妙手访问。

妙手接口失败：

- App Key / App Secret 错误。
- 妙手账号没有接口权限。
- 模板 ID 失效。
- 店铺、仓库或模板参数在妙手侧缺失。

更多处理方式见 [常见问题](troubleshooting.md)。

## 10. 发布或更新前检查

公开发布或更新代码前运行：

```bash
python scripts/check_public_release.py
python scripts/check_setup.py
python test_web_app.py
```

`check_public_release.py` 必须通过。不要把 `.env`、`accounts.json`、`ai_settings.json`、`runs/`、`uploads/`、日志文件提交到 GitHub。
