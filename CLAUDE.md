# Miaoshou TikTok Upload Agent Guide

This repository is a Miaoshou TikTok product upload web tool. Before helping a user operate, deploy, debug, or extend it, read `SKILL.md`.

For website operation, use `docs/agent-usage.md`. The stable user workflow is template batch upload. The single-product intelligent upload flow is still experimental unless the user explicitly asks to test or improve it.

Security invariant: never reveal, log, or commit `.env`, `accounts.json`, `ai_settings.json`, run output, upload files, or API keys.
