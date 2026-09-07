$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

Write-Host '启动 Flight Map API（后台）与前端开发服务器...'
$api = Start-Process -FilePath 'uv' -ArgumentList @('run', 'flightmap-api') -PassThru -WindowStyle Hidden
try {
    npm run dev
}
finally {
    if (-not $api.HasExited) {
        # Stop only the process tree started here (uv plus the reload worker).
        taskkill.exe /PID $api.Id /T /F | Out-Null
    }
}
