# Buddy AI - Windows Installer Specification

This is the build spec for the Buddy AI graphical Windows installer. It captures
every decision and every confirmed fact (download URLs, model sources, install
layout) so the installer can be built without re-deriving anything. The installer
itself is Inno Setup based (produces a single graphical `.exe`).

## Release identity

- First public release tag: **`v0.1.0-alpha`**
- GitHub Releases label: **alpha** (honest: functional and complete in features,
  but never installed from scratch by anyone but the author; fresh-machine
  install is unproven).
- One installer per OS. This spec is the **Windows** installer. Linux and a
  future Android companion are separate, later deliverables.

## Installer technology

- **Inno Setup** (free, standard for Windows graphical installers). Produces a
  polished wizard `.exe`: Welcome -> License -> Install-Type -> Location ->
  Components -> Preflight checks -> Prerequisite install -> File install ->
  Model download -> Finish.
- Heavy logic (downloads, extraction, prerequisite detection, model pulls) runs
  from Inno's `[Code]` (Pascal Script) calling PowerShell helper scripts that
  ship inside the installer. Keeping the real work in PowerShell scripts (not
  Pascal) makes it testable and reusable by the future Linux installer.
- The application code (companion, brain, watchdog, launchers, `buddy_config.py`,
  docs) is **bundled inside the installer**, not cloned from GitHub at install
  time. Rationale: self-contained, version-locked, no network dependency for the
  code itself, can't half-fail on a git error. GitHub Releases hosts the `.exe`;
  the code rides inside it.

## Confirmed download sources (verified against the author's live install)

### ComfyUI portable (NVIDIA)
- Version: **0.27.0** (matches the live install's `comfyui_version.py`).
- Asset: `ComfyUI_windows_portable_nvidia.7z` (~1990 MB compressed; extracts to
  ~21 GB on disk).
- URL: `https://github.com/Comfy-Org/ComfyUI/releases/download/v0.27.0/ComfyUI_windows_portable_nvidia.7z`
- Note: the standard `nvidia` variant (newer CUDA). There is also a
  `..._nvidia_cu126.7z` for older CUDA 12.6 machines. The live install is the
  standard nvidia build; if a target machine has an older driver the installer
  may fall back to the cu126 asset (same version tag).
- It is a `.7z` archive: the installer must ship a 7-Zip extractor (bundle
  `7zr.exe` from 7-Zip, which is freely redistributable) to extract it.

### Image-generation model weights (all from ONE Hugging Face repo)
Repo: **`Comfy-Org/z_image_turbo`** (official ComfyUI packaging of Z-Image
Turbo). All three files matched the live install by exact byte size.

| Local destination (under ComfyUI\models\)     | Repo path                                                  | Size (bytes)   |
|-----------------------------------------------|------------------------------------------------------------|----------------|
| `diffusion_models\z_image_turbo_int8_convrot.safetensors` | `split_files/diffusion_models/z_image_turbo_int8_convrot.safetensors` | 6,201,001,296 |
| `text_encoders\qwen_3_4b_fp8_mixed.safetensors`           | `split_files/text_encoders/qwen_3_4b_fp8_mixed.safetensors`           | 5,631,994,051 |
| `vae\ae.safetensors`                                       | `split_files/vae/ae.safetensors`                                       | 335,304,388   |

Full download URLs:
- `https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files/diffusion_models/z_image_turbo_int8_convrot.safetensors`
- `https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files/text_encoders/qwen_3_4b_fp8_mixed.safetensors`
- `https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files/vae/ae.safetensors`

SHA256 (for download verification):
- diffusion: `be517ebd47c912a5626a588e1aeea43e6be4a43c0cdcd2b48a2a780d9f358635`
- text_enc : `72450b19758172c5a7273cf7de729d1c17e7f434a104a00167624cba94f68f15`
- vae      : `afc8e28272cd15db3919bacdb6918ce9c1ed22e96cb12c4d5ed0fba823529e38`

The installer verifies each download's SHA256 so a corrupt/partial download is
caught rather than silently producing a broken image pipeline.

CORRECTION to earlier docs/MODELS.md: the diffusion model goes in
`diffusion_models\` (not `unet\`) and the CLIP/text-encoder goes in
`text_encoders\` (not `clip\`). MODELS.md must be updated to match this table.

### Ollama chat/vision/embedding models
Pulled with the Ollama CLI after Ollama is installed (no URLs needed):
- `ollama pull qwen3.5:9b`       (chat)
- `ollama pull gemma3:12b`       (vision)
- `ollama pull nomic-embed-text` (embeddings)
The installer sets `OLLAMA_MODELS` to the config's `ollama_models` path
(default `<root>\models\ollama`).

## Wizard flow (pages, in order)

1. **Welcome.**
2. **License** — no formal license yet; show a short "alpha / use at your own
   risk" notice instead.
3. **Install type** (the key branching choice):
   - **Full (local machine)** — install everything: companion, brain, watchdog,
     launchers, ComfyUI, Ollama, and all models.
   - **Companion only (remote machine)** — install ONLY the companion and its
     launcher. No brain, watchdog, ComfyUI, Ollama, or models. Ask for the brain
     endpoint next.
4. **Brain endpoint** (companion-only path only) — text field for `brain_url`,
   default `http://localhost:8766`; help text: enter the brain host, e.g.
   `http://192.168.x.x:8766` on the LAN or a tunnel DNS name for outside access.
5. **Install location** — one root folder; everything nests under it. Default
   `C:\BuddyAI` (user can pick another drive, e.g. `G:\Buddy AI`).
6. **Components / options** (checkboxes; full-install path):
   - Enable Home Assistant   (default ON)  -> `home_assistant_enabled`
   - Install Watchdog        (default ON)  -> `watchdog_enabled`
   - Start with Windows      (default ON)
   - Create desktop shortcuts (default ON)
   Companion-only path shows a reduced set: Start with Windows, desktop shortcut
   (companion launcher only).
7. **Preflight checks** — GPU, disk space, existing installs; shows the total
   download size before anything downloads.
8. **Confirmation** — "About to download ~X GB and install to <root>. Proceed?"
   Nothing downloads or installs before this explicit confirm.
9. **Prerequisite install** — detect + download + silently install missing
   prerequisites.
10. **File install** — write the app code from the bundle into the layout.
11. **Model download** — ComfyUI weights (HF) + Ollama pulls, with progress.
12. **Finish** — offer to launch Buddy; if HA enabled, show the connection
    values to enter in HA (URL `http://<host>:8766`, model `buddy`).

## Preflight checks (before any download)

- **GPU (full install only):** require an NVIDIA GPU with CUDA support. The
  author's baseline is an **RTX 4070**; treat that as the practical minimum for
  the models to run at usable speed. Detect via `nvidia-smi` (presence + driver
  + VRAM). If no NVIDIA GPU: warn strongly; allow override only with a clear
  "image/LLM generation may fail or be very slow" acknowledgement. A different
  NVIDIA card that meets or exceeds the 4070 baseline is fine. Skipped entirely
  for companion-only installs.
- **Disk space:** full install needs roughly **35-40 GB** free at the target
  root (ComfyUI ~21 GB extracted + 3 weights ~11.6 GB + Ollama models several GB
  + headroom). Check free space on the chosen drive and refuse if insufficient,
  showing the shortfall. Companion-only needs well under 1 GB.
- **Existing install:** detect an existing Ollama / ComfyUI / Python so the
  installer can skip re-installing them and reuse them (record their paths into
  the config rather than duplicating multi-GB downloads).

## Prerequisite handling (detect -> confirm -> download -> install)

Per the author's decision: **automatically install** missing prerequisites after
the confirmation step.

- **Python 3.11** (for the companion) — detect `py -3.11` / registry; if missing,
  download the official python.org 3.11 installer and run it silently
  (`/quiet InstallAllUsers=0 PrependPath=0`). The companion needs Pillow, so the
  installer then `pip install pillow` into that interpreter. (The brain runs on
  ComfyUI's embedded Python, so it needs no separate Python.)
- **Ollama** — detect `ollama` on PATH / default install dir; if missing,
  download the official Ollama Windows installer and run it silently. Then set
  `OLLAMA_MODELS` and pull the three models.
- **ComfyUI portable** — not a normal installer: download the `.7z` (URL above),
  verify size/hash, extract with the bundled `7zr.exe` into
  `<root>\ComfyUI_windows_portable`.
- **GPU driver / CUDA** — NOT auto-installed (too risky, machine-specific). The
  preflight only checks/ warns; driver updates are the user's responsibility.

## What the installer produces (final layout + config)

Mirrors the now-migrated live layout. Under the chosen `<root>` (e.g.
`C:\BuddyAI` or `G:\Buddy AI`):

```
<root>\
  companion\    (buddy.py, skin_highres.py, buddy_config.py)
  brain\        (buddy_ai.py, buddy_config.py)      [full only]
  watchdog\     (watchdog.py, watchdog_config.json, buddy_config.py) [full only, if enabled]
  launchers\    (BuddyStack.ps1, *.vbs, _install_shortcuts.ps1) [companion-only ships just the pet launcher]
  ComfyUI_windows_portable\   [full only]
  models\ollama\              [full only; OLLAMA_MODELS points here]
  shared\                     (runtime contract files; created empty)
  buddy_config.json           (written by the installer with the user's choices)
```

The installer writes `buddy_config.json` at `<root>` (UTF-8, no BOM) with the
chosen paths and toggles. Because each component's parent folder is `<root>`,
the shared loader finds this one config from every component. Keys written:
`companion_dir`, `brain_dir`, `watchdog_dir`, `comfyui_dir`, `ollama_models`,
`shared_dir`, `ollama_url`, `brain_url`, `home_assistant_enabled`,
`watchdog_enabled` (see `buddy_config.example.json`).

Companion-only installs write a config with just `companion_dir`, `shared_dir`,
and `brain_url` (pointed at the remote brain); the other keys are irrelevant and
omitted (loader defaults cover them).

## Shortcuts, startup, uninstall

- **Desktop shortcuts (full):** the three launcher shortcuts (Start pet / Start
  full stack / Stop everything) via the existing `_install_shortcuts.ps1` logic.
- **Desktop shortcut (companion-only):** ONLY the "Start Buddy (companion)"
  shortcut — the full-stack / stop / brain launchers are irrelevant on a
  companion box.
- **Start with Windows:** if chosen, register `BuddyStack-Startup.vbs` (full) or
  a companion-only startup entry as a Startup item / registry Run key.
- **Uninstall:** standard Add/Remove entry. Removes the app files and shortcuts.
  Should ASK before deleting the multi-GB ComfyUI + models (a user may want to
  keep those). Never deletes user-created data outside `<root>` without consent.

## Build process (how the .exe is produced)

This is the part a human runs once to compile the installer; it can't be done in
this chat environment (needs the Inno Setup compiler on a Windows machine).

1. Install **Inno Setup** (free) from jrsoftware.org on a Windows machine.
2. Lay out the installer source folder:
   - `BuddyAI.iss` (the Inno Setup script)
   - `payload\` = a copy of the repo's app code (companion, brain, watchdog,
     launchers, docs, `buddy_config.example.json`) — this is what gets bundled.
   - `scripts\` = the PowerShell helpers (preflight, prereq install, model
     download, config writer).
   - `tools\7zr.exe` (bundled 7-Zip standalone extractor for the ComfyUI .7z).
3. Compile: open `BuddyAI.iss` in Inno Setup and click Compile (or run
   `ISCC.exe BuddyAI.iss`). Output: `BuddyAI-Setup-v0.1.0-alpha.exe`.
4. Test the `.exe` on a clean machine / VM before releasing.

The `.iss` script, the PowerShell helper scripts, and a model manifest (URLs +
sizes + SHA256) are the concrete build artifacts to be written next. They will
live in an `installer/` folder in the repo (source), and the compiled `.exe` is
NOT committed (it's a release asset).

## Publishing the GitHub Release (author does this)

The compiled `.exe` is attached to a GitHub Release; this is the one step only
the author can click.

1. On GitHub: repo -> **Releases** -> **Draft a new release**.
2. **Tag:** `v0.1.0-alpha` (create it on publish). **Title:** "Buddy AI
   v0.1.0-alpha".
3. Mark **"Set as a pre-release"** (this is the alpha flag).
4. Write short release notes (what Buddy is; that it's an early alpha; system
   requirements: Windows + NVIDIA RTX 4070-class GPU; ~40 GB install).
5. **Attach** `BuddyAI-Setup-v0.1.0-alpha.exe` as a release asset.
6. Publish. The release appears under the repo's Releases tab, labeled
   pre-release/alpha, with the installer downloadable.

## Open items / next build steps

1. Write `installer/BuddyAI.iss` (Inno Setup wizard + component logic).
2. Write `installer/scripts/*.ps1` (preflight, prereqs, model download, config
   writer) — reuse the model manifest + URLs above.
3. Write `installer/models.manifest.json` (the URLs/sizes/SHA256 from this spec).
4. Fix `docs/MODELS.md` folder paths (`diffusion_models`, `text_encoders`).
5. Human: install Inno Setup, compile, test on a clean VM, publish the release.
