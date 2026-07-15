# BuddyLib.ps1 - shared helpers for the Buddy AI installer scripts.
# Dot-sourced by the other scripts. Pure PowerShell 5.1+ (ships with Windows 10/11).

$ErrorActionPreference = 'Stop'

function Write-Step($msg) { Write-Host "[buddy-install] $msg" }

function Get-Manifest($installerDir) {
    $p = Join-Path $installerDir 'models.manifest.json'
    return Get-Content -LiteralPath $p -Raw | ConvertFrom-Json
}

# Download a file with a progress-friendly method and verify size + optional SHA256.
# Resumes are not attempted; a failed/partial file is deleted and re-thrown.
function Get-FileVerified {
    param(
        [string]$Url,
        [string]$OutPath,
        [long]$ExpectedBytes = 0,
        [string]$ExpectedSha256 = ''
    )
    $dir = Split-Path -Parent $OutPath
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }

    # Skip if a valid copy already exists (idempotent re-runs).
    if (Test-Path $OutPath) {
        if ($ExpectedSha256 -and (Test-Sha256 $OutPath $ExpectedSha256)) {
            Write-Step "already present + verified: $(Split-Path -Leaf $OutPath)"
            return
        }
        if ($ExpectedBytes -gt 0 -and (Get-Item $OutPath).Length -eq $ExpectedBytes -and -not $ExpectedSha256) {
            Write-Step "already present (size ok): $(Split-Path -Leaf $OutPath)"
            return
        }
        Remove-Item -LiteralPath $OutPath -Force
    }

    Write-Step "downloading $(Split-Path -Leaf $OutPath) ..."
    try {
        # BITS is resumable + shows progress; fall back to WebClient if unavailable.
        Start-BitsTransfer -Source $Url -Destination $OutPath -ErrorAction Stop
    } catch {
        Write-Step "BITS unavailable, using WebClient..."
        (New-Object System.Net.WebClient).DownloadFile($Url, $OutPath)
    }

    if ($ExpectedBytes -gt 0) {
        $got = (Get-Item $OutPath).Length
        if ($got -ne $ExpectedBytes) {
            Remove-Item -LiteralPath $OutPath -Force -ErrorAction SilentlyContinue
            throw "size mismatch for $Url : expected $ExpectedBytes, got $got"
        }
    }
    if ($ExpectedSha256) {
        if (-not (Test-Sha256 $OutPath $ExpectedSha256)) {
            Remove-Item -LiteralPath $OutPath -Force -ErrorAction SilentlyContinue
            throw "SHA256 mismatch for $Url"
        }
    }
    Write-Step "ok: $(Split-Path -Leaf $OutPath)"
}

function Test-Sha256($path, $expected) {
    $h = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
    return ($h -ieq $expected)
}
