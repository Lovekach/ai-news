# Resolve the caller's Python without hard-coding a developer's installation.
function Resolve-AINewsPython {
    param([string]$Executable, [switch]$Windowless)
    if ($Executable) {
        $resolved = (Resolve-Path -LiteralPath $Executable -ErrorAction Stop).Path
    } else {
        $resolved = (Get-Command python.exe -CommandType Application -ErrorAction Stop).Source
    }
    if ($Windowless) { $resolved = Join-Path (Split-Path -Parent $resolved) 'pythonw.exe' }
    if (-not (Test-Path -LiteralPath $resolved -PathType Leaf)) { throw 'Python executable was not found. Specify its full path.' }
    return $resolved
}
