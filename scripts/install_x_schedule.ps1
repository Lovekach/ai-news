param([string]$PythonExecutable)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'python_runtime.ps1')
$runner = Join-Path $PSScriptRoot 'run_hidden.pyw'
$pythonwExe = Resolve-AINewsPython -Executable $PythonExecutable -Windowless
if (-not (Test-Path -LiteralPath $runner)) { throw 'Runner not found' }
if (-not (Test-Path -LiteralPath $pythonwExe)) { throw 'Python windowless executable not found' }
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
$action = New-ScheduledTaskAction -Execute $pythonwExe -Argument ('"' + $runner + '" x') -WorkingDirectory (Split-Path -Parent $PSScriptRoot)
$existing = Get-ScheduledTask -TaskName 'AI News X' -ErrorAction SilentlyContinue
if ($existing) {
    foreach ($prior in $existing.Actions) {
        if ($prior.WorkingDirectory -ne $action.WorkingDirectory -or -not $prior.Arguments.Contains($runner)) { throw 'Existing AI News X task belongs to another checkout' }
    }
}
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1) -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 4)
Register-ScheduledTask -TaskName 'AI News X' -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Write-Host 'X RSS account scan installed (every minute, hidden).'
