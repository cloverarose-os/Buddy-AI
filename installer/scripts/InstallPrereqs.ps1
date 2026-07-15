# InstallPrereqs.ps1 - detect + install missing prerequisites, then ComfyUI.
# Usage: InstallPrereqs.ps1 -InstallerDir <dir> -Root <target> [-UseCu126]
param(
    [string]$InstallerDir,
    [string]$Root,
    [switch]$UseCu126
)
. (Join-Path $InstallerDir 'scripts\BuddyLib.ps1')
$mf = Get-Manifest $InstallerDir
$dl = Join-Path $env:TEMP 'buddy_dl'
New-Item -ItemType Directory -Path $dl -Force | Out-Null

# --- Python 3.11 (for the companion) ---
$hasPy = $false
if (Get-Command py -ErrorAction SilentlyContinue) {
    if ((& py -3.11 -c "print(1)" 2>$null) -eq '1') { $hasPy = $true }
}
if (-not $hasPy) {
    $pyExe = Join-Path $dl 'python-3.11.exe'
    Get-FileVerified -Url $mf.prerequisites.python.url -OutPath $pyExe
    Write-Step "installing Python 3.11 (silent)..."
    Start-Process -FilePath $pyExe -ArgumentList $mf.prerequisites.python.silent_args -Wait
} else { Write-Step "Python 3.11 already present." }

# Ensure Pillow for the companion's interpreter.
Write-Step "ensuring Pillow for the companion..."
try { & py -3.11 -m pip install --quiet --upgrade pillow } catch { Write-Step "pip pillow warning: $_" }

# --- Ollama ---
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    $olExe = Join-Path $dl 'OllamaSetup.exe'
    Get-FileVerified -Url $mf.prerequisites.ollama.url -OutPath $olExe
    Write-Step "installing Ollama (silent)..."
    Start-Process -FilePath $olExe -ArgumentList $mf.prerequisites.ollama.silent_args -Wait
} else { Write-Step "Ollama already present." }

# --- ComfyUI portable (download .7z + extract with bundled 7zr) ---
$comfyTarget = Join-Path $Root $mf.comfyui.extract_to
if (Test-Path (Join-Path $comfyTarget 'python_embeded\python.exe')) {
    Write-Step "ComfyUI already present at $comfyTarget - skipping."
} else {
    $url = if ($UseCu126) { $mf.comfyui.url_cu126 } else { $mf.comfyui.url }
    $sevenZip = Join-Path $dl $mf.comfyui.asset
    Get-FileVerified -Url $url -OutPath $sevenZip -ExpectedBytes $mf.comfyui.compressed_bytes
    $zr = Join-Path $InstallerDir 'tools\7zr.exe'
    Write-Step "extracting ComfyUI to $Root ..."
    # the .7z contains a top-level ComfyUI_windows_portable folder
    & $zr x $sevenZip "-o$Root" -y | Out-Null
    if (-not (Test-Path (Join-Path $comfyTarget 'python_embeded\python.exe'))) {
        throw "ComfyUI extraction did not produce the expected folder at $comfyTarget"
    }
}
Write-Step "prerequisites complete."
