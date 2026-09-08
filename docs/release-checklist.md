# 公开发布前检查清单

这个清单用于把项目发布到 GitHub 前最后确认一遍，避免别人下载后不知道怎么跑，或者误用还在开发中的入口。

## 公开仓库必须包含

- `README.md`
- `SKILL.md`
- `.env.example`
- `accounts.example.json`
- `ai_settings.example.json`
- `requirements.txt`
- `docs/`
- `scripts/check_setup.py`
- `scripts/run_local.ps1`
- `scripts/run_server.sh`
- `scripts/miaoshou.service.example`

## 不能提交到 GitHub

- `.env`
- `accounts.json`
- `ai_settings.json`
- `runs/`
- `uploads/`
- `data/*.db`
- `app.log`
- `app.err`

发布前运行：

```bash
git status --short
python scripts/check_setup.py
python test_web_app.py
```

## 当前稳定入口

稳定入口只有：

- 模板批量上传

它适合标题和图片不同，但类目、SKU、价格、库存、物流参数来自同一套妙手模板的批量上货。

## 当前开发中入口

这些入口还不能作为公开稳定能力宣传：

- 单产品智能上传
- AI 自动补软参数
- 不同类目自由上货

可以保留页面入口，但 README 不要把它写成正式流程。

## 人工试跑建议

每次准备公开版本前，用一个小批次试跑：

1. 上传 1-3 条标题 Excel。
2. 上传对应图片 ZIP 或图片文件夹。
3. 勾选先预检。
4. 确认没有序号错配。
5. 再取消预检，实际创建到妙手。
6. 到妙手采集箱确认标题、图片、模板参数是否正确。
