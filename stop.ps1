$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ProjectRoot = $PSScriptRoot

foreach ($Port in 8502, 8001, 8002, 8003, 5005, 5006, 5007) {
    $Connections = Get-NetTCPConnection -LocalPort $Port -State Listen
    foreach ($Connection in $Connections) {
        Stop-Process -Id $Connection.OwningProcess -Force
    }
}

$MysqlPidFile = Join-Path $ProjectRoot 'runtime\mysql.pid'
if (Test-Path -LiteralPath $MysqlPidFile) {
    $MysqlPid = (Get-Content -LiteralPath $MysqlPidFile -TotalCount 1 | Select-Object -First 1).Trim()
    if ($MysqlPid -and (Get-Process -Id $MysqlPid -ErrorAction SilentlyContinue)) {
        Stop-Process -Id $MysqlPid -Force
    }
    Remove-Item -LiteralPath $MysqlPidFile -Force
}

Write-Host 'SmartVoyage stopped.'
