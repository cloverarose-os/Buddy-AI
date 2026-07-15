# CopyTree.ps1 - recursively copy a folder's contents. Usage: -Src <dir> -Dst <dir>
param([string]$Src, [string]$Dst)
New-Item -ItemType Directory -Path $Dst -Force | Out-Null
Copy-Item -Path (Join-Path $Src '*') -Destination $Dst -Recurse -Force
Write-Host "[buddy-install] copied $Src -> $Dst"
