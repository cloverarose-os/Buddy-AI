# prepare_payload.ps1 - assembles installer\payload from the repo's app code.
# Run this before compiling BuddyAI.iss. Repeatable (clears payload first).
$repo = Split-Path -Parent (Split-Path -Parent $PSCommandPath)  # ...\Buddy-AI
$pay = Join-Path $PSScriptRoot 'payload'

Remove-Item $pay -Recurse -Force -ErrorAction SilentlyContinue
foreach ($d in 'companion','brain','watchdog','launchers') {
    New-Item -ItemType Directory -Path (Join-Path $pay $d) -Force | Out-Null
    Copy-Item (Join-Path $repo "$d\*") (Join-Path $pay $d) -Recurse -Force
}
# never ship python bytecode caches
Get-ChildItem $pay -Recurse -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "payload assembled at $pay"
Get-ChildItem $pay -Recurse -File | ForEach-Object { $_.FullName.Replace($pay,'  payload') }
