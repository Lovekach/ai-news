$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$secretDir = Join-Path $root '.secrets'
New-Item -ItemType Directory -Path $secretDir -Force | Out-Null
$secret = Read-Host 'Paste Telegram bot token' -AsSecureString
if ($secret.Length -lt 20) { throw 'Token is too short' }
Add-Type -AssemblyName System.Security
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
try {
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    $bytes = [Text.Encoding]::UTF8.GetBytes($plain)
    try {
        $encrypted = [Security.Cryptography.ProtectedData]::Protect(
            $bytes, $null, [Security.Cryptography.DataProtectionScope]::CurrentUser
        )
        [IO.File]::WriteAllText(
            (Join-Path $secretDir 'bot-token.dpapi'),
            [Convert]::ToBase64String($encrypted),
            [Text.Encoding]::ASCII
        )
    } finally {
        [Array]::Clear($bytes, 0, $bytes.Length)
    }
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
}
Write-Host 'Token encrypted for the current Windows user.'
