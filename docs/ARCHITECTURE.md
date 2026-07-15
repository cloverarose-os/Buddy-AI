# Architecture

This document describes how Buddy Companion is structured and how it fits into
the wider Buddy AI project.

## Overview

Buddy Companion is a **thin display/animation client**. It does not contain any
AI logic itself — it renders Buddy, plays emotes, shows a chat box, and relays
what you type to the Buddy Brain service, then displays whatever the brain sends
back. Keeping the pet "dumb" means it always matches whatever the brain can do,
even as the brain grows.

```
   You type in the chat box
            │
            ▼
   buddy.py  ──HTTP──►  Buddy Brain (localhost:8766)   [separate service]
            ▲                    │
            │   {text, emote}    │
            └────────────────────┘
            │
            ▼
   skin_highres.py renders the face + gesture for that emote
```

## The two source files

### `src/buddy.py`

The desktop pet. Responsibilities:

- Creates the transparent always-on-top window and the 25 fps animation loop.
- Owns the **chat box** and the **speech bubble** (including the vertical-stretch
  and smooth-scroll behavior for long replies).
- Decides which emote to show, from either an emoji in the reply text or an
  explicit JSON `emote` tag, and validates it against the known emote set.
- Runs a small local **HTTP API** (port 8765) so other local tools can make
  Buddy speak or report status.
- Reads an `inbox.txt` drop file as an alternate way to trigger speech/emotes.

### `src/skin_highres.py`

The renderer. Responsibilities:

- Draws Buddy and every emote at high resolution using PIL, supersampled 4x for
  smooth edges, then downscaled.
- Builds the per-emote "plates" (the faces) and the animated gesture layers
  (arms, paws, accents like flames or sparkles).

## Runtime files (not in the repo)

At run time Buddy reads and writes several files in its working directory. These
are intentionally excluded from version control (see `.gitignore`):

- `inbox.txt` — drop a JSON `{text, emote}` here to trigger Buddy.
- `outbox.txt` — outbound channel.
- `log.txt` — conversation and emote log.
- `llm_status.json` — status written by the brain.
- `owui_api_key.txt` — a credential; **never** committed.

## Emote trigger paths

Both paths converge on a single validation point in `buddy.py`, so an unknown or
misspelled emote name always degrades safely to a default rather than crashing:

1. **Emoji path** — an emotion emoji in the reply text takes priority.
2. **JSON-tag path** — the brain's `{"emote": "..."}` names the emote.

## Where this is heading

The Buddy Brain service, an optional Home Assistant plugin, and a single
installer that wires everything together (with the Home Assistant piece offered
as an optional add-on) are planned. The installer will also remove the current
Windows-only and fixed-path assumptions.
