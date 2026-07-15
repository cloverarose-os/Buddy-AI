# InstallShortcuts.ps1 - installer-aware shortcut + startup registration.
# Usage: InstallShortcuts.ps1 -Root <dir> -InstallType full|companion
#          [-DesktopIcons 0|1] [-StartWithWindows 0|1]
param(
    [string]$Root,
    [ValidateSet('full','companion')][string]$InstallType = 'full',
    [int]$DesktopIcons = 1,
    [int]$StartWithWindows = 1
)
. (Join-Path $PSScriptRoot 'BuddyLib.ps1')

$WS = New-Object -ComObject WScript.Shell
$startup = [Environment]::GetFolderPath('Startup')
$desktop = [Environment]::GetFolderPath('Desktop')
$L = Join-Path $Root 'launchers'

function New-Shortcut($lnkPath, $target, $desc, $iconIdx) {
    $sc = $WS.CreateShortcut($lnkPath)
    $sc.TargetPath = $target
    $sc.WorkingDirectory = $L
    $sc.Description = $desc
    $sc.IconLocation = "$env:SystemRoot\System32\shell32.dll,$iconIdx"
    $sc.Save()
    Write-Step "shortcut: $lnkPath"
}

if ($DesktopIcons) {
    New-Shortcut (Join-Path $desktop 'Start Buddy (pet).lnk') `
        (Join-Path $L 'START BUDDY (pet).vbs') 'Opens the Buddy desktop pet.' 44
    if ($InstallType -eq 'full') {
        New-Shortcut (Join-Path $desktop 'Start Buddy - FULL STACK.lnk') `
            (Join-Path $L 'START BUDDY - FULL STACK.vbs') 'The whole multimodal system.' 137
        New-Shortcut (Join-Path $desktop 'Stop Buddy (everything).lnk') `
            (Join-Path $L 'STOP BUDDY (everything).vbs') 'Shuts down the entire stack.' 131
    }
}

if ($StartWithWindows) {
    if ($InstallType -eq 'full') {
        New-Shortcut (Join-Path $startup 'Buddy Stack (autostart).lnk') `
            (Join-Path $L 'BuddyStack-Startup.vbs') 'Starts the full Buddy stack at login.' 43
    } else {
        New-Shortcut (Join-Path $startup 'Buddy (autostart).lnk') `
            (Join-Path $L 'START BUDDY (pet).vbs') 'Starts the Buddy companion at login.' 43
    }
}
Write-Step "shortcuts done."
