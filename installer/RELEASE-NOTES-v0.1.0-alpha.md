# Buddy AI v0.1.0-alpha

A local, self-hosted AI companion for Windows: a friendly bear in an alien
jumpsuit who lives on your desktop, animates in real time, talks to you, reacts
with 65 hand-tuned emotes, and can generate images - all running on your own
machine.

**This is an early alpha.** It is feature-complete but has not been widely
installed from scratch yet. Expect rough edges, and please report issues.

## Requirements (full install)

- Windows 10/11 (64-bit)
- An **NVIDIA RTX GPU** with CUDA - an **RTX 4070 (12 GB) is the baseline**
- About **40 GB** of free disk space
- An internet connection (the installer downloads ComfyUI, Ollama, and the models)

The installer can also do a **companion-only** install for a second machine that
just shows the pet and talks to a Buddy brain running elsewhere - that needs
very little space and no GPU.

## Installing

1. Download `BuddyAI-Setup-v0.1.0-alpha.exe` below.
2. Run it. Choose **Full install** (this machine runs everything) or
   **Companion only** (talks to a brain on another machine).
3. Pick an install location, choose your options (Home Assistant, watchdog,
   startup, shortcuts), and confirm. The installer handles the rest.

## Home Assistant (optional)

If you enable it, Buddy's brain exposes an Ollama-compatible endpoint. In Home
Assistant, add the Ollama integration, point it at `http://<this-machine>:8766`,
and choose the `buddy` model. See the docs for details.

## Notes

- Not code-signed yet, so Windows SmartScreen may warn on first run
  ("More info" -> "Run anyway").
- Source, docs, and the installer build scripts are in this repository.
