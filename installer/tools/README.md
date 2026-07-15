# tools/

This folder must contain `7zr.exe` before compiling the installer.

`7zr.exe` is the standalone 7-Zip console extractor (freely redistributable),
used by `InstallPrereqs.ps1` to extract the ComfyUI portable `.7z` archive.

Get it from the official 7-Zip site (https://www.7-zip.org/download.html) - the
"7-Zip Extra: standalone console version" package contains `7zr.exe`. Place that
single file here as `tools\7zr.exe`.

It is intentionally not committed to the repo (it's a third-party binary); the
build step / BUILD.md documents fetching it.
