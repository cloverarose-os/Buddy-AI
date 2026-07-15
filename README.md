# Buddy AI

A local, self-hosted AI companion: a friendly bear in an alien jumpsuit who
lives on your desktop, animates in real time, talks to you, reacts with a large
roster of expressive emotes, and can generate images. Everything runs on your
own machine.

This repository holds the whole Buddy AI project. It is built up in stages, and
several of its parts are now here.

## Components

| Folder        | What it is                                                     | Status     |
|---------------|----------------------------------------------------------------|------------|
| `companion/`  | The desktop pet: rendering, animation, the 65-emote system, chat box, speech bubble. | published |
| `brain/`      | The local AI service: persona, tool-calling, image generation, vision, and the Home Assistant endpoint. | published |
| `watchdog/`   | GPU watchdog: yields the GPU to games, warms the model back up when idle. | published |
| `launchers/`  | One PowerShell orchestrator (+ shortcuts) that starts the whole stack in order, health-checked. | published |
| installer     | One installer to set up a working Buddy and all dependencies.  | planned    |

## What runs Buddy

Buddy is made of the four components above plus some external pieces that are
**not** included in this repo because they're large and already distributed
elsewhere:

- **ComfyUI** (portable) — provides the image-generation runtime and the
  embedded Python the brain runs under.
- **Ollama** — serves the chat, vision, and embedding models.
- **Model weights** — pulled from Hugging Face and Ollama. See
  [`docs/MODELS.md`](docs/MODELS.md) for the exact list and where each goes.

So this repository is the **source and configuration** for Buddy. Until the
installer exists, standing up a fully working, talking, image-generating Buddy
from scratch also means installing ComfyUI, Ollama, and the model weights by
hand (documented in the docs). The planned installer will automate all of that.

## The emotes

Buddy has **65 distinct emotes**, each reviewed and hand-tuned — everyday moods
(happy, thinking, sleepy), a full laughter set, a sad cluster, a five-step anger
ladder (mad → angry → furious), and playful states (mischievous, silly, cool,
nerdy). The brain chooses one per reply, via an emoji in the text (which wins)
or an explicit JSON `emote` tag.

## The speech bubble

When Buddy replies, a comic-style bubble appears above his head. It stretches
vertically to fit the message, growing upward to a cap of about twice its base
height; longer replies scroll smoothly inside with a small themed indicator.
The bubble's shape never distorts — only its height changes.

## Home Assistant (optional)

Home Assistant support is **optional** — Buddy is fully functional without it.
If you run Home Assistant, the brain exposes an Ollama-native endpoint that HA's
Ollama integration can point at, so you can talk to Buddy through Assist and
hear replies via a TTS engine like Piper. See
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md#the-home-assistant-plugin-optional).

## Running from source (developer preview)

> **Note:** early, source-first preview. Windows-first, and some paths are
> currently hardcoded; the planned installer will make these configurable and
> bundle the dependencies. See "Current limitations" in the architecture doc.

1. Install [Ollama](https://ollama.com) and pull the models in
   [`docs/MODELS.md`](docs/MODELS.md).
2. Install ComfyUI (portable) and place the image weights per
   [`docs/MODELS.md`](docs/MODELS.md).
3. Install Python deps: `pip install -r requirements.txt` (see the file for the
   two-environment note).
4. Start the stack with `launchers/BuddyStack.ps1 -Mode Full` (or just the pet
   with `-Mode Pet`).

## Documentation

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — how the four components fit
  together and talk.
- [`docs/MODELS.md`](docs/MODELS.md) — the external model dependencies.

## Contributing

Issues and pull requests welcome. Because the emote set is hand-tuned and
reviewed visually, changes touching existing emotes should include before/after
notes on how the animation looks, not just that it runs.
