from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Check Miaoshou TikTok upload tool configuration.")
    parser.add_argument("--root", default=None, help="Project root. Defaults to the parent of this scripts folder.")
    args = parser.parse_args()

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))

    from miaoshou_tool.self_check import run_release_check

    report = run_release_check(root=root, accounts_path=root / "accounts.json")
    summary = report["summary"]

    print("Miaoshou TikTok upload tool setup check")
    print(f"Root: {root}")
    print(f"OK: {summary['ok']}  WARN: {summary['warn']}  ERROR: {summary['error']}")
    print()

    for item in report["checks"]:
        status = item["status"].upper()
        print(f"[{status}] {item['label']}: {item['message']}")
        if item["status"] != "ok" and item.get("fix"):
            print(f"      Fix: {item['fix']}")

    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
