$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

python -m pip install -r requirements.txt
python scripts/check_setup.py
python web_app.py --host 127.0.0.1 --port 8002
