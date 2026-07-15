# Claude Gaming Watchdog - games get the GPU, the LLM yields.
# Polls for gaming activity; evicts Ollama models from VRAM when a
# game is detected, keeps the HA model warm when idle.
# Status: C:\ClaudeBuddy\llm_status.json | Log: watchdog.log
# Config: watchdog_config.json (add game exe names there)
import os, sys, time, json, ctypes, subprocess
import urllib.request

# Watchdog's own home (config + log live beside the script)
BASE = os.path.dirname(os.path.abspath(__file__))
# Pet's home - shared contract files the pet and brain read/write
PET_BASE = r"C:\ClaudeBuddy"
CFG_PATH = os.path.join(BASE, "watchdog_config.json")
STATUS = os.path.join(PET_BASE, "llm_status.json")
LOGF = os.path.join(BASE, "watchdog.log")
INBOX = os.path.join(PET_BASE, "inbox.txt")
API = "http://localhost:11434"

DEFAULT_CFG = {
    "poll_seconds": 10,
    "warm_on_idle": True,
    "warm_model": "qwen3.5:9b",
    "buddy_notifications": True,
    "gpu_util_threshold": 50,
    "game_processes": [
        "BONELAB.exe", "VRChat.exe", "Beat Saber.exe",
        "Lethal Company.exe", "Teardown.exe", "gmod.exe", "hl2.exe",
        "People Playground.exe", "REPO.exe", "FNAF_SOTM.exe",
        "BladeAndSorcery.exe", "Hard Bullet.exe", "portal2.exe",
        "BEHEMOTH.exe", "PoppyPlaytime.exe", "javaw.exe",
        "UltimateCustomNight.exe", "RustClient.exe"],
    "vr_processes": ["vrcompositor.exe", "vrmonitor.exe"],
    "fullscreen_whitelist": [
        "explorer.exe", "msedge.exe", "chrome.exe", "opera.exe",
        "operagx.exe", "firefox.exe", "vlc.exe", "Claude.exe",
        "SKYBOX.exe", "Spotify.exe", "Discord.exe"]}

def load_cfg():
    try:
        with open(CFG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        for k, v in DEFAULT_CFG.items():
            cfg.setdefault(k, v)
        return cfg
    except (OSError, ValueError):
        with open(CFG_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CFG, f, indent=2)
        return dict(DEFAULT_CFG)

def log(msg):
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        # Rotate: if log exceeds 1MB, keep only the last ~200 lines
        if os.path.exists(LOGF) and os.path.getsize(LOGF) > 1_000_000:
            with open(LOGF, "r", encoding="utf-8") as f:
                lines = f.readlines()[-200:]
            with open(LOGF, "w", encoding="utf-8") as f:
                f.writelines(lines)
        with open(LOGF, "a", encoding="utf-8") as f:
            f.write(f"[{stamp}] {msg}\n")
    except OSError:
        pass

def buddy_say(text, emote):
    try:
        with open(INBOX, "w", encoding="utf-8") as f:
            json.dump({"text": text, "emote": emote}, f)
    except OSError:
        pass

def api(path, payload=None, timeout=20):
    url = API + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode() or "{}")

def running_procs():
    try:
        out = subprocess.run(
            ["tasklist", "/fo", "csv", "/nh"], capture_output=True,
            text=True, timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW)
        names = {}
        for line in out.stdout.splitlines():
            parts = line.strip('"').split('","')
            if len(parts) >= 2:
                names[parts[0].lower()] = int(parts[1])
        return names
    except (OSError, ValueError, subprocess.SubprocessError):
        return {}

def gpu_util():
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu",
             "--format=csv,noheader,nounits"], capture_output=True,
            text=True, timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW)
        return int(out.stdout.strip().splitlines()[0])
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return 0

def foreground_exe(procs_by_pid):
    try:
        u = ctypes.windll.user32
        hwnd = u.GetForegroundWindow()
        if not hwnd:
            return None, False
        pid = ctypes.c_ulong()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        rect = ctypes.wintypes.RECT()
        u.GetWindowRect(hwnd, ctypes.byref(rect))
        sw = u.GetSystemMetrics(0)
        sh = u.GetSystemMetrics(1)
        full = (rect.right - rect.left) >= sw and \
               (rect.bottom - rect.top) >= sh
        return procs_by_pid.get(pid.value), full
    except OSError:
        return None, False

def detect_gaming(cfg):
    procs = running_procs()  # name.lower() -> pid
    games = {p.lower() for p in cfg["game_processes"]}
    vr = {p.lower() for p in cfg["vr_processes"]}
    hit = games & set(procs)
    if hit:
        return True, f"game process: {sorted(hit)[0]}"
    hitvr = vr & set(procs)
    if hitvr:
        return True, f"VR session: {sorted(hitvr)[0]}"
    util = gpu_util()
    if util >= cfg["gpu_util_threshold"]:
        by_pid = {v: k for k, v in procs.items()}
        fg, full = foreground_exe(by_pid)
        wl = {p.lower() for p in cfg["fullscreen_whitelist"]}
        if fg and full and fg not in wl and fg != "ollama.exe":
            return True, f"fullscreen+GPU {util}%: {fg}"
    return False, ""

def loaded_models():
    try:
        d = api("/api/ps")
        return [m["name"] for m in d.get("models", [])]
    except Exception:
        return []

def unload_all():
    evicted = []
    for name in loaded_models():
        try:
            api("/api/generate", {"model": name, "keep_alive": 0})
            evicted.append(name)
        except Exception as e:
            log(f"unload failed for {name}: {e}")
    return evicted

def warm(model):
    try:
        api("/api/generate", {"model": model, "keep_alive": -1},
            timeout=120)
        return True
    except Exception as e:
        log(f"warm failed: {e}")
        return False

def comfy_free():
    """Ask Buddy AI to drop the image model from VRAM (no-op if not
    running). ComfyUI's own server is retired - Buddy AI holds these
    weights natively now, in-process."""
    try:
        req = urllib.request.Request(
            "http://localhost:8766/evict",
            data=b"{}", headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10).read()
    except Exception:
        pass

def write_status(gaming, reason, loaded):
    try:
        with open(STATUS, "w", encoding="utf-8") as f:
            json.dump({
                "gaming": gaming, "reason": reason,
                "loaded_models": loaded,
                "updated": time.strftime("%Y-%m-%d %H:%M:%S")}, f)
    except OSError:
        pass

def main():
    import ctypes.wintypes  # noqa - ensure loaded
    once = "--once" in sys.argv
    cfg = load_cfg()
    gaming = None  # unknown -> force first transition handling
    log("watchdog started")
    while True:
        cfg = load_cfg()
        now_gaming, reason = detect_gaming(cfg)
        if now_gaming and loaded_models():
            evicted = unload_all()
            if evicted:
                log(f"evicted {evicted} ({reason})")
        if now_gaming:
            comfy_free()
        if now_gaming != gaming:
            if now_gaming:
                log(f"GAMING ON - {reason}")
                if cfg["buddy_notifications"]:
                    buddy_say("Game on! Brain unloaded - all 12GB of "
                              "VRAM is yours. Have fun!", "sleepy")
            else:
                log("GAMING OFF - idle mode")
                if cfg["warm_on_idle"]:
                    warm(cfg["warm_model"])
                if cfg["buddy_notifications"] and gaming is not None:
                    buddy_say("Game closed - brain back online and "
                              "warmed up for Home Assistant.", "happy")
            gaming = now_gaming
        write_status(now_gaming, reason, loaded_models())
        if once:
            print(json.dumps({"gaming": now_gaming, "reason": reason,
                              "loaded": loaded_models()}))
            return
        time.sleep(cfg["poll_seconds"])

if __name__ == "__main__":
    import ctypes.wintypes
    main()
