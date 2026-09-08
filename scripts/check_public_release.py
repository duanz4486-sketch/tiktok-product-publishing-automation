from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


REQUIRED_FILES = [
    ".gitignore",
    "README.md",
    "SKILL.md",
    ".env.example",
    "accounts.example.json",
    "ai_settings.example.json",
    "requirements.txt",
    "docs/configuration.md",
    "docs/deployment.md",
    "docs/template-batch-upload.md",
    "docs/troubleshooting.md",
    "docs/release-checklist.md",
    "miaoshou_tool/__init__.py",
    "miaoshou_tool/accounts.py",
    "miaoshou_tool/ai.py",
    "miaoshou_tool/config.py",
    "miaoshou_tool/errors.py",
    "miaoshou_tool/files.py",
    "miaoshou_tool/forms.py",
    "miaoshou_tool/json_io.py",
    "miaoshou_tool/miaoshou_api.py",
    "miaoshou_tool/oss_upload.py",
    "miaoshou_tool/publishing.py",
    "miaoshou_tool/rendering.py",
    "miaoshou_tool/self_check.py",
    "miaoshou_tool/text.py",
    "scripts/check_setup.py",
    "scripts/run_local.ps1",
    "scripts/run_server.sh",
    "scripts/miaoshou.service.example",
]

FORBIDDEN_EXACT = {
    ".env",
    "accounts.json",
    "ai_settings.json",
    "app.log",
    "app.err",
    "tunnel.log",
    "tunnel.err.log",
    "tunnel.out.log",
}
FORBIDDEN_PREFIXES = (
    "runs/",
    "uploads/",
    ".local_tools/",
    "deploy/",
    "__pycache__/",
)
FORBIDDEN_SUFFIXES = (
    ".pyc",
    ".pyo",
    ".log",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".zip",
)
REQUIRED_GITIGNORE_PATTERNS = [
    ".env",
    "accounts.json",
    "ai_settings.json",
    "runs/",
    "uploads/",
    "data/*.db",
    "app.log",
    "app.err",
    "miaoshou-*.zip",
]


def _run_git(root: Path, args: list[str]) -> list[str]:
    output = subprocess.check_output(["git", *args], cwd=root, text=True, encoding="utf-8")
    return [line.strip() for line in output.splitlines() if line.strip()]


def _is_forbidden_tracked(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return (
        normalized in FORBIDDEN_EXACT
        or normalized.startswith(FORBIDDEN_PREFIXES)
        or normalized.endswith(FORBIDDEN_SUFFIXES)
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Check whether the repository is safe to publish.")
    parser.add_argument("--root", default=None, help="Project root. Defaults to the parent of this scripts folder.")
    parser.add_argument("--max-file-mb", type=float, default=2.0, help="Warn when a tracked file is larger than this.")
    args = parser.parse_args()

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    max_bytes = int(args.max_file_mb * 1024 * 1024)
    errors: list[str] = []
    warnings: list[str] = []

    try:
        tracked = set(_run_git(root, ["ls-files"]))
    except Exception as exc:
        print(f"ERROR: not a readable git repository: {exc}")
        return 1

    missing = [path for path in REQUIRED_FILES if path not in tracked]
    if missing:
        errors.append("Required public files are missing from git: " + ", ".join(missing))

    forbidden = sorted(path for path in tracked if _is_forbidden_tracked(path))
    if forbidden:
        errors.append("Private/generated files are tracked: " + ", ".join(forbidden))

    gitignore = root / ".gitignore"
    if gitignore.exists():
        text = gitignore.read_text(encoding="utf-8", errors="ignore")
        missing_ignores = [pattern for pattern in REQUIRED_GITIGNORE_PATTERNS if pattern not in text]
        if missing_ignores:
            warnings.append("Missing .gitignore patterns: " + ", ".join(missing_ignores))
    else:
        errors.append(".gitignore is missing.")

    large_files = []
    for path in tracked:
        file_path = root / path
        if file_path.exists() and file_path.is_file() and file_path.stat().st_size > max_bytes:
            large_files.append(path)
    if large_files:
        warnings.append("Large tracked files: " + ", ".join(sorted(large_files)))

    print("Public release safety check")
    print(f"Root: {root}")
    print(f"Tracked files: {len(tracked)}")

    if warnings:
        print()
        for warning in warnings:
            print(f"WARN: {warning}")

    if errors:
        print()
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    print("OK: repository contents look safe for public GitHub release.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
