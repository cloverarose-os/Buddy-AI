"""
buddy_config.py - shared, dependency-free configuration loader for every Buddy
component (companion, brain, watchdog). Standard library only, so it stays
portable across Windows/Linux (and reachable for a future Android build).

Design:
- Looks for buddy_config.json at a platform-appropriate location, overridable
  with the BUDDY_CONFIG environment variable.
- Every value has a DEFAULT equal to the current hardcoded path, so until an
  installer writes a config file, behavior is byte-for-byte the same as before.
- Never assumes Windows: paths are built with os.path, and per-OS defaults are
  chosen at runtime.

This file is intentionally self-contained and copied into each component folder,
so no component depends on another's directory being importable.
"""
import os
import json
import platform


def _is_windows():
    return platform.system() == "Windows"


def _config_path():
    """Where buddy_config.json lives. Returns the FIRST candidate that exists,
    or the OS-standard location if none exist yet.

    Search order (first existing wins):
      1. BUDDY_CONFIG env var (explicit override)
      2. next to this component (same dir as buddy_config.py), and its parent
         - this is integrity-level-proof: a config the installer drops into the
           install root is readable by each component at its own integrity level,
           unlike %LOCALAPPDATA% which can be UAC-virtualized differently for
           elevated vs medium-integrity processes.
      3. the OS-standard per-user location (%LOCALAPPDATA% / XDG_CONFIG_HOME)
    """
    override = os.environ.get("BUDDY_CONFIG")
    if override:
        return override

    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, "buddy_config.json"),
        os.path.join(os.path.dirname(here), "buddy_config.json"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c

    if _is_windows():
        base = os.environ.get("LOCALAPPDATA",
                              os.path.expanduser(r"~\AppData\Local"))
        std = os.path.join(base, "BuddyAI", "buddy_config.json")
    else:
        base = os.environ.get("XDG_CONFIG_HOME",
                              os.path.expanduser("~/.config"))
        std = os.path.join(base, "buddyai", "buddy_config.json")
    if os.path.exists(std):
        return std
    # nothing exists yet: return the OS-standard path (so a first write has a
    # sensible home), but callers treat a missing file as "use defaults".
    return std


# --- current-machine defaults (EXACTLY today's hardcoded values) -----------
# These make the loader a no-op until a real config file exists: every getter
# returns the same literal the code used before the refactor.
_WINDOWS_DEFAULTS = {
    "companion_dir": r"C:\ClaudeBuddy",
    "brain_dir":     r"G:\Buddy AI\Brain",
    "watchdog_dir":  r"G:\Buddy AI\Watchdog",
    "comfyui_dir":   r"G:\Buddy AI\ComfyUI_windows_portable",
    "ollama_models": r"G:\Ollama\models",
    # shared_dir defaults to the companion dir, because that's where the
    # contract files (llm_status.json, inbox.txt, ...) live today.
    "shared_dir":    r"C:\ClaudeBuddy",
    "ollama_url":    "http://localhost:11434",
    # brain_url is where the COMPANION reaches the brain. localhost for an
    # all-in-one machine; a companion-only / remote machine sets this to the
    # brain host, e.g. "http://brain-host:8766" or a tunnel DNS name.
    "brain_url":     "http://localhost:8766",
    # Brave Web Search API key (free tier). Empty = web search disabled; the
    # brain simply won't offer the tool. Machine-local, never committed.
    "brave_api_key": "",
    "home_assistant_enabled": True,
    "watchdog_enabled": True,
}


def _defaults():
    """Per-OS defaults. Windows uses the current machine's real layout; other
    platforms get sensible relative-to-home defaults (used only once someone
    actually runs on Linux without a config file)."""
    if _is_windows():
        return dict(_WINDOWS_DEFAULTS)
    home = os.path.expanduser("~")
    root = os.path.join(home, "BuddyAI")
    return {
        "companion_dir": os.path.join(root, "companion"),
        "brain_dir":     os.path.join(root, "brain"),
        "watchdog_dir":  os.path.join(root, "watchdog"),
        "comfyui_dir":   os.path.join(root, "ComfyUI"),
        "ollama_models": os.path.join(root, "models", "ollama"),
        "shared_dir":    os.path.join(root, "shared"),
        "ollama_url":    "http://localhost:11434",
        "brain_url":     "http://localhost:8766",
        "brave_api_key": "",
        "home_assistant_enabled": True,
        "watchdog_enabled": True,
    }


# --- public API ------------------------------------------------------------
_cache = None


def _load():
    """Read + cache the config file merged over defaults. Missing file or bad
    JSON falls back cleanly to defaults (so a broken config never breaks Buddy;
    it just behaves like the pre-config code)."""
    global _cache
    if _cache is not None:
        return _cache
    cfg = _defaults()
    path = _config_path()
    try:
        # utf-8-sig tolerates a UTF-8 BOM (PowerShell/Notepad often add one);
        # plain utf-8 would raise on the BOM and silently drop the whole config.
        with open(path, "r", encoding="utf-8-sig") as f:
            user = json.load(f)
        if isinstance(user, dict):
            cfg.update({k: v for k, v in user.items() if v is not None})
    except (OSError, ValueError):
        pass  # no file / unreadable / bad JSON -> defaults only
    _cache = cfg
    return cfg


def get(key, default=None):
    """Get a single config value (falls back to the per-OS default, then to the
    caller's default)."""
    cfg = _load()
    if key in cfg:
        return cfg[key]
    return default


def path_in(dir_key, *parts):
    """Convenience: join a configured directory with sub-parts, OS-correctly.
    e.g. path_in('shared_dir', 'llm_status.json')."""
    base = get(dir_key)
    return os.path.join(base, *parts)


def reload():
    """Drop the cache (for tests or after the installer writes a new file)."""
    global _cache
    _cache = None
