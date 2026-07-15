# DownloadModels.ps1 - fetch ComfyUI weights (HF) + pull Ollama models.
# Usage: DownloadModels.ps1 -InstallerDir <dir> -Root <target> -OllamaModels <dir>
param(
    [string]$InstallerDir,
    [string]$Root,
    [string]$OllamaModels
)
. (Join-Path $InstallerDir 'scripts\BuddyLib.ps1')
$mf = Get-Manifest $InstallerDir

# --- ComfyUI safetensors (verified by SHA256) ---
$comfyRoot = Join-Path $Root $mf.comfyui.extract_to
foreach ($m in $mf.comfyui_models) {
    $dest = Join-Path (Join-Path $comfyRoot $m.dest_subdir) $m.name
    Get-FileVerified -Url $m.url -OutPath $dest -ExpectedBytes $m.bytes -ExpectedSha256 $m.sha256
}

# --- Ollama models ---
# Point Ollama at the chosen models dir for this session's pulls.
if ($OllamaModels) {
    New-Item -ItemType Directory -Path $OllamaModels -Force | Out-Null
    $env:OLLAMA_MODELS = $OllamaModels
    # persist for the user so the running stack uses the same location
    [Environment]::SetEnvironmentVariable('OLLAMA_MODELS', $OllamaModels, 'User')
}
foreach ($om in $mf.ollama_models) {
    Write-Step "ollama pull $($om.name) ..."
    & ollama pull $om.name
    if ($LASTEXITCODE -ne 0) { throw "ollama pull failed for $($om.name)" }
}
Write-Step "all models present."
