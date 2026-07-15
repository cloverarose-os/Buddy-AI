# Architecture

Buddy AI is a local, self-hosted AI companion. It has four cooperating
components, all running on one machine, plus external model services.

```
                    ┌─────────────────────────────────────────┐
                    │                COMPANION                 │
   you type  ─────► │  the desktop pet: window, animation,     │
                    │  65 emotes, chat box, speech bubble      │
                    └───────────────┬──────────────────────────┘
                                    │ HTTP :8766 /chat
                                    ▼
                    ┌─────────────────────────────────────────┐
                    │                  BRAIN                   │
                    │  persona, tool-calling loop, image gen,  │──► Ollama :11434
                    │  vision routing. Also exposes an Ollama- │    (chat/vision/
                    │  native /api/chat for Home Assistant.    │     embeddings)
                    └───────────────┬──────────────────────────┘
                                    │ (in-process ComfyUI nodes)
                                    ▼
                              image weights (see docs/MODELS.md)

   WATCHDOG   ── watches for games; frees the GPU for them, warms the
                 model back up when idle. Writes llm_status.json.

   LAUNCHERS  ── one PowerShell orchestrator (+ VBS shortcuts) that starts
                 the whole stack in the right order with health checks.
```

## Components

### companion/ — the desktop pet
A thin display/animation client. Renders Buddy, plays the 65-emote expression
system, shows the chat box and the vertical-stretch speech bubble, and relays
what you type to the brain over HTTP. It holds no AI logic itself, so it always
matches whatever the brain can do. Runs on a normal Python 3.11+ with Pillow.
See `companion/src/` and the emote/trigger details below.

### brain/ — the local AI service
The single service every frontend talks to. Owns the persona, the tool-calling
loop, image generation (calling ComfyUI's node classes directly, in-process),
and vision routing. It exposes two HTTP surfaces on port 8766:
- **`/chat`** — used by the companion; returns `{text, emote, image_path}`.
- **`/api/chat`** — an Ollama-native surface used by Home Assistant's Ollama
  integration (see "Home Assistant plugin" below).

The brain runs under ComfyUI's embedded Python (that environment provides
torch and the ComfyUI nodes) and talks to a local Ollama server for language
and vision. Models are external — see `docs/MODELS.md`.

### watchdog/ — the GPU watchdog
Games get the GPU; the AI yields. The watchdog polls for gaming activity (known
game processes, VR sessions, or fullscreen + high GPU use) and, when it sees a
game, evicts the models from VRAM and asks the brain to drop its image weights.
When the machine goes idle again it warms the chat model back up. It publishes
state to `llm_status.json`, which the companion reads (so Buddy can say "brain
unloaded, all the VRAM is yours"). Configure it via `watchdog_config.json`.

### launchers/ — stack orchestration
`BuddyStack.ps1` is the one launcher for the whole system, with three modes:
- **Pet** — just the companion.
- **Full** — Ollama → Brain → Watchdog → Pet, started in that order, each
  health-checked (by probing its real endpoint, not just its process) before
  the next begins.
- **Stop** — shut the whole stack down.

Add `-KeepAlive` to Full and it babysits the stack, restarting anything that
dies and logging it. The `.vbs` files are double-click shortcuts that invoke
these modes; `_install_shortcuts.ps1` sets them up.

## The Home Assistant plugin (optional)

Home Assistant support is **optional** — Buddy works fully without it. For those
who run Home Assistant, the brain exposes an Ollama-native `/api/chat` endpoint
that HA's built-in Ollama integration can point at (it advertises a model named
`buddy`). That lets you talk to Buddy through HA's Assist pipeline and, with a
TTS engine like Piper, hear the replies. The brain scrubs its spoken replies
for TTS (strips emoji, normalizes punctuation) on this path only; the companion
path keeps emoji, which drive the animations.

Because it's optional, nothing else in the project depends on Home Assistant.
The planned installer will offer the Home Assistant plugin as an opt-in add-on.

### Connecting Home Assistant to Buddy

**On the Home Assistant side you do not install anything Buddy-specific — you
use Home Assistant's own built-in Ollama integration and fill it out with the
values below.** To Home Assistant, Buddy's brain simply *looks like* an Ollama
server: it answers the same routes HA's Ollama integration expects
(`/api/version`, `/api/tags`, `/api/chat`, `/api/show`) and advertises a single
model named `buddy`. So the entire HA-side setup is "add the Ollama
integration, point it at the brain, pick the `buddy` model."

**What to enter (these are the values you'll need):**

| Field in HA's Ollama integration | Value                                    |
|----------------------------------|------------------------------------------|
| URL                              | `http://<BRAIN_HOST>:8766`               |
| Model                            | `buddy`                                  |

`<BRAIN_HOST>` is wherever Buddy's brain runs: `localhost` if it's the same
machine as Home Assistant, otherwise that machine's hostname or IP. `8766` is
the brain's default port.

Steps:

1. **Make sure the stack is running** so the brain is serving. Start it with
   the launcher (`launchers/BuddyStack.ps1 -Mode Full`); the brain listens on
   **port 8766** by default. Once the installer exists, it will start these
   services for you — the only thing you need from it is the **host and port**
   the brain ends up on (the port is the value in the table above).
2. In Home Assistant, add the **Ollama** integration
   (Settings → Devices & Services → Add Integration → Ollama). This is HA's
   own integration — there is nothing custom to install.
3. For the Ollama **URL**, enter `http://<BRAIN_HOST>:8766` from the table:
   - same machine as HA → `http://localhost:8766`
   - another machine on your network → that machine's address, e.g.
     `http://<its-hostname-or-ip>:8766`
4. When asked to pick a **model**, choose **`buddy`** (it's the only one the
   brain lists, so it should already appear in HA's model dropdown).
5. To talk to Buddy, attach that Ollama conversation agent to an **Assist**
   pipeline (Settings → Voice assistants). Add a TTS engine such as **Piper**
   to hear the replies. The brain already prepares its spoken text for TTS on
   this path (strips emoji, normalizes punctuation into pauseable sentences),
   so speech comes out clean.

Notes:
- The brain must be reachable from HA. If HA is on a different machine, the
  brain has to bind on an address that machine can reach (not just localhost),
  and any firewall must allow the port.
- **Whenever the brain restarts, reload the Ollama integration in HA** so it
  reconnects to the freshly-started brain.
- Only the port matters to HA — `8766` above is the brain's default. If a
  future installer or your own config changes it, use that value instead.

## Emote triggering

Buddy has 65 emotes. The brain picks one two ways, both driven by the reply it
produces, and they converge on a single validation point in the companion so an
unknown name degrades safely to a default rather than crashing:
1. **Emoji in the reply text** — an emotion emoji in the text wins.
2. **A JSON `emote` tag** — `{"text": ..., "emote": ...}` names the emote.

## Runtime files (not in the repo)

At run time the components read/write several files (logs, `inbox.txt`,
`outbox.txt`, `llm_status.json`, and a credential file). These are generated
locally and excluded via `.gitignore`; credentials are never committed.

## Current limitations (to be addressed by the installer)

- **Windows-first**, and several absolute paths are currently hardcoded (the
  companion's folder, `G:\Buddy AI`, the ComfyUI Python, the Ollama models
  dir). The planned installer will make these configurable.
- **Models and heavy dependencies are not included** — ComfyUI, Ollama, and the
  model weights are external (see `docs/MODELS.md`).
- **No packaged release yet** — run from source.
