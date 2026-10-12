param([string]$PythonExecutable)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'python_runtime.ps1')
$projectRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$runner = Join-Path $PSScriptRoot 'run_hidden.pyw'
if (-not (Test-Path -LiteralPath $runner)) { throw 'Runner not found' }
$pythonwExe = Resolve-AINewsPython -Executable $PythonExecutable -Windowless
if (-not (Test-Path -LiteralPath $pythonwExe)) { throw "Python windowless executable not found: $pythonwExe" }
$config = Get-Content -LiteralPath (Join-Path $projectRoot 'config.json') -Raw | ConvertFrom-Json
if ($config.publication_mode -ne 'daily') { throw 'AI configuration is not in daily mode' }
# Audit all existing AI jobs before changing any. Never overwrite another root.
$names = @('AI News Collector', 'AI News Editor', 'AI News Telegram', 'AI News X', 'AI News Daily Digest')
$backup = Join-Path $projectRoot ('.state\schedule-backup\' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $backup -Force | Out-Null
foreach ($name in $names) {
    $existing = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if ($existing) {
        foreach ($action in $existing.Actions) {
            if ($action.WorkingDirectory -ne $projectRoot -or -not $action.Arguments.Contains($runner)) {
                throw "Existing task belongs to a different project: $name"
            }
        }
        Export-ScheduledTask -TaskName $name | Set-Content -LiteralPath (Join-Path $backup ($name + '.xml')) -Encoding UTF8
    }
}
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
$mskNow = [DateTimeOffset]::UtcNow.ToOffset([TimeSpan]::FromHours(3))
function Daily-Trigger([int]$hour, [int]$minute) {
    $at = [DateTimeOffset]::new($mskNow.Year, $mskNow.Month, $mskNow.Day, $hour, $minute, 0, [TimeSpan]::FromHours(3))
    $trigger = New-ScheduledTaskTrigger -Daily -At $at.LocalDateTime
    $trigger.StartBoundary = $at.ToString('yyyy-MM-ddTHH:mm:sszzz')
    return $trigger
}
function Install-AIJob($name, $mode, $triggers, [int]$limitMinutes, [bool]$catchup) {
    $action = New-ScheduledTaskAction -Execute $pythonwExe -Argument ('"' + $runner + '" ' + $mode) -WorkingDirectory $projectRoot
    $settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes $limitMinutes) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    $settings.StartWhenAvailable = $catchup
    Register-ScheduledTask -TaskName $name -Action $action -Trigger $triggers -Principal $principal -Settings $settings -Force | Out-Null
    Write-Host "AI task enabled: $name ($mode)"
}
$first = (Get-Date).AddMinutes(1)
$minute = New-ScheduledTaskTrigger -Once -At $first -RepetitionInterval (New-TimeSpan -Minutes 1) -RepetitionDuration (New-TimeSpan -Days 3650)
$five = New-ScheduledTaskTrigger -Once -At $first -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 3650)
Install-AIJob 'AI News Collector' 'scan' @($minute) 1 $true
Install-AIJob 'AI News Telegram' 'telegram' @($five) 4 $true
Install-AIJob 'AI News X' 'x' @($minute) 4 $true
Install-AIJob 'AI News Editor' 'editor' @((Daily-Trigger 18 0), (Daily-Trigger 20 15), (Daily-Trigger 20 50)) 29 $true
Install-AIJob 'AI News Daily Digest' 'daily' @((Daily-Trigger 21 0)) 3 $false
$scheduledMessage = 'Daily Digest scheduled: ' + $mskNow.ToString('yyyy-MM-dd') + ' 21:00 MSK'
Write-Host $scheduledMessage
Add-Content -LiteralPath (Join-Path $projectRoot '.state\daily.log') -Value $scheduledMessage -Encoding UTF8
