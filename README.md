# TikTok Product Publishing Automation

## 项目简介
这是一个用于跨境电商商品批量发布的自动化系统。
系统可以读取 Excel 商品标题和本地商品图片，
自动完成图片上传、妙手 OpenAPI 调用、模板匹配、
TikTok 商品创建以及批量任务执行。

## 项目解决的问题
传统商品上架流程需要人工重复执行：
- 整理商品标题
- 上传图片
- 创建商品
- 匹配模板
- 检查参数
- 批量处理失败任务

本项目将这些固定流程自动化，减少人工重复操作和批量上传错误。

## 核心流程

Excel + 图片
↓
数据校验
↓
图片上传 OSS
↓
调用妙手 OpenAPI
↓
模板匹配
↓
创建 TikTok 商品
↓
批量处理
↓
输出结果

## 技术栈

- Python
- OpenPyXL
- HTTP API
- HMAC Signature
- Alibaba Cloud OSS
- HTML / CSS
- Python HTTP Server
- Multithreading
- JSON / SQL

## 核心功能

- Excel 商品数据读取
- 商品图片自动匹配
- ZIP 图片上传
- OSS 自动上传
- 妙手 OpenAPI 集成
- API 限流自动重试
- 504 超时重试
- 商品模板自动识别
- 批量任务执行
- Web UI
- 登录与账号管理
- 任务进度显示
- 错误报告
- 自动化测试

## 项目结构

batch_tiktok_collect.py
核心商品批量发布逻辑

web_app.py
Web 页面、账号管理、任务处理

test_web_app.py
自动化测试

schema.sql
数据库结构

accounts.example.json
账号配置示例

.env.example
环境变量配置示例

## 项目状态

当前版本已经可以完成固定流程的商品批量发布。
该项目目前采用确定性 Workflow，而不是 Agent 架构。

原因是商品上传流程步骤明确，
使用 Workflow 可以获得更高的稳定性和可控性。

未来计划加入 AI Agent，用于处理异常判断、
标题优化和自动决策。
