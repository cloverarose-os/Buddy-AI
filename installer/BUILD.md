# Building the Buddy AI Windows Installer

This produces `BuddyAI-Setup-v0.1.0-alpha.exe`, the graphical installer. It must
be built on a Windows machine with Inno Setup (this can't be done in the chat
environment - it needs the Inno Setup compiler).

## One-time setup

1. **Install Inno Setup 6+** - https://jrsoftware.org/isdl.php (free).
2. **Get `7zr.exe`** - from https://www.7-zip.org/download.html, the
   "7-Zip Extra: standalone console version" package. Copy `7zr.exe` into
   `installer\tools\`. (See `installer\tools\README.md`.)

## Build steps

From the repo root, in PowerShell:

```powershell
# 1. Assemble the payload (copies the app code into installer\payload)
powershell -ExecutionPolicy Bypass -File installer\prepare_payload.ps1

# 2. Compile the installer (adjust the ISCC path if needed)
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\BuddyAI.iss
```

Output: `installer\Output\BuddyAI-Setup-v0.1.0-alpha.exe`.

## Test before releasing

- Run the `.exe` on a **clean Windows VM** (no Python/Ollama/ComfyUI) to prove
  the prerequisite auto-install works.
- Test both paths: **Full install** and **Companion only** (point it at a brain
  on another machine).
- Verify the preflight blocks on low disk space and warns on a non-NVIDIA GPU.

## What the installer does (summary)

Wizard: Welcome -> Install Type -> (Brain URL if companion-only) -> Install
Location -> Options (full only) -> Preflight -> Ready -> Install. During install
it lays out the app code, auto-installs missing prerequisites (Python, Ollama,
ComfyUI portable 0.27.0), downloads the three Z-Image model weights (SHA256
verified) and pulls the three Ollama models, writes `buddy_config.json` from the
wizard choices, and creates shortcuts / startup entries.

See `docs/INSTALLER-SPEC.md` for the full specification and
`installer\models.manifest.json` for exact URLs/sizes/checksums.

## Publishing the GitHub Release

1. Repo -> Releases -> Draft a new release.
2. Tag `v0.1.0-alpha`, title "Buddy AI v0.1.0-alpha", check **Set as a
   pre-release**.
3. Attach `BuddyAI-Setup-v0.1.0-alpha.exe`.
4. Add notes: what Buddy is, that it's an early alpha, requirements (Windows +
   NVIDIA RTX 4070-class GPU, ~40 GB install). Publish.
