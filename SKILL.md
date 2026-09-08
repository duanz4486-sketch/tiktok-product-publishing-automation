---
name: miaoshou-tiktok-upload
description: Operate and maintain the Miaoshou TikTok template batch upload web tool, especially configuration, deployment, Excel/image matching, OSS upload, and troubleshooting.
---

# Miaoshou TikTok Upload

Use this skill when working on this repository's Miaoshou TikTok product upload tool.

## Current Supported Workflow

The stable workflow is template batch upload:

1. User prepares a title Excel file with sequence IDs and titles.
2. User uploads an image ZIP or image folder whose product subfolders are named by the same sequence IDs.
3. The tool matches Excel rows and image folders by sequence ID.
4. The tool uploads current images to OSS when enabled.
5. The tool creates public collection-box products, claims them to TikTok, applies the selected Miaoshou template, and writes local logs.

The single-product / single-link intelligent upload page exists in the app but is still under active development. Do not document it as a stable user workflow until the user confirms it is ready.

## Operational Invariants

- Treat the current uploaded Excel and current uploaded image source as authoritative.
- Match only by sequence ID, not by batch name, Excel filename, ZIP filename, or OSS folder name.
- Report Excel-only IDs as missing image folders and image-only IDs as missing titles.
- When OSS upload is enabled, current uploads may overwrite same-name OSS objects.
- Never expose or commit `.env`, `accounts.json`, `ai_settings.json`, logs, uploads, or run output.

## References

- For environment variables and account examples, read `docs/configuration.md`.
- For the stable user workflow, read `docs/template-batch-upload.md`.
- For local or server deployment, read `docs/deployment.md`.
- For known errors and diagnosis, read `docs/troubleshooting.md`.
