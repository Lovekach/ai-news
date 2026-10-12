param([string]$PythonExecutable)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'python_runtime.ps1')
$runner = Join-Path $PSScriptRoot 'run_hidden.pyw'
$pythonwExe = Resolve-AINewsPython -Executable $PythonExecutable -Windowless
if (-not (Test-Path -LiteralPath $runner)) { throw 'Runner not found' }
if (-not (Test-Path -LiteralPath $pythonwExe)) { throw 'Python windowless executable not found' }
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
$action = New-ScheduledTaskAction -Execute $pythonwExe -Argument ('"' + $runner + '" telegram') -WorkingDirectory (Split-Path -Parent $PSScriptRoot)
$existing = Get-ScheduledTask -TaskName 'AI News Telegram' -ErrorAction SilentlyContinue
if ($existing) {
    foreach ($prior in $existing.Actions) {
        if ($prior.WorkingDirectory -ne $action.WorkingDirectory -or -not $prior.Arguments.Contains($runner)) { throw 'Existing AI News Telegram task belongs to another checkout' }
    }
}
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 4)
Register-ScheduledTask -TaskName 'AI News Telegram' -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Write-Host 'Telegram channel scan installed (every 5 minutes, hidden).'
