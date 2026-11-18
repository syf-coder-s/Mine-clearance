$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONPATH = Join-Path $PSScriptRoot 'src'
Write-Host 'API:    http://localhost:8010/docs'
Write-Host 'Health: http://localhost:8010/v1/health'
python -m uvicorn mineclearance.api.main:app --host 127.0.0.1 --port 8010 --reload