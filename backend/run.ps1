$ErrorActionPreference = 'Stop'
$backendPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $backendPath
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
