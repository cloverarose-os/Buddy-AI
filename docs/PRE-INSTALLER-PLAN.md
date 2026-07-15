# Pre-Installer Plan: Closing the Holes

Goal: get the code into a state where an installer only has to (1) place files,
(2) fetch/place dependencies and models, and (3) **write one config file** with
the user's choices. No installer surgery on source code. This document is the
plan to get there; the installer itself is a later, separate task.

## The core principle

Every value the installer's wizard decides must be **read from one config
file at runtime**, not hardcoded in source. The wizard collects choices; each
component reads that same config on startup. That single change is what turns
"guided reinstall with hand-editing" into "install + drop a config file."

The wizard (per Clover's spec) collects:
- prerequisite install approval (Python, Ollama, ComfyUI)
- **one install location** (everything nests under it) — the recommended
  default — OR separate locations if the user insists
- Home Assistant: **enable or not** (runtime toggle — see Hole 4 for why it's
  "enable" rather than "install")
- Watchdog: install or not
- Start with the OS (Windows/Linux): yes/no
- Desktop icons / launcher shortcuts: yes/no

## The config file

A single JSON file, e.g. `buddy_config.json`, at a platform-appropriate,
well-known location, with an env var `BUDDY_CONFIG` able to override it (for
testing and for the eventual Android build):
- Windows: `%LOCALAPPDATA%\BuddyAI\buddy_config.json`
- Linux: `$XDG_CONFIG_HOME/buddyai/buddy_config.json` (fallback
  `~/.config/buddyai/buddy_config.json`)

Every component looks there first, then falls back to today's hardcoded values
so nothing breaks before the installer exists. The loader must resolve the right
location per-OS (via `platform`/`os` checks), never assume Windows.

```json
{
  "root":            "D:\\BuddyAI",
  "companion_dir":   "D:\\BuddyAI\\companion",
  "brain_dir":       "D:\\BuddyAI\\brain",
  "watchdog_dir":    "D:\\BuddyAI\\watchdog",
  "comfyui_dir":     "D:\\BuddyAI\\ComfyUI_windows_portable",
  "ollama_models":   "D:\\BuddyAI\\models\\ollama",
  "shared_dir":      "D:\\BuddyAI\\shared",
  "home_assistant_enabled": true,
  "watchdog_enabled": true
}
```

`shared_dir` is the fix for the cross-reference hole (below): the one folder
both the brain and companion use for `llm_status.json`, `inbox.txt`, etc.

## The holes, and the fix for each

### Hole 1 — Components find each other by absolute path (the critical one)

Today the brain writes `C:\ClaudeBuddy\llm_status.json` (the companion's
folder), the watchdog reads/writes `C:\ClaudeBuddy\` as `PET_BASE`, and the
companion reads that same status file. Three files cross-reference two roots by
literal path. If the installer puts things anywhere else, these silently break.

**Fix:** introduce `shared_dir` in the config. The brain, companion, and
watchdog all read `shared_dir` from config and put the contract files
(`llm_status.json`, `inbox.txt`, `outbox.txt`, `log.txt`) there. When the
installer uses one nested root, `shared_dir` is just `<root>\shared` and every
component agrees automatically.

Concrete edits:
- `companion/buddy.py` L27 `BASE = r"C:\ClaudeBuddy"` -> read from config
- `watchdog/watchdog.py` L12 `PET_BASE = r"C:\ClaudeBuddy"` -> read from config
- `brain/buddy_ai.py` L18 `STATUSF = r"C:\ClaudeBuddy\llm_status.json"` ->
  `<shared_dir>\llm_status.json`

### Hole 2 — ComfyUI location is reached three ways by the brain

`brain/buddy_ai.py` does `sys.path.insert(0, r"G:\Buddy AI\ComfyUI...\ComfyUI")`
(L12), reads generated images from `...\ComfyUI\output` (L248), and the launcher
runs the brain with ComfyUI's embedded Python. The installer knows where
ComfyUI landed; the code must read it.

**Fix:** `comfyui_dir` in config. Derive the ComfyUI-path insert, the output
dir, and (in the launcher) the embedded-python path from it.

Concrete edits:
- `brain/buddy_ai.py` L12 `sys.path.insert` -> `<comfyui_dir>\ComfyUI`
- `brain/buddy_ai.py` L248 output dir -> `<comfyui_dir>\ComfyUI\output`
- `companion/buddy.py` L3767 (image path) -> `<comfyui_dir>\ComfyUI\output`
- `launchers/BuddyStack.ps1` `$COMFY_PY` -> `<comfyui_dir>\python_embeded\pythonw.exe`

### Hole 3 — Model destination folders (distinct from downloading models)

Downloading the models isn't enough; they must land in exact folders: Ollama
models under `OLLAMA_MODELS`, and the three `.safetensors` under the ComfyUI
`models/unet`, `models/clip`, `models/vae`. Already documented in MODELS.md.

**Fix:** installer responsibility (place files + set `OLLAMA_MODELS` from
config's `ollama_models`). No source change needed beyond the launcher/Ollama
env var already reading config. Keep MODELS.md as the source of truth for
destinations.

### Hole 4 — Home Assistant plugin as a real functional toggle

The brain's HTTP handler serves eight routes. Four are core (needed by the
companion and watchdog): `/status`, `/chat`, `/generate`, `/evict`. Four are the
Ollama-facade that ONLY Home Assistant uses: `/api/version`, `/api/tags`,
`/api/show`, `/api/chat` (all share the `/api/` prefix).

**Architecture finding (decides install-vs-enable):** the HA routes are NOT a
separate program. They are interleaved into the brain's single HTTP handler
(`do_GET`/`do_POST`/`do_HEAD`/`do_OPTIONS`) and the `/api/chat` path calls the
SAME core (`ollama_native_chat` -> `buddy_respond`/`ollama_chat`) the companion
uses. So the HA endpoint cannot be cleanly "not installed" without real
refactoring to split the handler into its own module.

**Decision:** use a runtime **enable/disable** toggle, and name the installer
checkbox **"Enable Home Assistant"** (not "Install"). This matches Clover's
stated fallback: since the HA code shares the necessary brain core, switching it
off is the acceptable route. The config's `home_assistant_enabled` flag gates
the `/api/*` routes (and the HA-oriented HEAD/OPTIONS behavior): when false, the
brain 404s those paths so the endpoint genuinely does not function, even though
the code still physically lives in the file. The companion path is untouched
either way. Clean edit because the routes are already `/api/`-prefixed.

Installer behavior for the checkbox:
- checked -> `home_assistant_enabled: true`; after install, show the HA
  connection values (URL `http://<host>:8766`, model `buddy`) and optionally
  open the firewall port.
- unchecked -> `home_assistant_enabled: false`; brain runs companion-only.

Future option (not now): if the HA code should physically not ship, split the
`/api/*` handlers into a separate module the brain imports only when enabled.
Bigger change to the brain's core file; deferred unless there's a reason.

Note: `owui_api_key.txt` / Open WebUI is **fully retired** — confirmed no live
reference in the companion or brain (only a "no Open WebUI" note in a comment).
It gates nothing; drop the reference wherever it appears in docs.

### Hole 5 — Emoji font + Tkinter (real cross-platform concern)

Multi-platform is now a goal: Windows and Linux for everything, and eventually
an Android/APK build of the **companion only**. Two things in the companion
would block that and should be understood now (not necessarily fixed now):

- **Emoji font path** — `companion/buddy.py` loads `C:\Windows\Fonts\
  seguiemj.ttf` by absolute path. On Linux this file doesn't exist; on Android
  neither the path nor the font do. Fix direction: resolve an emoji font from
  config or a platform-appropriate default, with the current Windows path as
  the Windows default.
- **Tkinter UI** — the companion renders with Tkinter, which is desktop-only and
  will NOT run on Android. An APK would need a different UI layer (the render
  logic in `skin_highres.py` is more portable than the Tkinter window/chrome in
  `buddy.py`). This is a large future rework, well beyond the config refactor,
  and is called out here only so the APK goal isn't a surprise later.

For the config refactor itself: the immediate obligation is simply to stop
baking Windows-only absolute paths into shared code, and to use
`os.path`/`pathlib` with platform-aware defaults so Linux works and Android
stays reachable later.

## The other installer toggles (no source change, launcher/installer only)

- **Watchdog install or not** — `watchdog_enabled` in config; installer places
  the watchdog files or not, and the launcher's Full mode skips starting it when
  false. `BuddyStack.ps1` already health-checks components independently, so
  skipping the watchdog is a small conditional.
- **Start with the OS** — Windows: installer creates (or not) a startup entry
  pointing at the launcher. Linux: the equivalent is a systemd user service or
  autostart `.desktop` entry. The launchers themselves are currently Windows-only
  (PowerShell + VBS); a Linux port needs shell-script equivalents of
  `BuddyStack.ps1` and the `.vbs` shortcuts. Known future task, not part of the
  config refactor.
- **Desktop icons / shortcuts** — installer runs the equivalent of
  `_install_shortcuts.ps1` (Windows) or drops `.desktop` files (Linux), or not.
  Pure installer action.

## Recommended execution order (one component at a time, verified live)

The safest path is a small shared config loader plus per-component edits, each
tested against the live running setup before moving on. Nothing changes behavior
today because every config value defaults to the current hardcoded path.

1. **Write the config loader + defaults.** A tiny helper (one for Python, one
   for PowerShell) that finds `buddy_config.json`, reads a key, and falls back
   to the current literal if the file/key is absent. Ship the loader with
   defaults equal to today's paths. Result: zero behavior change, everything
   still runs.

2. **Brain** — replace L12/L18/L248 literals with config reads. Restart brain,
   verify `/status`, `/chat`, image gen, and (for now) the HA routes all still
   work. Reload HA integration per the runbook.

3. **Companion** — replace L27 `BASE` and L3767 image path with config reads.
   Restart pet, verify chat, bubble, emotes, image display.

4. **Watchdog** — replace L12 `PET_BASE`. Restart watchdog, verify it still
   writes `llm_status.json` to the shared dir and the pet reads it.

5. **HA toggle** — gate the `/api/*` routes on `home_assistant_enabled`. Test
   both states: enabled (HA connects) and disabled (those routes 404, companion
   unaffected).

6. **Launchers** — read config for `comfyui_dir`, `shared_dir`, component dirs;
   add the `watchdog_enabled` conditional. Keep the `%LOCALAPPDATA%` python/
   ollama paths already done.

7. **Update docs** — ARCHITECTURE.md gets a "Configuration" section describing
   `buddy_config.json`; RESTORE-from-scratch steps reference it.

8. **Confirm the repo is installer-ready** — no machine-specific literals remain
   in committed source (they've moved to the config file, which is NOT
   committed; only a `buddy_config.example.json` is).

## What this deliberately does NOT do

- It does not build the installer.
- It does not download or relocate models, ComfyUI, or Ollama.
- It does not change any emote, animation, persona, or TTS behavior.
- It does not touch the live personal setup's paths except where a verified
  edit swaps a literal for a config-read that resolves to the same value.
- It does not port anything to Linux or Android yet. It only stops baking
  Windows-only paths into shared code so those ports stay possible. The Linux
  launcher scripts and the Android UI layer are separate, larger future tasks
  (noted in Hole 5 and the toggles section).

## Resolved questions

- **Open WebUI / `owui_api_key.txt`:** fully retired. No live reference in the
  companion or brain. Gates nothing; drop the reference in docs.
- **HA "install" vs "enable":** the HA routes share the brain's core and aren't
  a separate program, so the checkbox is **"Enable Home Assistant"** (runtime
  toggle), per Hole 4.

## Cross-platform stance (Windows now, Linux near-term, Android/APK later)

- **Everything portable now:** all four components should read paths from config
  and use `os.path`/`pathlib`, so the same source runs on Windows and Linux once
  the Linux launcher scripts exist.
- **Companion is the APK candidate** and needs the most care: its Tkinter UI and
  Windows emoji-font assumption are the two blockers (Hole 5). The config
  refactor removes the path assumption; the UI rework is a separate future
  project.
- **Brain / watchdog / launchers are desktop-only** (ComfyUI, Ollama, OS
  service management) and are not APK targets, as Clover noted.

## Installer scenario: local (all-in-one) vs remote (companion-only)

The installer should ask up front whether it's setting up **this machine as the
full stack** or **as a companion-only / remote machine**:

- **Full / local machine:** install all components (companion, brain, watchdog,
  launchers), fetch ComfyUI + Ollama + models, write a `buddy_config.json` with
  local paths and `brain_url: http://localhost:8766`. Create all launcher
  shortcuts.
- **Remote / companion-only machine:** install ONLY the companion and its
  launcher. Do NOT install the brain, watchdog, ComfyUI, or Ollama. Ask for the
  brain endpoint and write it to `brain_url` (e.g. `http://<brain-host>:8766`,
  or a tunnel DNS name for outside-the-network access). Create ONLY the
  companion desktop launcher — the full-stack / stop / brain launchers aren't
  relevant on a companion-only box.

The code already supports both: the companion reaches the brain purely through
the config's `brain_url`, so no source differs between the two installs — only
which files get placed and what the config says. Most companion-only machines
reach the brain over the LAN; exposing it beyond the LAN (e.g. a Cloudflare
tunnel) changes only the endpoint string in `brain_url`, not the mechanism.

## Status after the config refactor (done)

Implemented and verified live:
- `buddy_config.py` loader (stdlib-only, cross-platform, BOM-tolerant,
  integrity-level-proof search order) in every component.
- Brain, companion, watchdog, and the PowerShell launcher all read paths from
  config with defaults equal to the previous hardcoded values.
- Home Assistant enable/disable toggle (gates the `/api/*` routes).
- Watchdog enable/disable toggle in the launcher.
- `brain_url` config key for companion-only / remote machines.

Still deferred to the installer or later work: model download/placement, the
Windows emoji-font path, Linux launcher scripts, and the Android companion UI.
