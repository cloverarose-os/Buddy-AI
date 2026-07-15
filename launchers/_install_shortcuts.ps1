# Install: 1 startup entry + desktop shortcuts for the double-click launchers.
$WS = New-Object -ComObject WScript.Shell
$startup = [Environment]::GetFolderPath('Startup')
$desktop = [Environment]::GetFolderPath('Desktop')
$L = 'G:\Buddy AI\Launchers'

function New-Shortcut($lnkPath, $target, $desc, $iconIdx) {
    $sc = $WS.CreateShortcut($lnkPath)
    $sc.TargetPath  = $target
    $sc.WorkingDirectory = $L
    $sc.Description = $desc
    $sc.IconLocation = "$env:SystemRoot\System32\shell32.dll,$iconIdx"
    $sc.Save()
    Write-Host ("  created: " + $lnkPath)
}

# --- startup (login) -> the FULL stack, ordered + keep-alive ---------
New-Shortcut (Join-Path $startup 'Buddy Stack (autostart).lnk') `
    (Join-Path $L 'BuddyStack-Startup.vbs') `
    'Brings up Ollama -> Brain -> Watchdog -> Pet in order, and keeps them alive.' 43

# --- desktop double-click launchers ---------------------------------
New-Shortcut (Join-Path $desktop 'Start Buddy (pet).lnk') `
    (Join-Path $L 'START BUDDY (pet).vbs') `
    'Opens the Buddy desktop pet.' 44

New-Shortcut (Join-Path $desktop 'Start Buddy - FULL STACK.lnk') `
    (Join-Path $L 'START BUDDY - FULL STACK.vbs') `
    'Ollama + Brain (image gen) + Watchdog + Pet. The whole multimodal system.' 137

New-Shortcut (Join-Path $desktop 'Stop Buddy (everything).lnk') `
    (Join-Path $L 'STOP BUDDY (everything).vbs') `
    'Shuts down the entire Buddy stack and frees the GPU.' 131

Write-Host ''
Write-Host 'DONE.'
