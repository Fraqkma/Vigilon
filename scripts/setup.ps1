param([string]$EnvironmentFile = '')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$envPath = if ([string]::IsNullOrWhiteSpace($EnvironmentFile)) { Join-Path $root '.env' } elseif ([IO.Path]::IsPathRooted($EnvironmentFile)) { $EnvironmentFile } else { Join-Path $root $EnvironmentFile }
if (-not (Test-Path -LiteralPath $envPath)) {
    Copy-Item -LiteralPath (Join-Path $root '.env.example') -Destination $envPath
}
$content = Get-Content -LiteralPath $envPath -Raw
if ($content.Contains('generate-with-scripts/setup.ps1') -or $content.Contains('set-a-unique-password')) {
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    $bytes = New-Object byte[] 48
    $rng.GetBytes($bytes)
    $secret = [Convert]::ToBase64String($bytes)
    $keyBytes = New-Object byte[] 32
    $rng.GetBytes($keyBytes)
    $key = [Convert]::ToBase64String($keyBytes).Replace('+','-').Replace('/','_')
    $dbBytes = New-Object byte[] 24
    $rng.GetBytes($dbBytes)
    $dbPassword = ([BitConverter]::ToString($dbBytes)).Replace('-','').ToLowerInvariant()
    $adminPassword = ''
    if ($content.Contains('VIGILON_ADMIN_PASSWORD=set-a-unique-password')) {
        $securePassword = Read-Host 'Choose the local admin password (12+ characters)' -AsSecureString
        if ($securePassword.Length -lt 12) { throw 'The administrator password must contain at least 12 characters.' }
        $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
        try { $adminPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
    }
    $content = $content.Replace('VIGILON_SECRET_KEY=generate-with-scripts/setup.ps1', "VIGILON_SECRET_KEY=$secret")
    $content = $content.Replace('VIGILON_ENCRYPTION_KEY=generate-with-scripts/setup.ps1', "VIGILON_ENCRYPTION_KEY=$key")
    $content = $content.Replace('VIGILON_ADMIN_PASSWORD=set-a-unique-password', "VIGILON_ADMIN_PASSWORD=$adminPassword")
    $content = $content.Replace('POSTGRES_PASSWORD=generate-with-scripts/setup.ps1', "POSTGRES_PASSWORD=$dbPassword")
    if (-not $content.Contains('DATABASE_URL=')) { $content += "`nDATABASE_URL=sqlite:///./.data/vigilon.db`n" }
    [IO.File]::WriteAllText($envPath,$content,(New-Object Text.UTF8Encoding($false)))
    Write-Host 'Filled missing .env placeholders with local secrets and the chosen admin password.'
} else { Write-Host '.env already contains configuration; left unchanged.' }
