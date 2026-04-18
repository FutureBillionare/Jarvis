# HUBERT UI Redesign

**Date:** 2026-04-06  
**Status:** Approved

## Overview

Redesign the HUBERT desktop UI from a two-column layout with a detached HUD overlay into a three-column always-on dashboard. HUBERT gains a voice-animated sphere, edge-tts speech, and fully interactive swarm graph navigation. The color scheme and SwarmPanel logic are unchanged.

---

## Layout

Three-column grid inside `HubertApp._build_ui()`:

| Column | Widget | Width |
|--------|--------|-------|
| 0 | `SwarmPanel` | 300px fixed |
| 1 | Chat column (sphere + chat + input) | flex (expands) |
| 2 | `HUDPanel` | 160px fixed |

All three columns fill the full height of the body. Column dividers are draggable — the user can resize col 0 and col 2 by dragging the separator. Double-clicking a separator resets its column to the default width.

The `HUD` button is removed from the header. `HUDOverlay` class is deleted entirely.

---

## New Components

### SphereWidget (`tk.Canvas`)

Embedded at the top of the chat column, above the chat scroll area. Height: 110px.

**States:**
- **Idle** — dim cyan orb, slow 2s breathe cycle, no rings
- **Speaking** — bright orb, three concentric rings animate outward in sequence (delays: 0s, 0.5s, 1.0s), rings fade as they expand
- **Muted** — orb turns purple, rings stop, a small 🔇 icon flashes on the orb for 1s then disappears

**Interactions:**
- Single click → toggle mute. Muted state suppresses `speak_async()` calls without stopping mid-sentence.
- State is toggled via a `self._muted: bool` flag on the app.

**Animation:** Driven by `tk.Canvas.after(33, ...)` loop (≈30fps). Two internal state vars: `self._speaking: bool` and `self._muted: bool`, both set via `ui_bridge` commands (`sphere_speaking`, `sphere_muted`).

---

### HUDPanel (`ctk.CTkFrame`)

Permanent right column. Polls live data in a background thread every 1s via `psutil`. Updates labels on the main thread via `self.after(0, ...)`.

**Sections (top to bottom):**
1. Header — `◈ HUD` label
2. CPU % — value label + 3px progress bar
3. RAM % — value label + 3px progress bar
4. NET — combined bytes/s label (↑↓)
5. Divider
6. Clock — `HH:MM` in large font, date below
7. Divider
8. Weather — fetched once at startup (same `get_weather()` call as boot screen)
9. Divider
10. Radar — 80×80px canvas with rotating sweep, two blinking dots, crosshair grid

**Expandable stats:** Clicking a CPU, RAM, or NET row toggles a 40px sparkline graph below it (rolling 60-sample history). Only one sparkline open at a time.

---

## Modified Components

### `speak_async(text)`

Replaced with `edge-tts` streaming. Voice: `en-US-GuyNeural`.

**Flow:**
1. If `self._muted` → return immediately, do not speak.
2. Push `ui_bridge.push("sphere_speaking", active=True)`.
3. Run `edge-tts` in a daemon thread: `edge_tts.Communicate(text, voice).stream()` → write audio bytes to a temp file → play with `sounddevice` (preferred) or `pygame.mixer` as alternative.
4. On completion (or error) → push `ui_bridge.push("sphere_speaking", active=False)`.
5. **Fallback:** if `edge-tts` or the audio backend is unavailable, fall back to `pyttsx3` silently.

`speak_async` is converted from a module-level function to a method on `HubertApp` so it can read `self._muted` directly.

Install: `pip install edge-tts sounddevice`.

### `_build_ui()` in `HubertApp`

- Switch body from 2-column to 3-column `grid_columnconfigure`.
- Add `SphereWidget` between header and `ChatDisplay` in the center column.
- Instantiate `HUDPanel` in column 2.
- Remove HUD button from header.
- Add draggable separator logic (see below).

### `_process_q()` — ui_bridge command handler

Add two new command handlers:
- `sphere_speaking` → call `self.sphere.set_speaking(active: bool)`
- `sphere_muted` → call `self.sphere.set_muted(active: bool)` (used if mute is triggered externally)

---

## SwarmPanel — Interactive Navigation

The existing `SwarmPanel` canvas gains mouse event bindings. The graph coordinate system uses a viewport transform: `(pan_x, pan_y, zoom)`.

**Pan:** `<Button-1>` records drag start; `<B1-Motion>` updates `pan_x/pan_y` and redraws.

**Zoom:** `<MouseWheel>` adjusts zoom (0.5× min, 3.0× max), centered on the cursor position.

**Zoom controls:** Three small buttons added to the SwarmPanel header bar: `−`, `⊙` (reset), `+`.

**Node hover tooltip:** On `<Motion>`, hit-test all node positions against cursor. If cursor is within node radius → draw a floating tooltip rectangle on the canvas with: agent name, status, current task, tool call count, last tool used.

**Node click inspector:** `<Button-1>` on a node opens a pinned inspector. The inspector is rendered as a canvas overlay in the bottom portion of the swarm canvas (or as a small `tk.Frame` popup within the SwarmPanel). Shows: name, status, task, tool call count, last tool, runtime, last 3 log lines. Click outside or click same node again to close.

**Coordinate transform helper:** All node positions stored in graph-space. Rendering applies: `screen_x = graph_x * zoom + pan_x`, `screen_y = graph_y * zoom + pan_y`. Hit-testing inverts this.

---

## Draggable Panel Dividers

A thin (5px) `tk.Frame` separator widget placed between each column pair. Binds `<B1-Motion>` to adjust the adjacent column's `minsize` in the grid. Double-click resets to default.

---

## What Is Unchanged

- `SwarmPanel` data model, node/edge/pulse logic, activity feed, all rendering math
- `ChatDisplay`, `InputBar`, `VoicePanel`, `MenuDrawer`
- `BootScreen`, `AnimatedLogo`
- All color constants (`BG`, `ACCENT`, `ACCENT2`, etc.)
- `JarvisCore`, `jarvis_core.py`, all tools
- `ui_bridge.py`

---

## Files Changed

| File | Change |
|------|--------|
| `main.py` | Primary change — new classes, modified layout, updated speak_async |
| `requirements.txt` (or equivalent) | Add `edge-tts`, `sounddevice` |

No new files are needed. All new classes (`SphereWidget`, `HUDPanel`) live in `main.py` alongside the existing ones.
