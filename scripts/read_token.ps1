$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$path = Join-Path (Join-Path $root '.secrets') 'bot-token.dpapi'
if (-not (Test-Path -LiteralPath $path)) { exit 2 }
Add-Type -AssemblyName System.Security
$encrypted = [Convert]::FromBase64String([IO.File]::ReadAllText($path, [Text.Encoding]::ASCII))
$bytes = [Security.Cryptography.ProtectedData]::Unprotect(
    $encrypted, $null, [Security.Cryptography.DataProtectionScope]::CurrentUser
)
try {
    [Console]::Out.Write([Text.Encoding]::UTF8.GetString($bytes))
} finally {
    [Array]::Clear($bytes, 0, $bytes.Length)
}
