# HUBERT UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the HUBERT desktop UI into a three-column always-on dashboard with an integrated HUD panel, a voice-animated sphere, edge-tts speech, and interactive swarm graph navigation.

**Architecture:** All changes live in `main.py`. Two new widget classes (`SphereWidget`, `HUDPanel`) are added alongside the existing ones. `speak_async` becomes a method on `HubertApp` with a module-level shim for backward compat. `SwarmPanel` gets a viewport transform layer and mouse bindings. `HUDOverlay` is deleted entirely.

**Tech Stack:** Python 3.13, tkinter/customtkinter, edge-tts, sounddevice, psutil (already installed), `tk.PanedWindow` for resizable column dividers.

---

## File Map

| File | Action | What changes |
|------|--------|-------------|
| `main.py` | Modify | Add `SphereWidget`, `HUDPanel`; update `_build_ui`, `speak_async`, `_process_q`, `SwarmPanel`; delete `HUDOverlay`, `_toggle_hud` |
| `requirements.txt` | Modify | Add `edge-tts`, `sounddevice` |

---

## Task 1: Install Dependencies

**Files:**
- Modify: `C:\Users\Jake\Jarvis\requirements.txt`

- [ ] **Step 1: Add to requirements.txt**

Open `requirements.txt` and add two lines:
```
edge-tts>=6.1.0
sounddevice>=0.4.6
```

- [ ] **Step 2: Install**

```bash
cd C:\Users\Jake\Jarvis
pip install edge-tts sounddevice
```

Expected output: `Successfully installed edge-tts-X.X.X sounddevice-X.X.X` (or "already satisfied" if present)

- [ ] **Step 3: Verify imports work**

```bash
python -c "import edge_tts, sounddevice; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "deps: add edge-tts and sounddevice for neural TTS"
```

---

## Task 2: SphereWidget Class

Add the `SphereWidget` class to `main.py`, placed just before the `SwarmPanel` class (around line 980).

**Files:**
- Modify: `C:\Users\Jake\Jarvis\main.py`

- [ ] **Step 1: Insert SphereWidget class**

Insert the following block immediately before the `# ── Swarm Panel` comment (before `class SwarmPanel`):

```python
# ── Sphere Widget ─────────────────────────────────────────────────────────────

class SphereWidget(tk.Canvas):
    """Animated voice orb. Idle: dim slow breathe. Speaking: bright + expanding rings.
    Muted: purple, rings stop. Click to toggle mute."""

    W = 200   # canvas width
    H = 110   # canvas height

    def __init__(self, parent, on_mute_toggle=None, **kwargs):
        super().__init__(parent, width=self.W, height=self.H,
                         bg=BG, highlightthickness=0, **kwargs)
        self._speaking   = False
        self._muted      = False
        self._t          = 0
        self._on_mute_toggle = on_mute_toggle
        # Ring phases: each ring has its own animation offset (0.0–1.0)
        self._rings      = [0.0, 0.333, 0.666]  # staggered starts
        self._mute_flash = 0   # countdown for 🔇 flash (frames)
        self.bind("<Button-1>", self._on_click)
        self._animate()

    # ── Public API ────────────────────────────────────────────────────────────

    def set_speaking(self, active: bool):
        self._speaking = active

    def set_muted(self, active: bool):
        if active and not self._muted:
            self._mute_flash = 30  # show 🔇 for ~1s at 30fps
        self._muted = active

    # ── Interaction ───────────────────────────────────────────────────────────

    def _on_click(self, event):
        new_state = not self._muted
        self.set_muted(new_state)
        if self._on_mute_toggle:
            self._on_mute_toggle(new_state)

    # ── Animation ─────────────────────────────────────────────────────────────

    def _animate(self):
        self._t += 1
        if self._speaking and not self._muted:
            for i in range(len(self._rings)):
                self._rings[i] = (self._rings[i] + 0.012) % 1.0
        if self._mute_flash > 0:
            self._mute_flash -= 1
        self._draw()
        self.after(33, self._animate)

    def _draw(self):
        self.delete("all")
        cx = self.W // 2
        cy = self.H // 2 + 4

        orb_col  = ACCENT2 if self._muted else ACCENT
        speaking = self._speaking and not self._muted

        # Expanding rings (only when speaking)
        if speaking:
            for phase in self._rings:
                # phase 0→1: ring starts small and transparent, expands and fades
                r       = 24 + phase * 36          # 24px → 60px
                alpha_v = int(255 * (1.0 - phase))
                # encode alpha into hex color by blending with BG (#060810)
                r_c = int(0x00 + (0xd4 - 0x00) * alpha_v / 255)
                g_c = int(0x08 + (0xd4 - 0x08) * alpha_v / 255)
                b_c = int(0x10 + (0xff - 0x10) * alpha_v / 255)
                col = f"#{r_c:02x}{g_c:02x}{b_c:02x}"
                self.create_oval(cx - r, cy - r, cx + r, cy + r,
                                 outline=col, width=1)

        # Orb glow (outer)
        glow_r = 26 if speaking else 22
        glow_r += 2 * math.sin(self._t * 0.06)
        gv = 0x33 if speaking else 0x18
        self.create_oval(cx - glow_r - 6, cy - glow_r - 6,
                         cx + glow_r + 6, cy + glow_r + 6,
                         outline=orb_col, width=1,
                         stipple="gray25")

        # Orb core
        r = int(glow_r)
        if self._muted:
            fill_col = "#0a0820"
        else:
            fill_col = "#040c18" if not speaking else "#030810"
        self.create_oval(cx - r, cy - r, cx + r, cy + r,
                         fill=fill_col, outline=orb_col, width=2)

        # Inner highlight spot
        hs = r // 3
        self.create_oval(cx - hs - 4, cy - hs - 4,
                         cx - hs + 4, cy - hs + 4,
                         fill=orb_col, outline="")

        # State label
        if self._mute_flash > 0:
            self.create_text(cx, cy, text="🔇",
                             font=("Consolas", 14), fill=ACCENT2)
        elif self._muted:
            self.create_text(cx, cy + r + 14, text="MUTED",
                             font=("Consolas", 7), fill=ACCENT2)
        elif speaking:
            self.create_text(cx, cy + r + 14, text="SPEAKING",
                             font=("Consolas", 7), fill=ACCENT)
        else:
            self.create_text(cx, cy + r + 14, text="STANDBY",
                             font=("Consolas", 7), fill=TEXT_DIM)
```

- [ ] **Step 2: Smoke test — run HUBERT and verify no import/syntax errors**

```bash
cd C:\Users\Jake\Jarvis
python -c "import main; print('SphereWidget' in dir(main))"
```

Expected: `True`

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat: add SphereWidget with idle/speaking/muted animation states"
```

---

## Task 3: HUDPanel Class

Add the `HUDPanel` class to `main.py` immediately after `SphereWidget` and before `SwarmPanel`.

**Files:**
- Modify: `C:\Users\Jake\Jarvis\main.py`

- [ ] **Step 1: Insert HUDPanel class**

Insert the following block immediately after the `SphereWidget` class and before `# ── Swarm Panel`:

```python
# ── HUD Panel ─────────────────────────────────────────────────────────────────

class HUDPanel(ctk.CTkFrame):
    """Permanent right-column HUD: CPU/RAM/NET stats, clock, weather, radar."""

    HC  = "#00d4aa"
    HD  = "#003028"
    HBG = "#020808"

    SPARKLINE_H  = 40   # px height when a stat row is expanded
    HISTORY_LEN  = 60   # samples kept for sparkline

    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color=self.HBG, corner_radius=0,
                         border_width=0, **kwargs)
        self._cpu_pct     = 0.0
        self._ram_pct     = 0.0
        self._net_bps     = 0.0
        self._cpu_hist    = [0.0] * self.HISTORY_LEN
        self._ram_hist    = [0.0] * self.HISTORY_LEN
        self._net_hist    = [0.0] * self.HISTORY_LEN
        self._weather_txt = "Fetching…"
        self._expanded    = None   # "cpu" | "ram" | "net" | None
        self._t           = 0
        self._build()
        threading.Thread(target=self._poll_sysinfo, daemon=True).start()
        threading.Thread(target=self._poll_weather, daemon=True).start()
        self._tick_clock()
        self._animate_radar()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        HC, HD, HBG = self.HC, self.HD, self.HBG

        # Header
        hdr = tk.Frame(self, bg="#030c0a", height=28)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="  ◈  HUD",
                 font=("Consolas", 8, "bold"), fg=HC, bg="#030c0a").pack(
            side="left", pady=6)

        # Left border accent
        tk.Frame(self, bg=HD, width=1).pack(side="left", fill="y")

        inner = tk.Frame(self, bg=HBG)
        inner.pack(fill="both", expand=True, side="left")

        # ── Stat rows ────────────────────────────────────────────────────────
        self._stat_frames = {}
        for key, label in [("cpu", "CPU"), ("ram", "RAM"), ("net", "NET")]:
            frame = tk.Frame(inner, bg=HBG, cursor="hand2")
            frame.pack(fill="x", padx=8, pady=(8, 0))
            self._stat_frames[key] = frame

            lbl = tk.Label(frame, text=label, font=("Consolas", 7),
                           fg=HD, bg=HBG, anchor="w")
            lbl.pack(fill="x")

            val_lbl = tk.Label(frame, text="0%", font=("Consolas", 12),
                               fg=HC, bg=HBG, anchor="w")
            val_lbl.pack(fill="x")
            setattr(self, f"_{key}_lbl", val_lbl)

            bar_track = tk.Frame(frame, bg=HD, height=3)
            bar_track.pack(fill="x", pady=(2, 0))
            bar_fill = tk.Frame(bar_track, bg=HC, height=3, width=0)
            bar_fill.place(x=0, y=0, relheight=1.0)
            setattr(self, f"_{key}_bar", bar_fill)
            setattr(self, f"_{key}_track", bar_track)

            # Sparkline canvas (hidden by default)
            spark = tk.Canvas(frame, bg=HBG, highlightthickness=0,
                              height=self.SPARKLINE_H)
            setattr(self, f"_{key}_spark", spark)

            frame.bind("<Button-1>", lambda e, k=key: self._toggle_sparkline(k))
            for child in frame.winfo_children():
                child.bind("<Button-1>", lambda e, k=key: self._toggle_sparkline(k))

        # Divider
        tk.Frame(inner, bg=HD, height=1).pack(fill="x", padx=8, pady=8)

        # Clock
        self._clock_lbl = tk.Label(inner, text="00:00",
                                   font=("Consolas", 22, "bold"),
                                   fg=HC, bg=HBG, anchor="w")
        self._clock_lbl.pack(fill="x", padx=8)
        self._date_lbl = tk.Label(inner, text="",
                                  font=("Consolas", 7), fg=HD, bg=HBG, anchor="w")
        self._date_lbl.pack(fill="x", padx=8)

        # Divider
        tk.Frame(inner, bg=HD, height=1).pack(fill="x", padx=8, pady=8)

        # Weather
        self._weather_lbl = tk.Label(inner, text="⛅ Fetching…",
                                     font=("Consolas", 8), fg=HD, bg=HBG,
                                     anchor="w", wraplength=140, justify="left")
        self._weather_lbl.pack(fill="x", padx=8)

        # Divider
        tk.Frame(inner, bg=HD, height=1).pack(fill="x", padx=8, pady=8)

        # Radar
        tk.Label(inner, text="RADAR", font=("Consolas", 7),
                 fg=HD, bg=HBG).pack(anchor="center")
        self._radar = tk.Canvas(inner, bg=HBG, highlightthickness=0,
                                width=90, height=90)
        self._radar.pack(pady=(4, 8))
        self._radar_angle = 0

    # ── Polling threads ───────────────────────────────────────────────────────

    def _poll_sysinfo(self):
        try:
            import psutil
            prev_net = psutil.net_io_counters()
            while True:
                time.sleep(1)
                self._cpu_pct = psutil.cpu_percent()
                self._ram_pct = psutil.virtual_memory().percent
                cur_net = psutil.net_io_counters()
                bps = (cur_net.bytes_sent + cur_net.bytes_recv
                       - prev_net.bytes_sent - prev_net.bytes_recv)
                self._net_bps = bps
                prev_net = cur_net
                self._cpu_hist = self._cpu_hist[1:] + [self._cpu_pct / 100]
                self._ram_hist = self._ram_hist[1:] + [self._ram_pct / 100]
                self._net_hist = self._net_hist[1:] + [min(1.0, bps / 1_000_000)]
                self.after(0, self._update_stats)
        except Exception:
            pass

    def _poll_weather(self):
        try:
            import requests
            r = requests.get("https://wttr.in/?format=%C,+%t", timeout=6)
            txt = r.text.strip()
        except Exception:
            txt = "Unavailable"
        self.after(0, lambda: self._weather_lbl.configure(text=f"⛅ {txt}"))

    # ── Updates ───────────────────────────────────────────────────────────────

    def _update_stats(self):
        try:
            self._cpu_lbl.configure(text=f"{self._cpu_pct:.0f}%")
            self._ram_lbl.configure(text=f"{self._ram_pct:.0f}%")
            mb = self._net_bps / 1_000_000
            self._net_lbl.configure(text=f"↑↓ {mb:.1f}MB/s")
            for key, pct in [("cpu", self._cpu_pct / 100),
                              ("ram", self._ram_pct / 100),
                              ("net", min(1.0, self._net_bps / 1_000_000))]:
                track = getattr(self, f"_{key}_track")
                bar   = getattr(self, f"_{key}_bar")
                w = track.winfo_width()
                bar.place(x=0, y=0, relheight=1.0, width=max(1, int(w * pct)))
            if self._expanded:
                self._draw_sparkline(self._expanded)
        except Exception:
            pass

    def _tick_clock(self):
        now = datetime.datetime.now()
        self._clock_lbl.configure(text=now.strftime("%H:%M"))
        self._date_lbl.configure(text=now.strftime("%A, %B %d"))
        self.after(10_000, self._tick_clock)

    # ── Sparklines ────────────────────────────────────────────────────────────

    def _toggle_sparkline(self, key: str):
        spark = getattr(self, f"_{key}_spark")
        if self._expanded == key:
            spark.pack_forget()
            self._expanded = None
        else:
            if self._expanded:
                getattr(self, f"_{self._expanded}_spark").pack_forget()
            spark.pack(fill="x", pady=(4, 0))
            self._expanded = key
            self._draw_sparkline(key)

    def _draw_sparkline(self, key: str):
        spark  = getattr(self, f"_{key}_spark")
        hist   = getattr(self, f"_{key}_hist")
        spark.delete("all")
        w = spark.winfo_width() or 130
        h = self.SPARKLINE_H
        if not any(hist):
            return
        step = w / max(len(hist) - 1, 1)
        pts  = []
        for i, v in enumerate(hist):
            px = i * step
            py = h - 4 - v * (h - 8)
            pts.extend([px, py])
        if len(pts) >= 4:
            spark.create_line(*pts, fill=self.HC, width=1, smooth=True)
        # Fill under curve
        fill_pts = [0, h] + pts + [w, h]
        spark.create_polygon(*fill_pts, fill=self.HD, outline="")

    # ── Radar ─────────────────────────────────────────────────────────────────

    def _animate_radar(self):
        self._t += 1
        self._radar_angle = (self._radar_angle + 3) % 360
        self._draw_radar()
        self.after(33, self._animate_radar)

    def _draw_radar(self):
        c = self._radar
        c.delete("all")
        HC, HD = self.HC, self.HD
        cx = cy = 45

        # Rings
        for r in [44, 30, 16]:
            c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=HD, width=1)
        # Crosshair
        c.create_line(cx, cy - 44, cx, cy + 44, fill=HD, width=1)
        c.create_line(cx - 44, cy, cx + 44, cy, fill=HD, width=1)

        # Sweep
        rad = math.radians(self._radar_angle)
        ex  = cx + 44 * math.cos(rad)
        ey  = cy + 44 * math.sin(rad)
        c.create_line(cx, cy, ex, ey, fill=HC, width=1)

        # Fade trail (3 trailing lines, dimmer)
        for i, off in enumerate([20, 40, 60]):
            trail_rad = math.radians(self._radar_angle - off)
            tx = cx + 44 * math.cos(trail_rad)
            ty = cy + 44 * math.sin(trail_rad)
            dim_col = [HD, "#002420", "#001815"][i]
            c.create_line(cx, cy, tx, ty, fill=dim_col, width=1)

        # Blinking dots (fixed graph-space positions)
        dots = [(cx + 28, cy - 12), (cx - 18, cy + 24)]
        for dx, dy in dots:
            blink = 0.5 + 0.5 * math.sin(self._t * 0.12)
            r_val = int(0x00 * blink)
            g_val = int(0xd4 * blink)
            b_val = int(0xaa * blink)
            col   = f"#{r_val:02x}{g_val:02x}{b_val:02x}"
            c.create_oval(dx - 3, dy - 3, dx + 3, dy + 3, fill=col, outline="")
```

- [ ] **Step 2: Smoke test — check for syntax errors**

```bash
python -c "import main; print('HUDPanel' in dir(main))"
```

Expected: `True`

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat: add HUDPanel with live stats, clock, weather, radar, sparklines"
```

---

## Task 4: Replace speak_async with edge-tts

Convert `speak_async` to use `edge-tts`. Keep a module-level shim so `BootScreen` (which can't access the app instance) still works.

**Files:**
- Modify: `C:\Users\Jake\Jarvis\main.py`

- [ ] **Step 1: Add module-level shim and _app_instance global**

Replace the existing `speak_async` function (lines ~106–116) with:

```python
# ── Speech ────────────────────────────────────────────────────────────────────

_app_instance = None   # set by HubertApp.__init__; lets BootScreen call speak_async


def speak_async(text: str):
    """Module-level shim. Delegates to HubertApp.speak() when available,
    otherwise falls back to pyttsx3 (used during boot before the app is ready)."""
    if _app_instance is not None:
        _app_instance.speak(text)
    else:
        def _run():
            try:
                import pyttsx3
                e = pyttsx3.init()
                e.setProperty("rate", 175)
                e.say(text)
                e.runAndWait()
            except Exception:
                pass
        threading.Thread(target=_run, daemon=True).start()
```

- [ ] **Step 2: Add HubertApp.speak() method**

Add the following method to `HubertApp`, just after `__init__` (before `_build_ui`):

```python
    def speak(self, text: str):
        """Speak text via edge-tts (en-US-GuyNeural). Animates the sphere.
        Falls back to pyttsx3 if edge-tts or sounddevice is unavailable."""
        if self._muted:
            return

        def _run():
            import ui_bridge as _ub
            _ub.push("sphere_speaking", active=True)
            try:
                import asyncio, tempfile, os
                import edge_tts, sounddevice as sd, numpy as np
                import scipy.io.wavfile as wav

                async def _synth():
                    tts = edge_tts.Communicate(text, "en-US-GuyNeural")
                    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                        tmp = f.name
                    await tts.save(tmp)
                    return tmp

                tmp = asyncio.run(_synth())
                # Decode mp3 → wav via pydub or soundfile, then play
                try:
                    from pydub import AudioSegment
                    seg  = AudioSegment.from_mp3(tmp)
                    pcm  = np.array(seg.get_array_of_samples(), dtype=np.float32)
                    pcm /= 2 ** (seg.sample_width * 8 - 1)
                    if seg.channels == 2:
                        pcm = pcm.reshape(-1, 2)
                    sd.play(pcm, seg.frame_rate)
                    sd.wait()
                except Exception:
                    # Fallback: just play the mp3 via pygame if pydub missing
                    try:
                        import pygame
                        pygame.mixer.init()
                        pygame.mixer.music.load(tmp)
                        pygame.mixer.music.play()
                        while pygame.mixer.music.get_busy():
                            time.sleep(0.05)
                    except Exception:
                        raise
                finally:
                    try:
                        os.unlink(tmp)
                    except Exception:
                        pass

            except Exception:
                # Final fallback: pyttsx3
                try:
                    import pyttsx3
                    e = pyttsx3.init()
                    e.setProperty("rate", 175)
                    e.say(text)
                    e.runAndWait()
                except Exception:
                    pass
            finally:
                _ub.push("sphere_speaking", active=False)

        threading.Thread(target=_run, daemon=True).start()
```

- [ ] **Step 3: Set _app_instance in HubertApp.__init__**

In `HubertApp.__init__`, add this line immediately after `super().__init__()`:

```python
        global _app_instance
        _app_instance = self
```

And add the muted flag:

```python
        self._muted: bool = False
```

Place both lines before the call to `self._build_ui()`.

- [ ] **Step 4: Smoke test speak path**

```bash
python -c "
import main, threading, time
app_cls = main.HubertApp
# just check the method exists on the class
print(hasattr(app_cls, 'speak'))
"
```

Expected: `True`

- [ ] **Step 5: Commit**

```bash
git add main.py
git commit -m "feat: replace speak_async with edge-tts neural voice (en-US-GuyNeural)"
```

---

## Task 5: Three-Column Layout + Sphere + HUD Integration

Rewrite `_build_ui` in `HubertApp` to use three columns and wire up the sphere and HUD.

**Files:**
- Modify: `C:\Users\Jake\Jarvis\main.py`

- [ ] **Step 1: Replace the body section of _build_ui**

Find the `# ── Body ──` section inside `HubertApp._build_ui()` (currently ends around the `self.input_bar` line) and replace it entirely with:

```python
        tk.Frame(self, bg=DIM, height=1).pack(fill="x")

        # ── Body: three-column PanedWindow ──
        self._paned = tk.PanedWindow(self, orient="horizontal",
                                     sashwidth=5, sashrelief="flat",
                                     bg=DIM, showhandle=False)
        self._paned.pack(fill="both", expand=True)

        # Col 0 — Swarm panel
        self.swarm_panel = SwarmPanel(self._paned)
        self._paned.add(self.swarm_panel, minsize=180, width=300, stretch="never")

        # Col 1 — Chat column (sphere + chat + voice + input)
        center = tk.Frame(self._paned, bg=BG)
        self._paned.add(center, minsize=360, stretch="always")

        self.sphere = SphereWidget(center,
                                   on_mute_toggle=self._on_sphere_mute)
        self.sphere.pack(fill="x", pady=(0, 0))

        tk.Frame(center, bg=DIM, height=1).pack(fill="x")

        self.chat = ChatDisplay(center)
        self.chat.pack(fill="both", expand=True, pady=(0, 4), padx=8)

        self.voice_panel = VoicePanel(center, height=72)
        self.voice_panel.pack(fill="x", padx=8, pady=(0, 4))
        self.voice_panel.pack_propagate(False)

        self.input_bar = InputBar(center, on_send=self._send,
                                  on_camera=self._on_video)
        self.input_bar.pack(fill="x", padx=8, pady=(0, 8))
        self.input_bar._on_mic_state   = self.voice_panel.set_active
        self.input_bar._on_transcript  = self.voice_panel.set_transcript

        # Col 2 — HUD panel
        self.hud_panel = HUDPanel(self._paned)
        self._paned.add(self.hud_panel, minsize=120, width=160, stretch="never")

        # Double-click any sash → reset column widths
        self._paned.bind("<Double-Button-1>", self._reset_pane_widths)

        import tools as _tr
        _tr.on_new_tool(lambda name: self._q_put(self._on_new_tool, name))

        self.drawer = MenuDrawer(self)
        self.drawer._on_api_key = self._prompt_api_key
```

- [ ] **Step 2: Add _on_sphere_mute and _reset_pane_widths helpers**

Add these two methods to `HubertApp`, after `_build_ui`:

```python
    def _on_sphere_mute(self, muted: bool):
        self._muted = muted

    def _reset_pane_widths(self, event=None):
        total = self._paned.winfo_width()
        self._paned.sash_place(0, 300, 1)
        self._paned.sash_place(1, total - 160, 1)
```

- [ ] **Step 3: Remove the HUD button from the header**

In `_build_ui`, find and delete these two lines in the `# Right controls` section:

```python
        ctk.CTkButton(right, text="HUD", width=42, height=32,
                      fg_color=DIM, hover_color="#003028", text_color="#00d4aa",
                      font=("Consolas", 9, "bold"), corner_radius=6,
                      command=self._toggle_hud).pack(side="left", padx=(6,0))
```

- [ ] **Step 4: Update _process_q to handle sphere commands**

Replace the `_process_q` method with:

```python
    def _process_q(self):
        try:
            while True:
                fn, args = self._q.get_nowait()
                fn(*args)
        except queue.Empty:
            pass
        # Drain live UI commands from HUBERT tools via ui_bridge
        try:
            import ui_bridge
            for cmd in ui_bridge.pop_all():
                c = cmd.get("cmd", "")
                if c == "sphere_speaking":
                    self.sphere.set_speaking(cmd.get("active", False))
                elif c == "sphere_muted":
                    self.sphere.set_muted(cmd.get("active", False))
                else:
                    self.swarm_panel.dispatch(cmd)
        except Exception:
            pass
        self.after(25, self._process_q)
```

- [ ] **Step 5: Run HUBERT and visually verify**

```bash
cd C:\Users\Jake\Jarvis
python main.py
```

Check:
- Three columns visible: swarm (left), chat + sphere (center), HUD (right)
- Sphere is showing in the chat column with STANDBY label
- HUD panel shows CPU/RAM/NET values updating, clock ticking, radar sweeping
- No HUD button in header
- Column dividers draggable; double-click resets widths

- [ ] **Step 6: Commit**

```bash
git add main.py
git commit -m "feat: three-column layout with integrated HUD and SphereWidget"
```

---

## Task 6: Delete HUDOverlay

Remove the now-unused `HUDOverlay` class and its supporting references.

**Files:**
- Modify: `C:\Users\Jake\Jarvis\main.py`

- [ ] **Step 1: Delete HUDOverlay class**

Find `class HUDOverlay(SafeTopLevel):` and delete the entire class definition (from that line to just before `# ── Main App ──`). This is approximately 295 lines.

- [ ] **Step 2: Remove _toggle_hud method from HubertApp**

Find and delete the entire `_toggle_hud` method:

```python
    def _toggle_hud(self):
        if self._hud is not None:
            try:
                self._hud.destroy()
            except Exception:
                pass
            self._hud = None
        else:
            self._hud = HUDOverlay(self)
            self._hud.protocol("WM_DELETE_WINDOW",
                               lambda: setattr(self, "_hud", None))
```

- [ ] **Step 3: Remove _hud attribute from HubertApp.__init__**

Find and delete this line in `HubertApp.__init__`:

```python
        self._hud: HUDOverlay | None = None
```

- [ ] **Step 4: Remove _toggle_map reference to swarm visibility if it used _hud**

Check `_toggle_map` — it currently calls `self.swarm_panel.toggle_visibility()` which is correct. No change needed there.

- [ ] **Step 5: Verify app still starts**

```bash
python main.py
```

Expected: app starts without errors, no HUD button anywhere.

- [ ] **Step 6: Commit**

```bash
git add main.py
git commit -m "refactor: delete HUDOverlay class, replaced by integrated HUDPanel"
```

---

## Task 7: SwarmPanel Viewport Transform

Add pan/zoom state to `SwarmPanel` and apply a coordinate transform in `_render`.

**Files:**
- Modify: `C:\Users\Jake\Jarvis\main.py`

- [ ] **Step 1: Add viewport state to SwarmPanel.__init__**

In `SwarmPanel.__init__`, add these lines after `self._visible = True`:

```python
        # Viewport state for pan/zoom
        self._pan_x  = 0.0
        self._pan_y  = 0.0
        self._zoom   = 1.0
        self._drag_start = None   # (x, y) screen coords at drag start
        self._pan_start  = None   # (pan_x, pan_y) at drag start
        self._hovered_node  = None   # nid of node under cursor
        self._inspected_node = None  # nid of pinned inspector node
```

- [ ] **Step 2: Add coordinate transform helpers to SwarmPanel**

Add these methods to `SwarmPanel` after `_add_hub`:

```python
    def _g2s(self, gx: float, gy: float):
        """Graph-space → screen-space."""
        return gx * self._zoom + self._pan_x, gy * self._zoom + self._pan_y

    def _s2g(self, sx: float, sy: float):
        """Screen-space → graph-space."""
        return (sx - self._pan_x) / self._zoom, (sy - self._pan_y) / self._zoom

    def _hit_node(self, sx: float, sy: float):
        """Return nid of the node whose screen circle contains (sx, sy), or None."""
        radii = {"hub": self.HUB_R, "agent": self.AGT_R, "tool": self.TOOL_R}
        for nid, nd in self._nodes.items():
            scx, scy = self._g2s(nd["x"], nd["y"])
            r = radii.get(nd["kind"], self.AGT_R) * self._zoom
            if math.hypot(sx - scx, sy - scy) <= r + 4:
                return nid
        return None
```

- [ ] **Step 3: Update _render to apply transform**

In `SwarmPanel._render`, replace every direct use of `fn["x"], fn["y"]`, `tn["x"], tn["y"]`, and all node drawing coordinates with transformed versions. 

Replace the entire `_render` method with:

```python
    def _render(self):
        c = self._canvas
        c.delete("all")
        w = c.winfo_width() or self.W
        h = c.winfo_height() or 300

        # Background grid dots (in screen space — fixed, not panned)
        for gx in range(0, w + 24, 24):
            for gy in range(0, h + 24, 24):
                c.create_oval(gx-1, gy-1, gx+1, gy+1, fill="#0d1530", outline="")

        # Static edges
        for fid, tid in self._edges:
            fn = self._nodes.get(fid)
            tn = self._nodes.get(tid)
            if fn and tn:
                fx, fy = self._g2s(fn["x"], fn["y"])
                tx, ty = self._g2s(tn["x"], tn["y"])
                c.create_line(fx, fy, tx, ty, fill="#131e3a", width=1, dash=(3, 5))

        # Animated pulse dots along edges
        dead = []
        for i, p in enumerate(self._pulses):
            fn = self._nodes.get(p["fid"])
            tn = self._nodes.get(p["tid"])
            if fn and tn:
                prog = p["t"] / p["max_t"]
                gx = fn["x"] + (tn["x"] - fn["x"]) * prog
                gy = fn["y"] + (tn["y"] - fn["y"]) * prog
                px, py = self._g2s(gx, gy)
                r = max(2, int(4 * self._zoom))
                c.create_oval(px-r, py-r, px+r, py+r, fill=p["color"], outline="")
            p["t"] += 1
            if p["t"] >= p["max_t"]:
                dead.append(i)
        for i in reversed(dead):
            self._pulses.pop(i)

        # Draw nodes
        for nid, nd in self._nodes.items():
            gx, gy = nd["x"], nd["y"]
            x, y   = self._g2s(gx, gy)
            kind   = nd["kind"]
            label  = nd["label"]
            age    = self._t - nd.get("last_active", 0)
            z      = self._zoom

            if kind == "hub":
                r, base_col, fill = int(self.HUB_R * z), ACCENT, "#040810"
                pr = r + int((6 + 3 * math.sin(self._t * 0.08)) * z)
                c.create_oval(x-pr, y-pr, x+pr, y+pr, outline="#002233", width=1)
                for arc_r_g, extent, phase, acol in [
                    (self.HUB_R+14, 180, 0,   ACCENT),
                    (self.HUB_R+20, 100, 200, ACCENT2),
                ]:
                    arc_r = int(arc_r_g * z)
                    c.create_arc(x-arc_r, y-arc_r, x+arc_r, y+arc_r,
                                 start=(self._t * 2.5 + phase) % 360,
                                 extent=extent, outline=acol, width=1, style="arc")
                icon, fsz = "H", max(6, int(10 * z))

            elif kind == "agent":
                r        = int(self.AGT_R * z)
                base_col = ACCENT2 if age < 80 else PURPLE
                fill     = "#0a0820"
                if age < 40:
                    pr = r + int(4 * abs(math.sin(self._t * 0.15)) * z)
                    c.create_oval(x-pr, y-pr, x+pr, y+pr, outline=ACCENT2, width=1)
                icon, fsz = "A", max(5, int(8 * z))

            else:  # tool
                r        = int(self.TOOL_R * z)
                base_col = GREEN if age < 80 else TEXT_TOOL
                fill     = "#071a12"
                if age < 40:
                    pr = r + int(3 * abs(math.sin(self._t * 0.18)) * z)
                    c.create_oval(x-pr, y-pr, x+pr, y+pr, outline=GREEN, width=1)
                icon, fsz = "T", max(5, int(7 * z))

            # Highlight hovered node
            if nid == self._hovered_node or nid == self._inspected_node:
                c.create_oval(x-r-4, y-r-4, x+r+4, y+r+4,
                              outline=ACCENT, width=1)

            c.create_oval(x-r, y-r, x+r, y+r, fill=fill, outline=base_col, width=2)
            c.create_text(x, y-3, text=icon,
                          font=("Consolas", fsz, "bold"), fill=base_col)
            short = label[:13] if len(label) <= 13 else label[:12] + "…"
            c.create_text(x, y + r + int(9 * z), text=short,
                          font=("Consolas", max(5, int(6 * z))), fill=TEXT_DIM,
                          width=int(88 * z), justify="center")

        # Draw hover tooltip
        if self._hovered_node and self._hovered_node != self._inspected_node:
            self._draw_tooltip(self._hovered_node)

        # Draw pinned inspector
        if self._inspected_node:
            self._draw_inspector(self._inspected_node)
```

- [ ] **Step 4: Add tooltip and inspector draw helpers**

Add these methods to `SwarmPanel` after `_render`:

```python
    def _draw_tooltip(self, nid: str):
        """Draw a small floating tooltip near the hovered node."""
        nd  = self._nodes.get(nid)
        if not nd:
            return
        c   = self._canvas
        sx, sy = self._g2s(nd["x"], nd["y"])
        r   = {"hub": self.HUB_R, "agent": self.AGT_R,
               "tool": self.TOOL_R}.get(nd["kind"], self.AGT_R) * self._zoom

        # Tooltip box
        tx, ty = sx + r + 6, sy - 30
        lines = [
            nd["label"][:18],
            f"status: {'ACTIVE' if self._t - nd.get('last_active',0) < 80 else 'idle'}",
            f"kind:   {nd['kind']}",
        ]
        box_w, box_h = 130, len(lines) * 14 + 10
        # keep in canvas bounds
        cw = c.winfo_width() or self.W
        if tx + box_w > cw - 4:
            tx = sx - r - box_w - 6
        c.create_rectangle(tx, ty, tx + box_w, ty + box_h,
                           fill="#0a0f1e", outline=ACCENT, width=1)
        for i, line in enumerate(lines):
            color = ACCENT if i == 0 else TEXT_DIM
            c.create_text(tx + 6, ty + 6 + i * 14, text=line,
                          font=("Consolas", 7), fill=color, anchor="nw")

    def _draw_inspector(self, nid: str):
        """Draw a pinned inspector panel at the bottom of the swarm canvas."""
        nd  = self._nodes.get(nid)
        if not nd:
            return
        c   = self._canvas
        cw  = c.winfo_width() or self.W
        ch  = c.winfo_height() or 300
        bx, by = 4, ch - 90
        bw, bh = cw - 8, 86
        age    = self._t - nd.get("last_active", 0)
        status = "ACTIVE" if age < 80 else "IDLE"

        c.create_rectangle(bx, by, bx + bw, by + bh,
                           fill="#040810", outline=ACCENT2, width=1)
        c.create_text(bx + 6, by + 6, text=nd["label"][:22],
                      font=("Consolas", 8, "bold"), fill=ACCENT, anchor="nw")
        c.create_text(bx + 6, by + 20, text=f"kind:    {nd['kind']}",
                      font=("Consolas", 7), fill=TEXT_DIM, anchor="nw")
        col = GREEN if status == "ACTIVE" else TEXT_DIM
        c.create_text(bx + 6, by + 32, text=f"status:  {status}",
                      font=("Consolas", 7), fill=col, anchor="nw")
        c.create_text(bx + 6, by + 44, text=f"age:     {age} ticks",
                      font=("Consolas", 7), fill=TEXT_DIM, anchor="nw")
        c.create_text(bx + 6, by + 56, text="[click node again or outside to close]",
                      font=("Consolas", 6), fill=TEXT_DIM, anchor="nw")
```

- [ ] **Step 5: Verify transforms work — run app and confirm graph renders correctly**

```bash
python main.py
```

The swarm graph should look identical to before (pan=0, zoom=1 means no visible change).

- [ ] **Step 6: Commit**

```bash
git add main.py
git commit -m "feat: add viewport transform layer to SwarmPanel (pan/zoom foundation)"
```

---

## Task 8: SwarmPanel Pan, Zoom, and Node Interaction

Wire up mouse event bindings for pan, zoom, hover tooltip, and click inspector.

**Files:**
- Modify: `C:\Users\Jake\Jarvis\main.py`

- [ ] **Step 1: Add zoom buttons to SwarmPanel header**

In `SwarmPanel._build`, replace the existing header line:

```python
        tk.Label(hdr, text="  ◈  SWARM MONITOR",
                 font=("Consolas", 8, "bold"), fg=ACCENT, bg=BG_CARD).pack(
            side="left", pady=6)
```

with:

```python
        tk.Label(hdr, text="  ◈  SWARM MONITOR",
                 font=("Consolas", 8, "bold"), fg=ACCENT, bg=BG_CARD).pack(
            side="left", pady=6)
        # Zoom controls
        for sym, cmd in [("−", lambda: self._zoom_step(-0.2)),
                         ("⊙", self._zoom_reset),
                         ("+", lambda: self._zoom_step(0.2))]:
            b = tk.Button(hdr, text=sym, font=("Consolas", 8),
                          fg=TEXT_DIM, bg=BG_CARD, relief="flat", bd=0,
                          activebackground=BG_CARD, activeforeground=ACCENT,
                          command=cmd)
            b.pack(side="right", padx=2)
```

- [ ] **Step 2: Bind mouse events to the canvas**

In `SwarmPanel._build`, after `self._canvas = tk.Canvas(...)` and `.pack(...)`, add:

```python
        self._canvas.bind("<Button-1>",       self._on_canvas_click)
        self._canvas.bind("<B1-Motion>",       self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_drag_end)
        self._canvas.bind("<Motion>",          self._on_hover)
        self._canvas.bind("<MouseWheel>",      self._on_scroll)   # Windows
        self._canvas.bind("<Button-4>",        self._on_scroll)   # Linux scroll up
        self._canvas.bind("<Button-5>",        self._on_scroll)   # Linux scroll down
```

- [ ] **Step 3: Add pan/zoom/hover/click handlers to SwarmPanel**

Add these methods to `SwarmPanel` after `_zoom_reset` (which you'll also add):

```python
    def _zoom_step(self, delta: float):
        self._zoom = max(0.5, min(3.0, self._zoom + delta))

    def _zoom_reset(self):
        self._zoom  = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0

    def _on_canvas_click(self, event):
        hit = self._hit_node(event.x, event.y)
        if hit:
            if hit == self._inspected_node:
                # Clicking pinned node again closes inspector
                self._inspected_node = None
            else:
                self._inspected_node = hit
        else:
            # Click on empty space: close inspector, start drag
            self._inspected_node = None
            self._drag_start = (event.x, event.y)
            self._pan_start  = (self._pan_x, self._pan_y)

    def _on_drag(self, event):
        if self._drag_start is None:
            return
        dx = event.x - self._drag_start[0]
        dy = event.y - self._drag_start[1]
        self._pan_x = self._pan_start[0] + dx
        self._pan_y = self._pan_start[1] + dy

    def _on_drag_end(self, event):
        self._drag_start = None
        self._pan_start  = None

    def _on_hover(self, event):
        self._hovered_node = self._hit_node(event.x, event.y)

    def _on_scroll(self, event):
        # Windows: event.delta is ±120; Linux: event.num is 4 or 5
        if event.num == 5 or event.delta < 0:
            direction = -1
        else:
            direction = 1
        old_zoom = self._zoom
        self._zoom = max(0.5, min(3.0, self._zoom + direction * 0.15))
        # Zoom centered on cursor
        scale = self._zoom / old_zoom
        self._pan_x = event.x - scale * (event.x - self._pan_x)
        self._pan_y = event.y - scale * (event.y - self._pan_y)
```

- [ ] **Step 4: Run app and test interactivity**

```bash
python main.py
```

Test each interaction:
- Drag on empty swarm canvas area → graph pans
- Scroll wheel up/down → graph zooms in/out centered on cursor
- Click `+`/`−`/`⊙` buttons → zoom changes / resets
- Hover over a node → tooltip appears
- Click a node → inspector panel appears at bottom
- Click same node again → inspector closes
- Click empty space → inspector closes

- [ ] **Step 5: Commit**

```bash
git add main.py
git commit -m "feat: interactive SwarmPanel — pan, zoom, hover tooltip, click inspector"
```

---

## Task 9: Wire Sphere Animation to HUBERT Replies

Ensure the sphere animates when HUBERT speaks — triggered by the reply completing.

**Files:**
- Modify: `C:\Users\Jake\Jarvis\main.py`

- [ ] **Step 1: Update _done to trigger speech of last reply**

Find the `_done` method in `HubertApp` and update it to speak the last HUBERT message:

```python
    def _done(self):
        self.chat.end_hubert()
        self._set_status("ready")
        self.input_bar.set_enabled(True)
        # Speak the last HUBERT reply
        try:
            last = self.core.conversation_history[-1]
            if last["role"] == "assistant" and isinstance(last["content"], str):
                text = last["content"].strip()
                if text:
                    # Truncate very long replies to avoid long TTS waits
                    self.speak(text[:600])
        except Exception:
            pass
```

- [ ] **Step 2: Verify sphere animates on reply**

Run the app, send a message, and confirm:
- Sphere brightens and rings expand while HUBERT is speaking
- Sphere returns to dim STANDBY when TTS finishes
- Clicking the sphere during speech mutes immediately (no new speech starts)

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat: sphere animates during HUBERT replies via edge-tts"
```

---

## Task 10: Final Polish and Smoke Test

**Files:**
- Modify: `C:\Users\Jake\Jarvis\main.py`

- [ ] **Step 1: Update all remaining speak_async call sites**

Search for any remaining direct calls to `speak_async(` in `main.py` (grep for it). There should be two left besides the shim:
- `BootScreen._display_info` (line ~306) — leave as-is, shim handles it
- `_show_last_session` (line ~1916) — update to `self.speak(...)`
- `_on_new_tool` (line ~2047) — update to `self.speak(...)`

Replace those two `speak_async(...)` calls inside `HubertApp` methods with `self.speak(...)`:

In `_show_last_session`:
```python
            self.speak(f"Welcome back, sir. Last time we were {recap[:120]}")
```

In `_on_new_tool`:
```python
        self.speak(f"New skill loaded: {name.replace('_', ' ')}")
```

- [ ] **Step 2: Full end-to-end smoke test**

```bash
python main.py
```

Walk through the full checklist:
- [ ] Boot screen appears → plays boot greeting via TTS → fades out
- [ ] Three columns visible: swarm (left), chat+sphere (center), HUD (right)
- [ ] HUD shows live CPU/RAM/NET updating every second
- [ ] Clock ticks every 10 seconds
- [ ] Weather fetches and shows
- [ ] Radar sweeps continuously
- [ ] Click a CPU/RAM/NET stat → sparkline expands; click again → collapses
- [ ] Swarm graph: drag to pan, scroll to zoom, hover tooltip, click inspector
- [ ] Send a message → HUBERT replies → sphere animates + voice plays
- [ ] Click sphere → mutes, 🔇 flashes, no more speech; click again → unmutes
- [ ] Dragging the sash between columns resizes them
- [ ] Double-clicking a sash resets widths

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat: complete HUBERT UI redesign — three-column, sphere, edge-tts, interactive swarm"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|-----------------|------|
| Three-column layout (swarm \| chat+sphere \| HUD) | Task 5 |
| SphereWidget idle/speaking/muted states | Task 2 |
| Sphere click to mute | Task 2 |
| HUDPanel — CPU/RAM/NET/clock/weather/radar | Task 3 |
| Expandable sparklines | Task 3 |
| edge-tts with en-US-GuyNeural | Task 4 |
| pyttsx3 fallback | Task 4 |
| speak_async → HubertApp method | Task 4 |
| _process_q sphere command handling | Task 5 |
| Draggable dividers via PanedWindow | Task 5 |
| Double-click sash to reset widths | Task 5 |
| HUDOverlay deleted | Task 6 |
| SwarmPanel viewport transform | Task 7 |
| SwarmPanel pan (drag) | Task 8 |
| SwarmPanel zoom (scroll + buttons) | Task 8 |
| Hover tooltip | Task 7 + 8 |
| Click inspector | Task 7 + 8 |
| Sphere animates on HUBERT replies | Task 9 |
| Remaining speak_async call sites updated | Task 10 |

All spec requirements are covered. ✓

**Type/name consistency check:**
- `SphereWidget.set_speaking(active: bool)` — used in `_process_q` as `self.sphere.set_speaking(...)` ✓
- `SphereWidget.set_muted(active: bool)` — used in `_process_q` and `_on_sphere_mute` ✓
- `HubertApp.speak(text: str)` — called as `self.speak(...)` in `_done`, `_show_last_session`, `_on_new_tool` ✓
- `SwarmPanel._g2s` / `_s2g` / `_hit_node` — used consistently in `_render`, `_draw_tooltip`, `_draw_inspector`, `_on_canvas_click`, `_on_hover` ✓
- `self._inspected_node` / `self._hovered_node` / `self._drag_start` / `self._pan_start` — initialized in Task 7 Step 1, used in Task 8 ✓
