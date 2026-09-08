# 部署说明

本项目可以本地运行，也可以部署到云服务器给小团队使用。

## 本地运行

```bash
python -m pip install -r requirements.txt
python web_app.py --host 127.0.0.1 --port 8002
```

浏览器打开：

```text
http://127.0.0.1:8002/
```

## 局域网或服务器运行

```bash
python web_app.py --host 0.0.0.0 --port 8002
```

然后访问：

```text
http://服务器IP:8002/
```

首次部署建议先打开：

```text
http://服务器IP:8002/check
```

确认系统自检没有红色失败项后，再让团队使用模板批量上传。

如果部署在阿里云服务器，需要同时放行：

- 阿里云安全组入方向 TCP `8002`
- 服务器系统防火墙 TCP `8002`

## 宝塔 / Alibaba Cloud Linux 示例

如果 Python 3.10 安装在宝塔 Python 项目管理器中，可能的启动命令类似：

```bash
cd /www/wwwroot/miaoshou
/www/server/python_manager/versions/3.10.0/bin/python3 -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
nohup /www/server/python_manager/versions/3.10.0/bin/python3 web_app.py --host 0.0.0.0 --port 8002 > app.log 2>&1 &
```

查看日志：

```bash
tail -50 app.log
tail -50 app.err
```

## 长期运行建议

`nohup` 适合临时测试。长期每天给团队使用时，建议改成 systemd 或宝塔的进程守护方式，保证服务器重启后自动恢复。

systemd 示例：

```ini
[Unit]
Description=Miaoshou TikTok Upload Tool
After=network.target

[Service]
WorkingDirectory=/www/wwwroot/miaoshou
ExecStart=/www/server/python_manager/versions/3.10.0/bin/python3 /www/wwwroot/miaoshou/web_app.py --host 0.0.0.0 --port 8002
Restart=always
RestartSec=5
User=www

[Install]
WantedBy=multi-user.target
```

## 更新代码

更新前先备份真实配置：

```bash
cp .env .env.bak
cp accounts.json accounts.json.bak
```

更新代码后不要覆盖：

- `.env`
- `accounts.json`
- `ai_settings.json`
- `runs/`
- `uploads/`
