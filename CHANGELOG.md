# Changelog

All notable changes to Buddy AI are documented here.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/),
and the project aims to follow semantic versioning once past alpha.

## [Unreleased]

Work since `v0.1.0-alpha`, focused on the desktop pet's input cluster and a
web-search tool for the brain.

### Added

- **Vision attach — file picker.** A paperclip button in the talk box opens a
  file dialog; the chosen image is attached as context and sent to the brain's
  vision pipeline with the next message. A green check marks the attached state.
- **Vision attach — webcam.** A camera button opens a live preview and captures
  a single frame as image context. The camera is probed across indices and
  backends (it is not always on index 0). The preview window sits to the left of
  the talk box.
- **Clear / cancel attachments.** Clicking the green-check button clears the
  pending attachment; attaching via the other input (file ↔ webcam) swaps
  cleanly instead of stacking.
- **Reach-and-pocket attach animation.** When you attach a file or capture a
  frame, Buddy reaches an empty hand out and holds it while you pick; on success
  the file's thumbnail (or a type icon for non-visual files) appears in his paw,
  he presents it for a beat, then carries it in and pockets it. Cancelling
  returns the empty hand to idle. Built by rotating his real arm — no
  hand-rolled limb.
- **Hide to system tray.** The right-click menu can hide Buddy to a tray icon;
  double-click the icon to bring him back, or exit from it.
- **Web search tool (brain).** The brain can call a Brave-backed web search for
  current-information questions, with a broadened trigger gate and a
  retry/fallback on empty replies.

### Changed

- The attach/webcam flow shares a single pending-image slot and one green-check
  affordance, so only one attachment is active at a time.

### Fixed

- **Arm clipping during the pocket sweep.** The reach reused the wave-arm patch,
  whose canvas only had room above the shoulder (it was sculpted for an upward
  wave). A downward-pointing arm ran off the bottom of that canvas and was
  clipped to a rectangle, so the arm appeared to vanish into a transparent box
  mid-sweep. The arm is now padded onto a larger canvas centered on the shoulder
  before rotating, so it has room in every direction. All 65 emotes remain
  byte-for-byte identical.
- **File dialog covering the pet.** The native Windows file dialog opened on top
  of Buddy. It is now lifted above him via the Win32 API (found by window title,
  moved on a side thread while the modal dialog blocks the main thread). An
  earlier invisible-parent approach was dropped because it disturbed z-order.

## [0.1.0-alpha] - 2026-07

Initial alpha: the desktop pet (65 emotes, real-time animation, speech
bubbles), the brain (persona, tool-calling, image generation, vision), the
gaming watchdog, a PowerShell stack orchestrator, and an Inno Setup installer.
See `installer/RELEASE-NOTES-v0.1.0-alpha.md`.
