# Buddy AI

A desktop companion: a friendly bear in an alien jumpsuit who lives on your
desktop, animates in real time, talks to you, and reacts with a large roster
of expressive emotes. Buddy is driven by a local AI "brain," so he responds in
character to whatever you say — and shows how he feels with the matching
animation.

This repository is the home of the whole Buddy AI project. It is being built
up in stages; the first piece published here is **Buddy Companion**, the
desktop pet itself (the part you see and talk to).

## Project status

Buddy AI is under active development and is organized into a few parts that
will land here over time:

- **Buddy Companion** — the desktop pet: rendering, animation, the chat box,
  and the 65-emote expression system. *(published — this repo, `src/`)*
- **Buddy Brain** — the local AI service that decides what Buddy says and which
  emotion he shows. *(planned)*
- **Home Assistant plugin** — an optional integration for people who run
  Home Assistant, exposing Buddy as an endpoint. *(planned, optional)*
- **Installer** — a single installer that sets up a working Buddy, all
  dependencies, and the brain, with the Home Assistant plugin offered as an
  optional add-on. *(planned)*

Until the installer lands, this repo is source-first: it contains the Buddy
Companion code and documentation, intended for developers who want to read,
run, or contribute.

## What's in this repository

```
Buddy-AI/
├─ src/
│  ├─ buddy.py          # the desktop pet: window, animation loop, chat box,
│  │                    #   speech bubble, emote triggering, local HTTP API
│  └─ skin_highres.py   # the renderer: draws Buddy and every emote at high
│                       #   resolution (PIL, 4x supersampled)
├─ docs/
│  └─ ARCHITECTURE.md   # how the pieces fit together
├─ requirements.txt
├─ .gitignore
└─ README.md
```

## The emotes

Buddy has **65 distinct emotes**, each reviewed and hand-tuned — from everyday
moods (happy, thinking, sleepy) through a full laughter set, a sad cluster, a
five-step anger ladder (mad → angry → furious), and playful states (mischievous,
silly, cool, nerdy). Each has its own face and, where it matters, its own
animated gesture (waving, paw-rubbing, forehead-wiping, and so on).

Buddy shows an emote in one of two ways, both driven by the reply he produces:

1. **Emoji in the reply text** — if his message contains a known emotion emoji,
   that wins and drives the animation.
2. **An explicit JSON `emote` tag** — the brain returns
   `{"text": "...", "emote": "happy"}`; the tag names the emote to play.

## How Buddy talks (the speech bubble)

When Buddy replies, a comic-style speech bubble appears above his head. It
stretches vertically to fit the message, growing upward to a cap of about twice
its base height; longer replies scroll smoothly inside the bubble with a small
themed scroll indicator. The bubble shape itself never distorts — only its
height changes.

## Running Buddy Companion (developer preview)

> **Note:** This is an early, source-first preview. Buddy Companion currently
> expects to run on Windows and to find its files under a fixed path, and it
> talks to the (not-yet-published) Buddy Brain service on `localhost:8766`.
> These assumptions will be removed by the forthcoming installer, which will
> configure paths and bundle the brain. Until then, running from source takes
> a little manual setup. See **Current limitations** below.

### Requirements

- **Python 3.11+**
- **Pillow** (`pip install -r requirements.txt`)
- **tkinter** — included with the standard python.org installer on Windows and
  macOS; on Linux install it via your package manager (e.g.
  `sudo apt install python3-tk`).

### Steps

```bash
# 1. install dependencies
pip install -r requirements.txt

# 2. run the pet
python src/buddy.py
```

Buddy appears on your desktop and begins idling. Double-click him to open the
chat box. Without the brain running he can still be driven directly (see
Architecture), but full conversation needs the Buddy Brain service.

## Current limitations (being addressed by the installer)

- **Windows-first.** The renderer and window logic are developed and tested on
  Windows. Other platforms are not yet supported.
- **Fixed base path.** `buddy.py` currently uses a hardcoded working directory.
  The installer will make this configurable.
- **Brain not included yet.** Conversation requires the Buddy Brain service on
  `localhost:8766`, which will be published separately.
- **No packaged release yet.** For now this is run from source.

## Contributing

Issues and pull requests are welcome. Because the emote set is hand-tuned and
reviewed visually, changes that touch existing emotes should include before/after
notes on how the animation looks, not just that it runs.
