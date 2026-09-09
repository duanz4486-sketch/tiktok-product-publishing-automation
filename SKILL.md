---
name: miaoshou-tiktok-upload
description: Use the Miaoshou TikTok upload web app: launch or open the site, guide template batch uploads, configure accounts safely, and troubleshoot Excel, image, OSS, and Miaoshou API failures.
---

# Miaoshou TikTok Upload

Use this skill when a user wants an agent such as Codex or Claude Code to help operate, deploy, or troubleshoot this repository's Miaoshou TikTok product upload website.

This skill is not the hosted website. It teaches the agent how to find, launch, or open the website, then guide the user through the stable upload workflow.

## Current Supported Workflow

The stable workflow is template batch upload:

1. User prepares a title Excel file with sequence IDs and titles.
2. User uploads an image ZIP or image folder whose product subfolders are named by the same sequence IDs.
3. The tool matches Excel rows and image folders by sequence ID.
4. The tool uploads current images to OSS when enabled.
5. The tool creates public collection-box products, claims them to TikTok, applies the selected Miaoshou template, and writes local logs.

The single-product / single-link intelligent upload page exists in the app but is still under active development. Do not document it as a stable user workflow until the user confirms it is ready.

## Agent Quick Start

1. Inspect the repository root and confirm these files exist: `web_app.py`, `requirements.txt`, `.env.example`, `accounts.example.json`, `docs/`, and `docs/first-time-setup.md`.
2. For a first-time user, guide `docs/first-time-setup.md` first. It is the source of truth for local setup, server setup, OSS configuration, Miaoshou account setup, and the stable upload workflow.
3. Run `python scripts/check_setup.py` before guiding real uploads when the local environment is available.
4. If the website is already deployed, ask the user for the deployment URL or use the URL already visible in the conversation. Open it with a browser tool when available.
5. If the user wants local use, start the app with `python web_app.py --host 127.0.0.1 --port 8002` or `powershell -ExecutionPolicy Bypass -File scripts/run_local.ps1`, then open `http://127.0.0.1:8002/`.
6. If the user wants team/server use, point them to `docs/deployment.md` and require the server `.env` access gate before exposing the URL.
7. Use `/check` for system self-check, `/accounts` for Miaoshou account setup, and `/` for the stable template batch upload workflow.

## Website Operating Flow

For a stable batch upload, guide the user through this sequence:

1. Open the website.
2. Confirm at least one Miaoshou account exists and is unlocked only while editing settings.
3. Run system self-check and resolve red failures.
4. On the template batch page, select the Miaoshou account and product template type.
5. Upload the current title Excel and current image ZIP or image folder.
6. Keep precheck enabled for the first pass.
7. Review mismatched sequence IDs, missing images, OSS upload errors, and Miaoshou API errors.
8. Run the real upload only after precheck is clean or the user accepts the failed items.

## Operational Invariants

- Treat the current uploaded Excel and current uploaded image source as authoritative.
- Match only by sequence ID, not by batch name, Excel filename, ZIP filename, or OSS folder name.
- Report Excel-only IDs as missing image folders and image-only IDs as missing titles.
- When OSS upload is enabled, current uploads may overwrite same-name OSS objects.
- Never expose or commit `.env`, `accounts.json`, `ai_settings.json`, logs, uploads, or run output.
- Do not hardcode the maintainer's server URL in public docs or Skill files. Public users should run their own local or server deployment, or explicitly provide their own URL.
- The single-product intelligent upload and AI soft-parameter workflow are in development; mention them as experimental unless the user explicitly asks to test them.

## Expected User Inputs

- Title Excel: must contain a sequence column such as `序号` and a title column such as `标题`, `最终英文标题`, or equivalent.
- Images: ZIP, folder, or uploaded image source whose product folders are named by sequence ID for batch upload.
- Miaoshou account: display name, Miaoshou account identifier, App Key, App Secret, and template IDs or discovered template matches.
- OSS: every deployment must configure its own `OSS_BUCKET`, `OSS_ENDPOINT`, `OSS_REGION`, `OSS_ACCESS_KEY_ID`, and `OSS_ACCESS_KEY_SECRET` privately through `.env`; same-name uploads may overwrite existing objects.

## References

- For a first-time user installing from GitHub, read `docs/first-time-setup.md`.
- For agent-specific website usage, read `docs/agent-usage.md`.
- For environment variables and account examples, read `docs/configuration.md`.
- For the stable user workflow, read `docs/template-batch-upload.md`.
- For local or server deployment, read `docs/deployment.md`.
- For known errors and diagnosis, read `docs/troubleshooting.md`.
