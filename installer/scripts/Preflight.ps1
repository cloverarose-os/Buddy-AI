# Preflight.ps1 - checks BEFORE any download. Writes a JSON result the wizard reads.
# Usage: Preflight.ps1 -InstallerDir <dir> -Root <target> -InstallType full|companion -OutFile <json>
param(
    [string]$InstallerDir,
    [string]$Root,
    [ValidateSet('full','companion')][string]$InstallType = 'full',
    [string]$OutFile = "$env:TEMP\buddy_preflight.json"
)
. (Join-Path $InstallerDir 'scripts\BuddyLib.ps1')

$result = [ordered]@{
    ok = $true; warnings = @(); errors = @()
    gpu = $null; free_gb = $null; needed_gb = $null
    existing = [ordered]@{ python=$false; ollama=$false; comfyui=$false }
}

# --- GPU (full install only) ---
if ($InstallType -eq 'full') {
    $smi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
    if ($smi) {
        try {
            $vram = (& nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>$null | Select-Object -First 1).Trim()
            $name = (& nvidia-smi --query-gpu=name --format=csv,noheader 2>$null | Select-Object -First 1).Trim()
            $result.gpu = "$name ($vram MB VRAM)"
            if ([int]$vram -lt 11000) {
                $result.warnings += "GPU has ${vram}MB VRAM; the RTX 4070 baseline is ~12GB. Image/LLM gen may fail or be slow."
            }
        } catch { $result.warnings += "nvidia-smi present but could not be queried." }
    } else {
        $result.gpu = 'none detected'
        $result.warnings += "No NVIDIA GPU detected. Buddy's image/LLM generation needs an NVIDIA RTX (4070-class baseline). You can proceed, but generation may fail or be very slow."
    }
}

# --- disk space ---
$needed = if ($InstallType -eq 'full') { 40 } else { 1 }
$result.needed_gb = $needed
$drive = (Split-Path -Qualifier $Root)
try {
    $free = [math]::Round((Get-PSDrive ($drive.TrimEnd(':'))).Free / 1GB, 1)
    $result.free_gb = $free
    if ($free -lt $needed) {
        $result.ok = $false
        $result.errors += "Not enough free space on $drive : need ~${needed}GB, have ${free}GB."
    }
} catch { $result.warnings += "Could not determine free space on $drive." }

# --- existing installs (so we can reuse, not re-download) ---
if (Get-Command ollama -ErrorAction SilentlyContinue) { $result.existing.ollama = $true }
if (Get-Command py -ErrorAction SilentlyContinue) {
    if ((& py -3.11 -c "print(1)" 2>$null) -eq '1') { $result.existing.python = $true }
}
if (Test-Path (Join-Path $Root 'ComfyUI_windows_portable\python_embeded\python.exe')) { $result.existing.comfyui = $true }

$result | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $OutFile -Encoding UTF8
Write-Step "preflight written to $OutFile (ok=$($result.ok))"
