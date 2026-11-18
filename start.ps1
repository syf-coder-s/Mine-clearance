$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { throw 'Deployment failed. Run docker compose logs api for details.' }
Write-Host '前端（同源）: http://localhost:8010/'
Write-Host 'API 文档: http://localhost:8010/docs'
Write-Host '健康检查: http://localhost:8010/v1/health'
