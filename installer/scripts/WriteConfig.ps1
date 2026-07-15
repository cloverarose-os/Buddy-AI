# WriteConfig.ps1 - writes buddy_config.json + creates the shared dir.
# Usage: WriteConfig.ps1 -Root <dir> -InstallType full|companion
#          [-BrainUrl url] [-HAEnabled 0|1] [-WatchdogEnabled 0|1]
param(
    [string]$Root,
    [ValidateSet('full','companion')][string]$InstallType = 'full',
    [string]$BrainUrl = 'http://localhost:8766',
    [int]$HAEnabled = 1,
    [int]$WatchdogEnabled = 1
)
. (Join-Path $PSScriptRoot 'BuddyLib.ps1')

$shared = Join-Path $Root 'shared'
New-Item -ItemType Directory -Path $shared -Force | Out-Null

if ($InstallType -eq 'companion') {
    # remote/companion-only: only the keys that matter; rest use loader defaults
    $cfg = [ordered]@{
        companion_dir = (Join-Path $Root 'companion')
        shared_dir    = $shared
        brain_url     = $BrainUrl
    }
} else {
    $cfg = [ordered]@{
        companion_dir = (Join-Path $Root 'companion')
        brain_dir     = (Join-Path $Root 'brain')
        watchdog_dir  = (Join-Path $Root 'watchdog')
        comfyui_dir   = (Join-Path $Root 'ComfyUI_windows_portable')
        ollama_models = (Join-Path $Root 'models\ollama')
        shared_dir    = $shared
        ollama_url    = 'http://localhost:11434'
        brain_url     = $BrainUrl
        home_assistant_enabled = [bool]$HAEnabled
        watchdog_enabled       = [bool]$WatchdogEnabled
    }
}

$json = $cfg | ConvertTo-Json -Depth 5
# write WITHOUT BOM (the loader tolerates a BOM, but clean is better)
[System.IO.File]::WriteAllText((Join-Path $Root 'buddy_config.json'), $json)
Write-Step "wrote $(Join-Path $Root 'buddy_config.json')"
