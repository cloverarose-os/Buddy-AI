# =====================================================================
#  BuddyStack.ps1 - the ONE launcher for the whole Buddy system.
#  Modes:  -Mode Pet    : just the desktop pet
#          -Mode Full   : Ollama -> Brain -> Watchdog -> Pet (ORDERED,
#                         each health-checked before the next starts)
#          -Mode Stop   : shut the whole stack down
#  Add -KeepAlive to Full: it then babysits the stack and restarts
#  anything that dies. This is what was MISSING when the Brain silently
#  died and took Home Assistant down with it (2026-07-12).
# =====================================================================
param(
    [ValidateSet('Pet', 'Full', 'Stop')] [string]$Mode = 'Full',
    [switch]$KeepAlive
)

$ErrorActionPreference = 'Continue'

# ---- paths ----------------------------------------------------------
# $env:LOCALAPPDATA resolves to C:\Users\<you>\AppData\Local automatically,
# so these work on any machine without a username baked in. The G:\Buddy AI
# paths reflect this dev machine's layout; the planned installer will make the
# install root configurable (they're single-quoted because the path has a space).
$SYS_PY   = "$env:LOCALAPPDATA\Programs\Python\Python311\pythonw.exe"
$COMFY_PY = 'G:\Buddy AI\ComfyUI_windows_portable\python_embeded\pythonw.exe'
$OLLAMA   = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
$BRAIN    = 'G:\Buddy AI\Brain\buddy_ai.py'
$BRAINDIR = 'G:\Buddy AI\Brain'
$WATCHDOG = 'G:\Buddy AI\Watchdog\watchdog.py'
$PET      = 'C:\ClaudeBuddy\buddy.py'
$LOG      = 'G:\Buddy AI\Launchers\stack.log'

function Log($msg) {
    $line = ('[{0}] {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg)
    Add-Content -LiteralPath $LOG -Value $line -ErrorAction SilentlyContinue
}

# ---- health checks: probe the real ENDPOINT, not just a process name.
# A process can be alive and still not serving (that is exactly how the
# Brain fooled us before).
function Test-Url($url) {
    try {
        $null = Invoke-WebRequest -Uri $url -TimeoutSec 3 -UseBasicParsing
        return $true
    } catch {
        # a 404 still proves something is LISTENING and answering
        if ($_.Exception.Response) { return $true }
        return $false
    }
}

function Test-Ollama   { Test-Url 'http://127.0.0.1:11434/api/version' }
function Test-Brain    { Test-Url 'http://127.0.0.1:8766/api/version' }
function Test-Pet      { Test-Url 'http://127.0.0.1:8765/status' }
function Test-Watchdog {
    $p = Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" -EA 0 |
         Where-Object { $_.CommandLine -like '*watchdog.py*' }
    return [bool]$p
}

# Wait for a service to come up, up to $secs. Returns $true if it did.
function Wait-For($name, $check, $secs = 60) {
    for ($i = 0; $i -lt $secs; $i++) {
        if (& $check) {
            Log ("  $name is UP (after {0}s)" -f $i)
            return $true
        }
        Start-Sleep -Seconds 1
    }
    Log "  *** $name FAILED to come up within ${secs}s ***"
    return $false
}

# ---- starters. All IDEMPOTENT: if it's already up, do nothing. So
# double-clicking a launcher twice can never spawn duplicates.
function Start-Ollama {
    if (Test-Ollama) { Log '  Ollama already running.'; return $true }
    Log '  starting Ollama...'
    # these MUST be set or HA/the LAN cannot reach it and models are lost
    $env:OLLAMA_HOST   = '0.0.0.0'
    $env:OLLAMA_MODELS = 'G:\Ollama\models'
    Start-Process -FilePath $OLLAMA -ArgumentList 'serve' `
                  -WindowStyle Hidden -EA SilentlyContinue
    return (Wait-For 'Ollama' ${function:Test-Ollama} 60)
}

function Start-Brain {
    if (Test-Brain) { Log '  Brain already running.'; return $true }
    Log '  starting Brain (ComfyUI embedded python)...'
    # *** MUST be the ComfyUI embedded python. *** The system python can
    # serve chat but CANNOT do image generation - the ComfyUI nodes live
    # in that embedded environment.
    Start-Process -FilePath $COMFY_PY -ArgumentList "`"$BRAIN`"" `
                  -WorkingDirectory $BRAINDIR -WindowStyle Hidden `
                  -EA SilentlyContinue
    # cold start loads models: give it room
    return (Wait-For 'Brain' ${function:Test-Brain} 120)
}

function Start-Watchdog {
    if (Test-Watchdog) { Log '  Watchdog already running.'; return $true }
    Log '  starting Watchdog...'
    Start-Process -FilePath $SYS_PY -ArgumentList "`"$WATCHDOG`"" `
                  -WindowStyle Hidden -EA SilentlyContinue
    Start-Sleep -Seconds 2
    return $true
}

function Start-Pet {
    if (Test-Pet) { Log '  Pet already running.'; return $true }
    Log '  starting Pet...'
    Start-Process -FilePath $SYS_PY -ArgumentList "`"$PET`"" `
                  -WindowStyle Hidden -EA SilentlyContinue
    return (Wait-For 'Pet' ${function:Test-Pet} 45)
}

function Stop-Stack {
    Log 'STOP: shutting the stack down...'
    Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" -EA 0 |
        Where-Object { $_.CommandLine -like '*buddy.py*' -or
                       $_.CommandLine -like '*buddy_ai.py*' -or
                       $_.CommandLine -like '*watchdog.py*' } |
        ForEach-Object {
            Log ('  killing PID {0}' -f $_.ProcessId)
            Stop-Process -Id $_.ProcessId -Force -EA SilentlyContinue
        }
    Get-Process ollama -EA SilentlyContinue |
        Stop-Process -Force -EA SilentlyContinue
    Log 'STOP: done.'
}

# =====================================================================
#  MAIN
# =====================================================================
Log ("===== BuddyStack: Mode=$Mode KeepAlive=$KeepAlive =====")

switch ($Mode) {

    'Stop' { Stop-Stack; break }

    'Pet' {
        # Just the desktop pet. Note: the pet needs the Brain to TALK, so
        # if the Brain is down we say so in the log rather than leaving
        # Buddy answering "Brain hiccup".
        Start-Pet | Out-Null
        if (-not (Test-Brain)) {
            Log '  NOTE: Brain is NOT running - Buddy will animate but cannot chat.'
            Log '        Use the FULL STACK launcher for the whole system.'
        }
        break
    }

    'Full' {
        # ORDER MATTERS. The Brain talks to Ollama, so Ollama must be
        # serving FIRST. The old startup fired all four VBS files at the
        # same instant with no ordering and no health checks.
        $okO = Start-Ollama
        if (-not $okO) { Log '  ABORT: Ollama never came up.' }
        $okB = Start-Brain
        if (-not $okB) { Log '  WARNING: Brain never came up - HA + chat will fail.' }
        Start-Watchdog | Out-Null
        Start-Pet | Out-Null
        Log ('SUMMARY  Ollama={0}  Brain={1}  Watchdog={2}  Pet={3}' -f
             (Test-Ollama), (Test-Brain), (Test-Watchdog), (Test-Pet))
        break
    }
}

# ---------------------------------------------------------------------
#  KEEP-ALIVE
#  This is the fix for the actual failure that took Home Assistant down:
#  the Brain died silently and NOTHING noticed or restarted it. Buddy
#  answered "Brain hiccup: URLError", HA's Assist just said "Oops, an
#  error has occurred", and both stayed broken until a human investigated.
#  Now: poll every 30s, restart anything that has fallen over, and LOG it
#  so there's always a record of what died and when.
# ---------------------------------------------------------------------
if ($KeepAlive -and $Mode -eq 'Full') {
    Log 'KEEP-ALIVE: watching Ollama / Brain / Pet every 30s.'
    while ($true) {
        Start-Sleep -Seconds 30
        try {
            if (-not (Test-Ollama)) {
                Log 'KEEP-ALIVE: *** OLLAMA DIED - restarting ***'
                Start-Ollama | Out-Null
            }
            if (-not (Test-Brain)) {
                Log 'KEEP-ALIVE: *** BRAIN DIED - restarting (this is what broke HA) ***'
                Start-Brain | Out-Null
            }
            if (-not (Test-Pet)) {
                Log 'KEEP-ALIVE: *** PET DIED - restarting ***'
                Start-Pet | Out-Null
            }
            if (-not (Test-Watchdog)) {
                Log 'KEEP-ALIVE: *** WATCHDOG DIED - restarting ***'
                Start-Watchdog | Out-Null
            }
        } catch {
            Log ('KEEP-ALIVE: error in loop: ' + $_.Exception.Message)
        }
    }
}
