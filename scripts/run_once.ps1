param([string]$PythonExecutable)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'python_runtime.ps1')
$root = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $root '.state'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$logPath = Join-Path $logDir 'scheduler.log'
$pythonExe = Resolve-AINewsPython -Executable $PythonExecutable
if (-not (Test-Path -LiteralPath $pythonExe)) { throw "Python not found: $pythonExe" }
$utf8 = New-Object System.Text.UTF8Encoding $false
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8
$env:PYTHONIOENCODING = 'utf-8'
Set-Location -LiteralPath $root
"[$(Get-Date -Format o)] start" | Out-File -LiteralPath $logPath -Append -Encoding utf8
& $pythonExe -m ainews run-once 2>&1 | Out-File -LiteralPath $logPath -Append -Encoding utf8
$code = $LASTEXITCODE
"[$(Get-Date -Format o)] exit=$code" | Out-File -LiteralPath $logPath -Append -Encoding utf8
exit $code
