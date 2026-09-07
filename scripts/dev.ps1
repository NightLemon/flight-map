$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

Write-Host '启动 Flight Map API（后台）与前端开发服务器...'
$api = Start-Process -FilePath 'uv' -ArgumentList @('run', 'flightmap-api') -PassThru -NoNewWindow
try {
    npm run dev
}
finally {
    if (-not $api.HasExited) {
        Stop-Process -Id $api.Id
    }
}
