$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ProjectRoot = $PSScriptRoot
$ParentRoot = Split-Path -Parent $ProjectRoot
Set-Location -LiteralPath $ParentRoot

function Test-Port {
    param([int]$Port)
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $result = $client.BeginConnect('127.0.0.1', $Port, $null, $null)
        if ($result.AsyncWaitHandle.WaitOne(500)) {
            $client.EndConnect($result)
            return $true
        }
        return $false
    }
    catch {
        return $false
    }
    finally {
        $client.Close()
    }
}

function Wait-Port {
    param([int]$Port, [int]$TimeoutSec = 120)
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if (Test-Port -Port $Port) { return $true }
        Start-Sleep -Milliseconds 500
    }
    return (Test-Port -Port $Port)
}

# 1. 选择 Python 解释器：优先使用独立 SmartVoyage 环境。
$PythonPathFile = Join-Path $ProjectRoot 'runtime\python-path.txt'
$Python = $null
if ($env:SMARTVOYAGE_PYTHON -and (Test-Path -LiteralPath $env:SMARTVOYAGE_PYTHON)) {
    $Python = $env:SMARTVOYAGE_PYTHON
}
elseif (Test-Path -LiteralPath $PythonPathFile) {
    $Candidate = (Get-Content -LiteralPath $PythonPathFile -TotalCount 1 | Select-Object -First 1).Trim()
    if ($Candidate -and (Test-Path -LiteralPath $Candidate)) { $Python = $Candidate }
}
if (-not $Python) {
    $DefaultPython = 'D:\agentFinal\FinRAG\Miniconda3\envs\SmartVoyage\python.exe'
    if (Test-Path -LiteralPath $DefaultPython) { $Python = $DefaultPython }
}
if (-not $Python) {
    $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($PythonCommand) { $Python = $PythonCommand.Source }
}
if (-not $Python) {
    throw 'Python not found. Set SMARTVOYAGE_PYTHON or create runtime\python-path.txt.'
}

# 2. 统一环境变量：修复系统代理/SSL 证书对 localhost 的影响。
$env:PYTHONPATH = $ParentRoot
$env:PYTHONIOENCODING = 'utf-8'
$env:NO_PROXY = '127.0.0.1,localhost'
$env:no_proxy = '127.0.0.1,localhost'

$CertFile = (& $Python -c "import certifi; print(certifi.where())" 2>$null | Select-Object -First 1).Trim()
if ($CertFile -and (Test-Path -LiteralPath $CertFile)) {
    $env:SSL_CERT_FILE = $CertFile
}
else {
    Remove-Item Env:SSL_CERT_FILE -ErrorAction SilentlyContinue
}

$LogDir = Join-Path $ProjectRoot 'runtime\logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$StreamlitPort = 8502

function Start-PythonService {
    param(
        [string]$Title,
        [string]$Module,
        [int]$Port,
        [string[]]$ExtraArgs = @()
    )

    if (Test-Port -Port $Port) {
        Write-Host "[$Title] already running on port $Port."
        return
    }

    Write-Host "[$Title] starting on port $Port..."
    $SafeName = $Title -replace '[^A-Za-z0-9_-]', '_'
    $ArgumentList = @('-m', $Module) + $ExtraArgs
    Start-Process -FilePath $Python -ArgumentList $ArgumentList `
        -WorkingDirectory $ParentRoot -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $LogDir "$SafeName.out.log") `
        -RedirectStandardError (Join-Path $LogDir "$SafeName.err.log")

    if (-not (Wait-Port -Port $Port -TimeoutSec 120)) {
        throw "$Title failed to start. See $LogDir\$SafeName.err.log"
    }
}

try {
    # 3. MySQL 中间件：优先启动项目本地 MySQL，其次回退 Docker Compose。
    $MysqlPort = 3309
    $MysqlData = Join-Path $ProjectRoot 'runtime\mysql-data'
    $MysqlBinFile = Join-Path $ProjectRoot 'runtime\mysql-bin.txt'
    $MysqlPidFile = Join-Path $ProjectRoot 'runtime\mysql.pid'

    if (-not (Test-Port -Port $MysqlPort)) {
        $StartedLocalMysql = $false
        if (Test-Path -LiteralPath $MysqlBinFile) {
            $MysqlBin = (Get-Content -LiteralPath $MysqlBinFile -TotalCount 1 | Select-Object -First 1).Trim()
            if ($MysqlBin -and (Test-Path -LiteralPath $MysqlBin)) {
                $MysqlBasedir = Split-Path -Parent (Split-Path -Parent $MysqlBin)
                $Process = Start-Process -FilePath $MysqlBin `
                    -ArgumentList @(
                        '--port=3309',
                        '--bind-address=127.0.0.1',
                        "--basedir=$MysqlBasedir",
                        "--datadir=$MysqlData",
                        '--console',
                        '--character-set-server=utf8mb4',
                        '--collation-server=utf8mb4_unicode_ci'
                    ) -WindowStyle Hidden `
                    -RedirectStandardOutput (Join-Path $LogDir 'mysql.out.log') `
                    -RedirectStandardError (Join-Path $LogDir 'mysql.err.log') `
                    -PassThru
                Set-Content -LiteralPath $MysqlPidFile -Value $Process.Id -Encoding ASCII
                $StartedLocalMysql = $true
            }
        }

        if (-not $StartedLocalMysql) {
            Write-Host 'Trying Docker Compose MySQL...'
            docker compose -f (Join-Path $ProjectRoot 'docker-compose.yml') up -d mysql
        }

        if (-not (Wait-Port -Port $MysqlPort -TimeoutSec 120)) {
            throw "MySQL failed to start on port $MysqlPort. See runtime\logs\mysql.err.log"
        }
        Write-Host 'MySQL is ready.'
    }
    else {
        Write-Host 'MySQL is already running.'
    }

    # 4. MCP 服务。
    Start-PythonService -Title 'SmartVoyage-MCP-Weather' -Module 'SmartVoyage.mcp_server.mcp_weather_server' -Port 8002
    Start-PythonService -Title 'SmartVoyage-MCP-Ticket' -Module 'SmartVoyage.mcp_server.mcp_ticket_server' -Port 8001
    Start-PythonService -Title 'SmartVoyage-MCP-Order' -Module 'SmartVoyage.mcp_server.mcp_order_server' -Port 8003

    # 5. A2A 服务。
    Start-PythonService -Title 'SmartVoyage-A2A-Weather' -Module 'SmartVoyage.a2a_server.weather_server' -Port 5005
    Start-PythonService -Title 'SmartVoyage-A2A-Ticket' -Module 'SmartVoyage.a2a_server.ticket_server' -Port 5006
    Start-PythonService -Title 'SmartVoyage-A2A-Order' -Module 'SmartVoyage.a2a_server.order_server' -Port 5007

    # 6. Streamlit 前端。
    Start-PythonService -Title 'SmartVoyage-Web' -Module 'streamlit' -Port $StreamlitPort `
        -ExtraArgs @('run', 'SmartVoyage/app.py', '--server.headless', 'true', '--server.port', "$StreamlitPort", '--server.address', '127.0.0.1')

    Write-Host ''
    Write-Host 'SmartVoyage is ready:'
    Write-Host '  MySQL:     127.0.0.1:3309'
    Write-Host '  MCP:       8001 / 8002 / 8003'
    Write-Host '  A2A:       5005 / 5006 / 5007'
    Write-Host "  Streamlit: http://127.0.0.1:$StreamlitPort"
    Start-Process "http://127.0.0.1:$StreamlitPort"
}
catch {
    Write-Host ''
    Write-Host ('Startup failed: ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host 'Log directory: ' + $LogDir
    Read-Host 'Press Enter to exit'
    exit 1
}
