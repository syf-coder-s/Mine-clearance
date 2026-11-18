$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
# 停止服务但保留容器和证据卷，避免误删历史快照。
docker compose stop api
if ($LASTEXITCODE -ne 0) { throw 'Failed to stop API.' }
