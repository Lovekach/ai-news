"""Execute the installer function with fake Task Scheduler cmdlets."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(sys.platform == 'win32', 'Windows scheduling scripts')
class WakeScheduleTests(unittest.TestCase):
    def test_installer_explicitly_disables_wake_for_every_task(self):
        source = Path(__file__).resolve().parents[1]/'scripts/install_schedule.ps1'
        with tempfile.TemporaryDirectory() as temp:
            harness = Path(temp)/'installer.ps1'
            harness.write_text(r'''
param([string]$Source)
$ErrorActionPreference='Stop'
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($Source,[ref]$tokens,[ref]$errors)
if($errors.Count){throw 'Script parse failure'}
$f=$ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Install-AIJob'},$true)
. ([scriptblock]::Create($f.Extent.Text))
$script:jobs=@();$pythonwExe='pythonw.exe';$runner='runner.pyw';$projectRoot='.'
function New-ScheduledTaskAction { param($Execute,$Argument,$WorkingDirectory) return @{} }
function New-ScheduledTaskSettingsSet {
 param($MultipleInstances,$ExecutionTimeLimit,[switch]$AllowStartIfOnBatteries,[switch]$DontStopIfGoingOnBatteries)
 return [pscustomobject]@{WakeToRun=$true;StartWhenAvailable=$false}
}
function Register-ScheduledTask {
 param($TaskName,$Action,$Trigger,$Principal,$Settings,[switch]$Force)
 $script:jobs+= [pscustomobject]@{name=$TaskName;wake=$Settings.WakeToRun;catchup=$Settings.StartWhenAvailable}
}
foreach($mode in @('scan','telegram','x','editor','daily')) { Install-AIJob $mode $mode @() 3 ($mode -ne 'daily') }
$script:jobs | ConvertTo-Json -Compress
''', encoding='utf8')
            result = subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-File',str(harness),
                                     '-Source',str(source)],capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            jobs = {r['name']: r for r in json.loads(result.stdout.splitlines()[-1])}
            self.assertEqual({name for name, job in jobs.items() if job['wake']}, set())
            self.assertFalse(jobs['daily']['catchup'])
            self.assertTrue(jobs['editor']['catchup'])
