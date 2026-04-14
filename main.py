"""
H.U.B.E.R.T. — Highly Unified Brilliant Experimental Research Terminal
Powered by Claude Sonnet 4.6
"""
import sys, math, threading, queue, time, os, random, datetime, platform, subprocess
import tkinter as tk
import customtkinter as ctk
from pathlib import Path
from jarvis_core import JarvisCore, chat_in_thread
from config import get_api_key, set_api_key

_IS_WIN = platform.system() == "Windows"
_IS_MAC = platform.system() == "Darwin"
_MONO_FONT = "Menlo" if _IS_MAC else _MONO_FONT

# ── Speech globals (cached so mic presses are instant after first use) ─────────
_whisper_model   = None
_whisper_lock    = threading.Lock()
_mic_index_cache = None          # cached USB mic index
_ffmpeg_ready    = False

# ── TTS serialisation — one queue + one worker thread prevents overlapping audio
import queue as _tts_queue_mod
_tts_queue    = _tts_queue_mod.Queue()
_tts_worker   = None    # started lazily on first speak() call
_tts_skip_tag = [0]     # incremented to cancel queued sentences from old responses

def _tts_worker_loop():
    """Single background thread drains _tts_queue one closure at a time."""
    while True:
        item = _tts_queue.get()
        if item is None:
            break
        tag, fn = item
        # Only play if tag matches current — skips stale sentences
        if tag == _tts_skip_tag[0]:
            try:
                fn()
            except Exception:
                pass
        _tts_queue.task_done()

def _ensure_tts_worker():
    global _tts_worker
    if _tts_worker is None or not _tts_worker.is_alive():
        _tts_worker = threading.Thread(target=_tts_worker_loop, daemon=True)
        _tts_worker.start()

def _tts_enqueue(fn, tag=None):
    """Add a playback closure to the serial TTS queue."""
    _ensure_tts_worker()
    t = tag if tag is not None else _tts_skip_tag[0]
    _tts_queue.put((t, fn))

def _tts_cancel():
    """Discard all queued (unstarted) TTS items by bumping the generation tag."""
    _tts_skip_tag[0] += 1

def _ensure_ffmpeg():
    global _ffmpeg_ready
    if _ffmpeg_ready:
        return
    try:
        if _IS_WIN:
            import imageio_ffmpeg, shutil
            exe   = imageio_ffmpeg.get_ffmpeg_exe()
            fdir  = os.path.dirname(exe)
            plain = os.path.join(fdir, "ffmpeg.exe")
            if not os.path.exists(plain):
                shutil.copy(exe, plain)
            if fdir not in os.environ.get("PATH", ""):
                os.environ["PATH"] = fdir + os.pathsep + os.environ.get("PATH", "")
        else:
            # On Mac/Linux ffmpeg is installed via brew/apt — just verify it exists
            import shutil as _sh
            if not _sh.which("ffmpeg"):
                pass  # whisper will still work without ffmpeg for many formats
        _ffmpeg_ready = True
    except Exception:
        pass

def _get_whisper():
    """Load Whisper once, cache forever. Thread-safe."""
    global _whisper_model
    if _whisper_model is not None:
        return _whisper_model
    with _whisper_lock:
        if _whisper_model is None:
            try:
                import whisper
                _ensure_ffmpeg()
                _whisper_model = whisper.load_model("base")
            except Exception:
                pass
    return _whisper_model

def _get_mic_index():
    """Find the best microphone once, cache the index."""
    global _mic_index_cache
    if _mic_index_cache is not None:
        return _mic_index_cache
    try:
        import speech_recognition as sr
        for i, name in enumerate(sr.Microphone.list_microphone_names()):
            if "usb" in name.lower() or ("microphone" in name.lower()
                                         and "output" not in name.lower()):
                _mic_index_cache = i
                return i
    except Exception:
        pass
    _mic_index_cache = 0
    return 0

# ── Theme ────────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

BG        = "#060810"
BG_PANEL  = "#080c1a"
BG_CARD   = "#0a0f1e"
BG_INPUT  = "#0b1120"
BG_MSG    = "#0c1325"
ACCENT    = "#00d4ff"
ACCENT2   = "#6644ff"
ACCENT3   = "#00ff9d"
DIM       = "#131e3a"
DIM2      = "#1a2848"
TEXT      = "#d0e8ff"
TEXT_DIM  = "#2e4468"
TEXT_TOOL = "#00cc88"
TEXT_ERR  = "#ff3355"
TEXT_USR  = "#5599ff"
PURPLE    = "#8866ff"
GREEN     = "#00ff9d"

# Bubble colours
USR_BG    = "#0d1a3a"
USR_BORDER= "#1a3060"
HUB_BG    = "#090e1c"
TOOL_BG   = "#071a14"
ERR_BG    = "#1a0610"

F_MONO  = (_MONO_FONT, 11)
F_CHAT  = (_MONO_FONT, 11)
F_TITLE = (_MONO_FONT, 17, "bold")
F_SUB   = (_MONO_FONT, 8)
F_SMALL = (_MONO_FONT, 10)
F_TAG   = (_MONO_FONT, 8, "bold")


# ── Utilities ─────────────────────────────────────────────────────────────────

# ── Speech ────────────────────────────────────────────────────────────────────

_app_instance = None   # set by HubertApp.__init__; lets BootScreen call speak_async


def speak_async(text: str):
    """Module-level shim — always routes through _tts_queue for serialisation."""
    if _app_instance is not None:
        _app_instance.speak(text)
        return
    def _play():
        try:
            import pyttsx3
            e = pyttsx3.init()
            e.setProperty("rate", 175)
            e.say(text)
            e.runAndWait()
        except Exception:
            pass
    _tts_enqueue(_play)


def get_weather() -> str:
    try:
        import requests
        r = requests.get("https://wttr.in/?format=%C,+%t", timeout=6)
        return r.text.strip()
    except Exception:
        return "Weather unavailable"


def build_greeting():
    now = datetime.datetime.now()
    hour = now.hour
    if hour < 12:   greeting = "Good morning"
    elif hour < 17: greeting = "Good afternoon"
    else:           greeting = "Good evening"
    return greeting, now.strftime("%A, %B %d"), now.strftime("%I:%M %p")


def ts() -> str:
    return time.strftime("%H:%M")


# ── Auto-start ────────────────────────────────────────────────────────────────

def is_autostart_enabled() -> bool:
    if _IS_WIN:
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\Windows\CurrentVersion\Run")
            winreg.QueryValueEx(key, "HUBERT")
            winreg.CloseKey(key)
            return True
        except Exception:
            return False
    elif _IS_MAC:
        plist = Path.home() / "Library/LaunchAgents/com.jake.hubert.plist"
        return plist.exists()
    return False

def set_autostart(enable: bool):
    if _IS_WIN:
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\Windows\CurrentVersion\Run",
                                 0, winreg.KEY_SET_VALUE)
            if enable:
                script = str(Path(__file__).resolve())
                winreg.SetValueEx(key, "HUBERT", 0, winreg.REG_SZ,
                                  f'"{sys.executable}" "{script}"')
            else:
                try: winreg.DeleteValue(key, "HUBERT")
                except FileNotFoundError: pass
            winreg.CloseKey(key)
        except Exception:
            pass
    elif _IS_MAC:
        plist = Path.home() / "Library/LaunchAgents/com.jake.hubert.plist"
        if enable:
            script = str(Path(__file__).resolve())
            plist.parent.mkdir(parents=True, exist_ok=True)
            plist.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.jake.hubert</string>
  <key>ProgramArguments</key>
  <array>
    <string>{sys.executable}</string>
    <string>{script}</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><false/>
</dict></plist>
""")
            subprocess.run(["launchctl", "load", str(plist)], check=False)
        else:
            if plist.exists():
                subprocess.run(["launchctl", "unload", str(plist)], check=False)
                plist.unlink(missing_ok=True)


# ── Safe Toplevel base (silences CTK post-destroy callback errors) ─────────────

class SafeTopLevel(ctk.CTkToplevel):
    """Wraps CTK internal callbacks that fire on already-destroyed windows."""
    def _revert_withdraw_after_windows_set_titlebar_color(self):
        try:
            super()._revert_withdraw_after_windows_set_titlebar_color()
        except Exception:
            pass
    def _update_dimensions_event(self, event=None):
        try:
            super()._update_dimensions_event(event)
        except Exception:
            pass
    def _update_appearance_mode_event(self, mode_string):
        try:
            super()._update_appearance_mode_event(mode_string)
        except Exception:
            pass
    def iconbitmap(self, *args, **kwargs):
        try:
            return super().iconbitmap(*args, **kwargs)
        except Exception:
            pass
    def deiconify(self):
        try:
            return super().deiconify()
        except Exception:
            pass


# ── Boot Screen ───────────────────────────────────────────────────────────────

class BootScreen(tk.Toplevel):
    """Full-screen animated boot overlay. No chrome (overrideredirect).
    Speaks exactly ONE greeting then calls on_complete — no other voice fires at boot."""
    LINES = [
        ("POWER SYSTEMS",   "ONLINE"),
        ("NEURAL INTERFACE","ACTIVE"),
        ("TOOL REGISTRY",   "LOADED"),
        ("BROWSER ENGINE",  "READY"),
        ("VOICE MODULE",    "ENABLED"),
        ("CLAUDE API",      "CONNECTED"),
    ]

    def __init__(self, parent, on_complete):
        super().__init__(parent)
        self._on_complete = on_complete
        self._spoke       = False   # guard: speak exactly once
        self.overrideredirect(True)
        self.configure(bg="#000000")
        parent.update_idletasks()
        x, y = parent.winfo_x(), parent.winfo_y()
        w, h = parent.winfo_width(), parent.winfo_height()
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.lift()
        self._bw    = w
        self._bh    = h
        self._canvas = tk.Canvas(self, bg="#000000", highlightthickness=0)
        self._canvas.pack(fill="both", expand=True)
        self._step     = 0
        self._char_idx = 0
        self._title    = "H·U·B·E·R·T"
        self._angle    = 0
        self.after(200, self._animate_title)

    def _draw_bg(self):
        self._bw = self._canvas.winfo_width()  or self._bw
        self._bh = self._canvas.winfo_height() or self._bh
        c = self._canvas
        c.delete("all")
        for i in range(0, self._bh, 4):
            v = int(8 + 6 * math.sin(i * 0.08 + self._angle * 0.04))
            col = f"#{v:02x}{v:02x}{v:02x}"
            c.create_line(0, i, self._bw, i, fill=col)
        cx, cy = self._bw // 2, self._bh // 2 - 80
        for r in range(90, 5, -12):
            a = max(0, int(5 * r / 90))
            col = f"#00{min(255,a*5):02x}{min(255,a*12):02x}"
            c.create_oval(cx-r, cy-r, cx+r, cy+r, outline=col, width=1)
        for i, (ext, _, col, w_) in enumerate([
            (220, 0, ACCENT, 2), (80, 250, ACCENT2, 1), (140, 130, PURPLE, 1),
        ]):
            c.create_arc(cx-50+i*5, cy-50+i*5, cx+50-i*5, cy+50-i*5,
                         start=(self._angle * (1 + i*0.4)) % 360, extent=ext,
                         outline=col, width=w_, style="arc")
        self._angle += 2.5
        return cx, cy

    def _animate_title(self):
        cx, cy = self._draw_bg()
        self._canvas.create_text(cx, cy, text=self._title[:self._char_idx],
            font=(_MONO_FONT, 36, "bold"), fill=ACCENT, anchor="center")
        self._canvas.create_text(cx, cy + 44, text="INITIALIZING SYSTEMS",
            font=(_MONO_FONT, 10), fill=TEXT_DIM, anchor="center")
        if self._char_idx < len(self._title):
            self._char_idx += 1
            self.after(75, self._animate_title)
        else:
            self.after(300, self._show_checklist)

    def _show_checklist(self):
        self._step = 0
        self._tick()

    def _tick(self):
        cx, cy = self._draw_bg()
        self._canvas.create_text(cx, cy, text=self._title,
            font=(_MONO_FONT, 36, "bold"), fill=ACCENT, anchor="center")
        self._canvas.create_text(cx, cy + 44, text="INITIALIZING SYSTEMS",
            font=(_MONO_FONT, 10), fill=TEXT_DIM, anchor="center")
        start_y = cy + 90
        for i, (label, status) in enumerate(self.LINES):
            color = GREEN if i < self._step else TEXT_DIM
            tick  = "✓" if i < self._step else ("▶" if i == self._step else "·")
            self._canvas.create_text(cx - 180, start_y + i * 26,
                text=f"  {tick}  {label:<22}{status if i < self._step else '...'}",
                font=(_MONO_FONT, 10), fill=color, anchor="w")
        if self._step < len(self.LINES):
            self._step += 1
            self.after(240, self._tick)
        else:
            self.after(400, self._show_weather)

    def _show_weather(self):
        def _fetch():
            greeting, date_str, time_str = build_greeting()
            weather = get_weather()
            self.after(0, lambda: self._display_info(greeting, date_str, time_str, weather))
        threading.Thread(target=_fetch, daemon=True).start()

    def _display_info(self, greeting, date_str, time_str, weather):
        cx, cy = self._draw_bg()
        self._canvas.create_text(cx, cy, text=self._title,
            font=(_MONO_FONT, 36, "bold"), fill=ACCENT, anchor="center")
        info_y = cy + 80
        for i, (line, color, sz) in enumerate([
            (f"{greeting}, Jake.",        TEXT,     14),
            (f"Today is {date_str}.",     TEXT_DIM, 12),
            (f"Current time: {time_str}", TEXT_DIM, 12),
            (f"⛅  {weather}",            ACCENT2,  12),
        ]):
            self._canvas.create_text(cx, info_y + i * 32,
                text=line, font=(_MONO_FONT, sz), fill=color, anchor="center")

        # ONE speak call — guarded so closing early can't re-trigger it
        if not self._spoke:
            self._spoke = True
            speak_async(
                f"{greeting}, Jake. Today is {date_str}. "
                f"The time is {time_str}. Weather: {weather}. "
                f"Hubert is online and ready."
            )
        self.after(3200, self._close)

    def _close(self):
        cb = self._on_complete
        try:
            self.destroy()
        except Exception:
            pass
        cb()


# ── Animated Logo ─────────────────────────────────────────────────────────────

class AnimatedLogo(tk.Canvas):
    def __init__(self, parent, size=48, **kwargs):
        super().__init__(parent, width=size, height=size,
                         bg=BG_PANEL, highlightthickness=0, **kwargs)
        self._s    = size
        self._t    = 0
        self._animate()

    def _animate(self):
        self.delete("all")
        c = self._s // 2
        t = self._t

        # Outer glow pulse
        glow_r = c - 2 + 2 * math.sin(t * 0.06)
        gv = int(20 + 10 * math.sin(t * 0.04))
        self.create_oval(c - glow_r - 4, c - glow_r - 4,
                         c + glow_r + 4, c + glow_r + 4,
                         outline=f"#00{gv:02x}{gv*2:02x}", width=1)

        # 3 orbital arcs at different speeds and radii
        orbits = [
            (c - 4,  200, 0,    ACCENT,  2),
            (c - 11, 140, 260,  ACCENT2, 1),
            (c - 17, 90,  160,  PURPLE,  1),
        ]
        for r, ext, phase, col, w_ in orbits:
            self.create_arc(c-r, c-r, c+r, c+r,
                            start=(t * 2.2 + phase) % 360, extent=ext,
                            outline=col, width=w_, style="arc")
            # Counter-clockwise ghost
            self.create_arc(c-r, c-r, c+r, c+r,
                            start=(-t * 1.1 + phase + 180) % 360, extent=40,
                            outline=col, width=1, style="arc")

        # Pulsing core dot
        pr = 3 + 1.5 * math.sin(t * 0.08)
        gv2 = int(150 + 105 * (0.5 + 0.5 * math.sin(t * 0.07)))
        gc  = f"#00{gv2:02x}{min(255, gv2 + 55):02x}"
        self.create_oval(c - pr, c - pr, c + pr, c + pr,
                         fill=gc, outline="")

        self._t += 1
        self.after(28, self._animate)


# ── Status Dot ────────────────────────────────────────────────────────────────

class StatusDot(tk.Canvas):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, width=14, height=14,
                         bg=BG_PANEL, highlightthickness=0, **kwargs)
        self._color = TEXT_DIM
        self._t = 0
        self._animate()

    def set_status(self, s):
        self._color = {"ready": GREEN, "thinking": ACCENT,
                       "error": TEXT_ERR, "offline": TEXT_DIM}.get(s, TEXT_DIM)

    def _animate(self):
        self.delete("all")
        c = 7
        # Outer ring (breathes) — dim version of the color
        outer_r = 5 + 1.5 * abs(math.sin(self._t * 0.06))
        try:
            r = int(self._color[1:3], 16)
            g = int(self._color[3:5], 16)
            b = int(self._color[5:7], 16)
            dim = f"#{r//4:02x}{g//4:02x}{b//4:02x}"
        except Exception:
            dim = DIM
        self.create_oval(c - outer_r, c - outer_r, c + outer_r, c + outer_r,
                         outline=dim, width=1)
        # Inner dot
        self.create_oval(c - 3, c - 3, c + 3, c + 3,
                         fill=self._color, outline="")
        self._t += 1
        self.after(40, self._animate)


# ── Typing Indicator ──────────────────────────────────────────────────────────

class TypingIndicator(tk.Canvas):
    """Three bouncing dots shown while HUBERT is processing."""
    def __init__(self, parent, **kwargs):
        super().__init__(parent, width=54, height=22,
                         bg=BG_PANEL, highlightthickness=0, **kwargs)
        self._t   = 0
        self._on  = False
        self._animate()

    def show(self):
        self._on = True
        self.pack(anchor="w", padx=28, pady=(2, 4))

    def hide(self):
        self._on = False
        self.pack_forget()

    def _animate(self):
        self.delete("all")
        if self._on:
            for i in range(3):
                y  = 11 + 3.5 * math.sin(self._t * 0.18 + i * 1.1)
                r  = 3.5
                bv = int(180 + 75 * math.sin(self._t * 0.18 + i * 1.1))
                col = f"#00{min(255, bv):02x}{min(255, bv + 55):02x}"
                self.create_oval(10 + i * 17 - r, y - r,
                                  10 + i * 17 + r, y + r,
                                  fill=col, outline="")
        self._t += 1
        self.after(35, self._animate)


# ── Voice Panel ───────────────────────────────────────────────────────────────

class VoicePanel(ctk.CTkFrame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color=BG_CARD, corner_radius=10,
                         border_width=1, border_color=DIM, **kwargs)
        self._active  = False
        self._bars    = [0.0] * 32
        self._targets = [0.0] * 32
        self._t       = 0
        self._build()
        self._animate()

    def _build(self):
        self.wave = tk.Canvas(self, bg=BG_CARD, height=44,
                              highlightthickness=0)
        self.wave.pack(fill="x", padx=10, pady=(8, 2))
        self.label = ctk.CTkLabel(self, text="— voice input ready —",
                                   font=(_MONO_FONT, 9), text_color=TEXT_DIM)
        self.label.pack(pady=(0, 6))

    def set_active(self, active: bool):
        self._active = active
        if not active:
            self._targets = [0.0] * 32

    def set_transcript(self, text: str, interim=False):
        self.label.configure(text=text,
                              text_color=TEXT_DIM if interim else TEXT)

    def _animate(self):
        if self._active:
            for i in range(len(self._targets)):
                self._targets[i] = random.uniform(0.1, 1.0)
        else:
            amp = 0.08 + 0.06 * abs(math.sin(self._t * 0.025))
            for i in range(len(self._targets)):
                self._targets[i] = amp * (0.7 + 0.3 * math.sin(i * 0.5 + self._t * 0.03))

        for i in range(len(self._bars)):
            self._bars[i] += (self._targets[i] - self._bars[i]) * 0.22

        self._draw_wave()
        self._t += 1
        self.after(35, self._animate)

    def _draw_wave(self):
        c = self.wave
        c.delete("all")
        w  = c.winfo_width() or 500
        h  = 44
        n  = len(self._bars)
        bw = (w - 20) / n

        for i, val in enumerate(self._bars):
            bh  = max(2, val * (h - 8))
            x   = 10 + i * bw + bw * 0.12
            bw_ = bw * 0.76
            y0  = (h - bh) / 2
            y1  = (h + bh) / 2
            if self._active:
                v   = int(80 + 175 * val)
                col = f"#00{min(255,v):02x}{min(255,v+30):02x}"
            else:
                v   = int(20 + 18 * val)
                col = f"#{v:02x}{v+4:02x}{v+18:02x}"
            c.create_rectangle(x, y0, x + bw_, y1, fill=col, outline="")


# ── Chat Display ──────────────────────────────────────────────────────────────

class ChatDisplay(ctk.CTkFrame):
    """Bubble-style chat with smooth scroll. User = right, HUBERT = left."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color=BG_PANEL, corner_radius=12,
                         border_width=1, border_color=DIM, **kwargs)
        self._streaming       = False
        self._stream_label    = None
        self._stream_text     = ""
        self._typing          = None
        self._photos: list    = []   # keep PhotoImage refs alive
        self._build()

    def _build(self):
        self._sf = ctk.CTkScrollableFrame(
            self, fg_color=BG_PANEL, corner_radius=0,
            scrollbar_button_color=DIM2,
            scrollbar_button_hover_color=DIM,
        )
        self._sf.pack(fill="both", expand=True, padx=0, pady=0)
        # Typing indicator lives inside the scrollable frame
        self._typing = TypingIndicator(self._sf)
        # Working indicator — floats at bottom-left of the chat area (hidden until active)
        self._working = WorkingIndicator(self)
        # Grab the inner canvas so we can forward scroll events to it
        self._scroll_canvas = self._sf._parent_canvas
        self._stream_resize_id = None
        # Bind Enter/Leave on the ChatDisplay frame to capture all scroll while hovering
        self.bind("<Enter>", lambda e: self.bind_all("<MouseWheel>", self._on_scroll))
        self.bind("<Leave>", self._on_leave_scroll)

    def _on_scroll(self, event):
        try:
            self._scroll_canvas.yview_scroll(int(-1 * event.delta), "units")
        except Exception:
            pass

    def _on_leave_scroll(self, event):
        # Only release scroll grab if mouse truly left the ChatDisplay (not just a child)
        try:
            x, y = self.winfo_pointerxy()
            w = self.winfo_containing(x, y)
            while w:
                if w is self:
                    return
                w = w.master
        except Exception:
            pass
        self.unbind_all("<MouseWheel>")

    def _bind_scroll(self, widget):
        """Recursively bind mousewheel on widget and all descendants."""
        try:
            widget.bind("<MouseWheel>", self._on_scroll)
            for child in widget.winfo_children():
                self._bind_scroll(child)
        except Exception:
            pass

    @staticmethod
    def _selectable(parent, text: str, *, fg: str, bg: str, font,
                    padx=12, pady=9, justify="left") -> "tk.Text":
        """
        Selectable read-only text widget — drop-in for tk.Label in chat bubbles.
        Auto-sizes its height to fit content; supports copy via mouse drag or Cmd+C.
        """
        t = tk.Text(
            parent,
            wrap="word",
            state="disabled",
            relief="flat",
            bd=0,
            highlightthickness=0,
            fg=fg,
            bg=bg,
            font=font,
            padx=padx,
            pady=pady,
            cursor="xterm",
            selectbackground="#1a4a70",
            selectforeground="#ffffff",
            width=1,
            height=1,
            spacing1=0,
            spacing2=2,
            spacing3=0,
        )
        t.tag_configure("c", justify=justify)
        t.configure(state="normal")
        t.insert("1.0", text, "c")
        t.configure(state="disabled")

        def _fit(t=t):
            try:
                lines = t.count("1.0", "end", "displaylines")
                if lines and lines[0]:
                    t.configure(height=lines[0])
            except Exception:
                pass

        t.after(30, _fit)
        t.bind("<Configure>", lambda e: t.after(10, _fit))
        return t

    def set_working(self, active: bool):
        self._working.set_active(active)

    def _scroll_bottom(self):
        def _do():
            try:
                self._sf.update_idletasks()
                self._sf._parent_canvas.yview_moveto(1.0)
            except Exception:
                pass
        self.after(40, _do)

    # ── User bubble ──
    def add_user(self, text: str):
        self._hide_typing()
        outer = tk.Frame(self._sf, bg=BG_PANEL)
        outer.pack(fill="x", pady=(10, 2), padx=14)
        tk.Label(outer, text=f"YOU  {ts()}",
                 font=F_TAG, fg=TEXT_DIM, bg=BG_PANEL,
                 anchor="e").pack(anchor="e", padx=2)
        bubble = tk.Frame(outer, bg=USR_BG,
                          highlightbackground=USR_BORDER,
                          highlightthickness=1)
        bubble.pack(anchor="e", fill="x")
        lbl = self._selectable(bubble, text, fg=TEXT_USR, bg=USR_BG,
                               font=F_CHAT, padx=14, pady=9, justify="right")
        lbl.pack(fill="x")
        self._bind_scroll(outer)
        self._scroll_bottom()

    # ── File card (attached / generated document) ──
    def file_card(self, name: str, path: str, info: str = "",
                  thumb_path: str = None):
        """
        Show a compact file card with an optional thumbnail, file info, and Open button.
        Used for both incoming attachments and HUBERT-generated output documents.
        """
        _EXT_ICONS = {
            "pdf": "📄", "docx": "📝", "doc": "📝",
            "txt": "📃", "md": "📃", "csv": "📊", "gdoc": "📗",
        }
        ext  = Path(name).suffix.lower().lstrip(".")
        icon = _EXT_ICONS.get(ext, "📁")

        outer = tk.Frame(self._sf, bg=BG_CARD,
                         highlightbackground=DIM2, highlightthickness=1)
        outer.pack(fill="x", padx=14, pady=(3, 1))

        row = tk.Frame(outer, bg=BG_CARD)
        row.pack(fill="x", padx=8, pady=6)

        # Optional thumbnail (PDF page render)
        if thumb_path:
            try:
                from PIL import Image, ImageTk
                img = Image.open(thumb_path)
                img.thumbnail((56, 76), Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                self._photos.append(photo)   # prevent GC
                thumb_lbl = tk.Label(row, image=photo, bg=BG_CARD,
                                     relief="flat", cursor="hand2")
                thumb_lbl.image = photo
                thumb_lbl.pack(side="left", padx=(0, 10))
            except Exception:
                pass

        # Name + info
        meta = tk.Frame(row, bg=BG_CARD)
        meta.pack(side="left", fill="x", expand=True)
        tk.Label(meta, text=f"{icon}  {name}",
                 font=(_MONO_FONT, 10, "bold"), fg=TEXT, bg=BG_CARD,
                 anchor="w").pack(anchor="w")
        if info:
            tk.Label(meta, text=info,
                     font=(_MONO_FONT, 8), fg=TEXT_DIM, bg=BG_CARD,
                     anchor="w").pack(anchor="w")

        # Open button
        def _open_file(p=path):
            import subprocess, platform as _plat
            if _plat.system() == "Darwin":
                subprocess.run(["open", p], check=False)
            elif _plat.system() == "Windows":
                subprocess.run(["start", "", p], shell=True, check=False)
            else:
                subprocess.run(["xdg-open", p], check=False)

        ctk.CTkButton(row, text="Open", width=54, height=26,
                      fg_color=DIM, hover_color=ACCENT2, text_color=TEXT,
                      font=(_MONO_FONT, 9), corner_radius=4,
                      command=_open_file).pack(side="right", padx=(8, 0))

        self._bind_scroll(outer)
        self._scroll_bottom()

    # ── HUBERT bubble ──
    def start_hubert(self):
        self._hide_typing()
        outer = tk.Frame(self._sf, bg=BG_PANEL)
        outer.pack(fill="x", pady=(10, 2), padx=14)
        tk.Label(outer, text=f"HUBERT  {ts()}",
                 font=F_TAG, fg=ACCENT, bg=BG_PANEL,
                 anchor="w").pack(anchor="w", padx=6)
        row = tk.Frame(outer, bg=BG_PANEL)
        row.pack(fill="x")
        # Accent left bar
        tk.Frame(row, bg=ACCENT, width=2).pack(side="left", fill="y", padx=(4, 0))
        bubble = tk.Frame(row, bg=HUB_BG)
        bubble.pack(side="left", fill="x", expand=True, padx=(6, 4), pady=2)
        # Selectable streaming Text widget (replaces Label)
        t = tk.Text(
            bubble,
            wrap="word",
            state="disabled",
            relief="flat",
            bd=0,
            highlightthickness=0,
            fg=TEXT,
            bg=HUB_BG,
            font=F_CHAT,
            padx=12,
            pady=9,
            cursor="xterm",
            selectbackground="#1a4a70",
            selectforeground="#ffffff",
            width=1,
            height=1,
            spacing1=0,
            spacing2=2,
            spacing3=0,
        )
        t.pack(anchor="w", fill="x")
        self._stream_label = t
        self._stream_text  = ""
        self._streaming    = True
        self._bind_scroll(outer)
        self._scroll_bottom()

    def stream(self, chunk: str):
        if not self._streaming:
            self.start_hubert()
        self._stream_text += chunk
        t = self._stream_label
        if t:
            try:
                t.configure(state="normal")
                t.insert("end", chunk)
                t.configure(state="disabled")
                # Debounced height resize — avoid reflow on every single token
                if self._stream_resize_id:
                    self.after_cancel(self._stream_resize_id)
                def _fit(t=t):
                    try:
                        lines = t.count("1.0", "end", "displaylines")
                        if lines and lines[0]:
                            t.configure(height=lines[0])
                    except Exception:
                        pass
                self._stream_resize_id = self.after(80, _fit)
            except Exception:
                pass
        self._scroll_bottom()

    def end_hubert(self):
        # Final height fit on stream end
        t = self._stream_label
        if t:
            try:
                lines = t.count("1.0", "end", "displaylines")
                if lines and lines[0]:
                    t.configure(height=lines[0])
            except Exception:
                pass
        self._streaming    = False
        self._stream_label = None
        self._stream_text  = ""
        self._stream_resize_id = None
        self._hide_typing()

    # ── Tool pills ──
    def tool_call(self, name: str, params: dict):
        ps  = ", ".join(f"{k}={repr(v)[:28]}" for k, v in list(params.items())[:2])
        txt = f"⚙  {name}({ps})"
        f   = tk.Frame(self._sf, bg=TOOL_BG,
                       highlightbackground="#0a2a1a", highlightthickness=1)
        f.pack(anchor="w", padx=30, pady=(1, 0))
        tk.Label(f, text=txt, font=(_MONO_FONT, 9),
                 fg=TEXT_TOOL, bg=TOOL_BG, padx=10, pady=4).pack(anchor="w")
        self._bind_scroll(f)
        self._scroll_bottom()

    def tool_result(self, name: str, result: str):
        r   = result[:150].replace("\n", " ") + ("…" if len(result) > 150 else "")
        f   = tk.Frame(self._sf, bg=BG)
        f.pack(anchor="w", padx=34, pady=(0, 1))
        lbl = self._selectable(f, f"  → {r}", fg=TEXT_DIM, bg=BG,
                               font=(_MONO_FONT, 8), padx=8, pady=3)
        lbl.pack(anchor="w", fill="x")
        self._bind_scroll(f)
        self._scroll_bottom()

    def error(self, text: str):
        f = tk.Frame(self._sf, bg=ERR_BG,
                     highlightbackground="#330010", highlightthickness=1)
        f.pack(fill="x", padx=14, pady=6)
        lbl = self._selectable(f, f"✗  {text}", fg=TEXT_ERR, bg=ERR_BG,
                               font=F_SMALL, padx=12, pady=8)
        lbl.pack(anchor="w", fill="x")
        self._bind_scroll(f)
        self._scroll_bottom()

    def add_status(self, msg: str):
        """Append a grey italic status line (e.g. rate-limit retry notice)."""
        row = tk.Frame(self._sf, bg=BG)
        row.pack(fill="x", padx=8, pady=(0, 4))
        lbl = tk.Label(
            row,
            text=msg,
            font=(_MONO_FONT, 10, "italic"),
            fg="#888888",
            bg=BG,
            anchor="w",
            wraplength=560,
            justify="left",
        )
        lbl.pack(fill="x")
        self._scroll_bottom()

    def system(self, text: str):
        lbl = tk.Label(self._sf, text=f"◈  {text}",
                       font=(_MONO_FONT, 9), fg=ACCENT2, bg=BG_PANEL,
                       anchor="center")
        lbl.pack(pady=6)
        self._bind_scroll(lbl)
        self._scroll_bottom()

    def show_typing(self):
        if self._typing:
            self._typing.show()
            self._scroll_bottom()

    def _hide_typing(self):
        if self._typing:
            self._typing.hide()

    def clear(self):
        self._hide_typing()
        for w in self._sf.winfo_children():
            if w is not self._typing:
                w.destroy()
        # Re-add typing indicator at end
        self._typing = TypingIndicator(self._sf)
        self._streaming = False
        self._stream_label = None
        self._stream_text  = ""


# ── Working Indicator ─────────────────────────────────────────────────────────

class WorkingIndicator(ctk.CTkFrame):
    """Small animated 'WORKING...' strip shown above the input bar while HUBERT is responding."""

    ORB_R   = 7       # orb sphere radius
    TRAIL   = 10      # number of trail dots
    W       = 120     # canvas width
    H       = 22      # canvas height

    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color="transparent", height=self.H + 4, **kwargs)
        self._active   = False
        self._angle    = 0.0
        self._after_id = None
        self._build()

    def _build(self):
        inner = ctk.CTkFrame(self, fg_color="transparent")
        inner.pack(side="left", fill="y", padx=(6, 0))

        # Canvas for the 3-D spinning orb
        self._canvas = tk.Canvas(
            inner,
            width=self.W, height=self.H,
            bg="#0a0a0f", highlightthickness=0, bd=0,
        )
        self._canvas.pack(side="left", padx=(0, 8))

        # "WORKING..." label
        self._label = ctk.CTkLabel(
            inner,
            text="WORKING...",
            font=(_MONO_FONT, 9, "bold"),
            text_color=ACCENT,
        )
        self._label.pack(side="left")

    # ── public API ──────────────────────────────────────────────────────────

    def set_active(self, active: bool):
        if active == self._active:
            return
        self._active = active
        if active:
            self.place(x=10, rely=1.0, anchor="sw", y=-8)
            self.lift()   # float above the scrollable frame
            self._loop()
        else:
            if self._after_id:
                try:
                    self.after_cancel(self._after_id)
                except Exception:
                    pass
                self._after_id = None
            self._canvas.delete("all")
            self.place_forget()

    # ── animation ───────────────────────────────────────────────────────────

    def _loop(self):
        if not self._active:
            return
        self._paint()
        self._angle += 0.07
        self._after_id = self.after(28, self._loop)

    def _paint(self):
        c   = self._canvas
        c.delete("all")
        cx  = self.W // 2
        cy  = self.H // 2
        a   = self._angle

        # Orbit path radius
        rx, ry = 42, 7

        # Draw trail dots (fading)
        for i in range(self.TRAIL):
            t      = a - i * 0.22
            ox     = cx + rx * math.cos(t)
            oy     = cy + ry * math.sin(t)
            depth  = 0.5 + 0.5 * math.sin(t)            # 0..1, back→front
            alpha  = max(0.0, 1.0 - i / self.TRAIL)
            sz     = max(1, int((self.ORB_R - 2) * depth * alpha * 0.6))
            # Color: dim cyan → bright cyan depending on depth & trail pos
            bright = int(alpha * depth * 180)
            col    = f"#{0:02x}{bright:02x}{min(255, bright + 60):02x}"
            c.create_oval(ox - sz, oy - sz, ox + sz, oy + sz, fill=col, outline="")

        # Main orb — front/back depth shading
        ox    = cx + rx * math.cos(a)
        oy    = cy + ry * math.sin(a)
        depth = 0.5 + 0.5 * math.sin(a)
        r     = max(2, int(self.ORB_R * (0.6 + 0.4 * depth)))

        # Gradient-like 3-D shading via concentric ovals
        for layer in range(r, 0, -1):
            t_layer = layer / r
            # Core: bright cyan highlight; rim: deep blue
            rb = int(20  + (0x00 - 20)  * t_layer)
            gb = int(180 + (0xd4 - 180) * (1 - t_layer) * depth)
            bb = int(220 + (0xff - 220) * t_layer)
            rb, gb, bb = max(0, min(255, rb)), max(0, min(255, gb)), max(0, min(255, bb))
            col = f"#{rb:02x}{gb:02x}{bb:02x}"
            c.create_oval(ox - layer, oy - layer, ox + layer, oy + layer,
                          fill=col, outline="")

        # Specular highlight (small white dot, upper-left of orb)
        hx, hy = ox - r * 0.3, oy - r * 0.3
        hs = max(1, r // 3)
        c.create_oval(hx - hs, hy - hs, hx + hs, hy + hs,
                      fill="#ccf0ff", outline="")


# ── Input Bar ─────────────────────────────────────────────────────────────────

class InputBar(ctk.CTkFrame):
    def __init__(self, parent, on_send, on_camera=None, **kwargs):
        super().__init__(parent, fg_color=BG_INPUT, corner_radius=12,
                         border_width=2, border_color=DIM, **kwargs)
        self._on_send        = on_send
        self._on_camera      = on_camera
        self._mic_active     = False   # True = always-on listen loop running
        self._voice_thread   = None
        self._glow           = False
        self._glow_t         = 0
        self._attached_files: list[str] = []   # paths of pending attachments
        self._attach_prefix  = ""             # prefix injected into entry for display
        self._build()
        self._animate_border()

    def _build(self):
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="both", expand=True, padx=10, pady=8)

        # Left icons — mic + file upload
        icons = ctk.CTkFrame(row, fg_color="transparent")
        icons.pack(side="left", fill="y", padx=(0, 8))
        self.mic_btn = ctk.CTkButton(
            icons, text="🎤", width=36, height=25,
            fg_color=DIM, hover_color=DIM2, text_color=TEXT,
            font=("Segoe UI Emoji", 12), corner_radius=8,
            command=self._toggle_mic)
        self.mic_btn.pack(pady=(0, 2))
        self.upload_btn = ctk.CTkButton(
            icons, text="📎", width=36, height=25,
            fg_color=DIM, hover_color=DIM2, text_color=TEXT,
            font=("Segoe UI Emoji", 12), corner_radius=8,
            command=self._pick_file)
        self.upload_btn.pack()

        # Text entry
        self.entry = ctk.CTkTextbox(
            row, height=60, fg_color=BG,
            text_color=TEXT, font=F_CHAT,
            border_color=DIM, border_width=0,
            corner_radius=8, wrap="word")
        self.entry.pack(side="left", fill="both", expand=True, padx=(0, 8))
        self.entry.bind("<Return>",       self._enter_key)
        self.entry.bind("<Shift-Return>", lambda e: None)
        self.entry.bind("<FocusIn>",      lambda e: self._set_glow(True))
        self.entry.bind("<FocusOut>",     lambda e: self._set_glow(False))

        # Send button
        self.send_btn = ctk.CTkButton(
            row, text="SEND", width=70, height=60,
            fg_color=ACCENT2, hover_color="#4422cc",
            text_color="white", font=(_MONO_FONT, 10, "bold"),
            corner_radius=8, command=self._fire)
        self.send_btn.pack(side="right", fill="y")

    # ── Animated glow border ──
    def _set_glow(self, active: bool):
        self._glow = active

    def set_thinking(self, thinking: bool):
        self._thinking = thinking

    def _animate_border(self):
        if getattr(self, "_glow", False) or getattr(self, "_thinking", False):
            self._glow_t += 0.12
            v   = 0.5 + 0.5 * math.sin(self._glow_t)
            c1  = (0x1a, 0x28, 0x48)         # DIM2
            c2  = (0x66, 0x44, 0xff)          # ACCENT2/purple when thinking
            if not getattr(self, "_thinking", False):
                c2 = (0x00, 0xd4, 0xff)       # ACCENT when focused
            r  = int(c1[0] + (c2[0]-c1[0]) * v)
            g  = int(c1[1] + (c2[1]-c1[1]) * v)
            b  = int(c1[2] + (c2[2]-c1[2]) * v)
            try:
                self.configure(border_color=f"#{r:02x}{g:02x}{b:02x}")
            except Exception:
                pass
        else:
            try:
                self.configure(border_color=DIM)
            except Exception:
                pass
        self.after(35, self._animate_border)

    def _enter_key(self, e):
        if not (e.state & 1):
            self._fire()
            return "break"

    def _fire(self):
        raw = self.entry.get("1.0", "end").strip()
        # Strip the attachment prefix if present
        if self._attach_prefix and raw.startswith(self._attach_prefix):
            raw = raw[len(self._attach_prefix):]
        file_paths = list(self._attached_files)
        if raw or file_paths:
            self.entry.delete("1.0", "end")
            self._clear_attachment()
            self._on_send(raw, file_paths=file_paths)

    def _pick_file(self):
        """Open a file picker; allow multiple selections and show a badge."""
        from tkinter import filedialog
        from pathlib import Path as _Path
        paths = filedialog.askopenfilenames(title="Attach files")
        if not paths:
            return
        self._attached_files.extend(paths)
        n = len(self._attached_files)
        if n == 1:
            self._attach_prefix = f"📎 {_Path(self._attached_files[0]).name} — "
        else:
            self._attach_prefix = f"📎 {n} files — "
        self.upload_btn.configure(
            text=f"📎{n}", fg_color=ACCENT2, hover_color="#3311aa",
        )
        # Rebuild entry with new prefix
        rest = self.entry.get("1.0", "end").strip()
        # Strip any old prefix
        for prefix_check in [self._attach_prefix]:
            if rest.startswith(prefix_check):
                rest = rest[len(prefix_check):]
        self.entry.delete("1.0", "end")
        self.entry.insert("1.0", self._attach_prefix + rest)
        self.entry.mark_set("insert", "end")
        self.entry.focus_set()

    def _clear_attachment(self):
        """Remove all attachment state."""
        self._attached_files.clear()
        self._attach_prefix = ""
        self.upload_btn.configure(text="📎", fg_color=DIM, hover_color=DIM2)

    def set_enabled(self, v: bool):
        s = "normal" if v else "disabled"
        self.send_btn.configure(state=s)
        self.entry.configure(state=s)
        self.set_thinking(not v)
        # Don't kill the always-on listen loop when input is disabled during inference

    def insert_text(self, t: str):
        self.entry.delete("1.0", "end")
        self.entry.insert("1.0", t)

    # ── Mic toggle ────────────────────────────────────────────────────────────

    def _toggle_mic(self):
        if self._mic_active:
            self._mic_active = False
            self.mic_btn.configure(fg_color=DIM, text="🎤")
            if hasattr(self, "_on_mic_state"):
                self._on_mic_state(False)
        else:
            self._mic_active = True
            self.mic_btn.configure(fg_color="#006633", text="🔴")
            if hasattr(self, "_on_mic_state"):
                self._on_mic_state(True)
            self._voice_thread = threading.Thread(
                target=self._listen_loop, daemon=True)
            self._voice_thread.start()

    def _listen_loop(self):
        """
        Always-on VAD loop with smart speech stitching.

        Flow per utterance:
          1. Capture phrase (no timeout — waits silently)
          2. Transcribe immediately in background thread
          3. 550ms stitch window: if another fragment arrives, join them
          4. If result looks like a cut-off sentence, ask Ollama to complete it
             (this runs in parallel with TTS synthesis — no perceived delay)
          5. Fire completed text to HUBERT
          6. Return to step 1
        """
        try:
            import speech_recognition as sr
            import tempfile, queue as _q

            def _status(msg):
                if hasattr(self, "_on_transcript"):
                    self.after(0, lambda m=msg: self._on_transcript(m, True))

            def _transcribe(audio) -> str:
                """Whisper → Google fallback. Returns empty string on failure."""
                model = _get_whisper()
                if model is not None:
                    try:
                        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
                        tmp.write(audio.get_wav_data())
                        tmp.close()
                        result = model.transcribe(tmp.name, fp16=False,
                                                  language="en", condition_on_previous_text=False)
                        os.unlink(tmp.name)
                        return result.get("text", "").strip()
                    except Exception:
                        pass
                try:
                    r2 = sr.Recognizer()
                    return r2.recognize_google(audio)
                except Exception:
                    return ""

            def _looks_partial(text: str) -> bool:
                """Heuristic: does this look like a cut-off phrase?"""
                if not text:
                    return False
                t = text.strip()
                # Very short (< 4 words) unless it's clearly a command
                if len(t.split()) < 4 and not any(
                    t.lower().startswith(w) for w in
                    ("open", "play", "run", "show", "go", "find",
                     "what", "who", "how", "when", "where", "why",
                     "can", "is", "are", "do", "did", "will", "yes", "no")
                ):
                    return True
                # Ends mid-sentence (no terminal punctuation, ends with conjunction/preposition)
                last_word = t.split()[-1].lower().rstrip(".,!?")
                partial_endings = {
                    "and", "but", "or", "the", "a", "an", "to", "in",
                    "on", "at", "with", "for", "of", "about", "because",
                    "that", "which", "when", "if", "so", "then", "i",
                }
                return last_word in partial_endings

            def _stitch(parts: list[str]) -> str:
                """Join fragments. If still looks partial, use ollama to complete."""
                joined = " ".join(p for p in parts if p).strip()
                if not _looks_partial(joined):
                    return joined
                # Quick local Ollama call to fill in the intent (non-blocking feel
                # because TTS synthesis takes ~300ms anyway)
                try:
                    import requests as _req
                    body = {
                        "model":   "llama3",
                        "messages": [{
                            "role": "user",
                            "content": (
                                f'The user said (possibly cut off): "{joined}"\n'
                                "Complete or correct this into a single clear sentence "
                                "that preserves the user's intent. "
                                "Reply with ONLY the corrected sentence, nothing else."
                            )
                        }],
                        "stream":  False,
                        "options": {"num_predict": 60, "temperature": 0.1},
                    }
                    resp = _req.post("http://localhost:11434/api/chat",
                                     json=body, timeout=3)
                    corrected = resp.json().get("message", {}).get("content", "").strip()
                    if corrected:
                        return corrected
                except Exception:
                    pass
                return joined

            r = sr.Recognizer()
            r.dynamic_energy_threshold = True
            r.energy_threshold         = 300
            r.pause_threshold          = 0.7

            mic = sr.Microphone(device_index=_get_mic_index())

            with mic as src:
                _status("🎤 Calibrating…")
                r.adjust_for_ambient_noise(src, 0.4)
                _status("🎤 Listening…")

            while self._mic_active:
                # ── Capture phrase ────────────────────────────────────────────
                try:
                    with mic as src:
                        audio = r.listen(src, timeout=None, phrase_time_limit=12)
                except Exception:
                    time.sleep(0.05)
                    continue

                if not self._mic_active:
                    break

                _status("⟳ Transcribing…")

                # ── Transcribe first fragment ─────────────────────────────────
                text1 = _transcribe(audio)
                if not text1:
                    _status("🎤 Listening…")
                    continue

                # ── Stitch window (550ms) — catch cut-off second fragment ─────
                fragments = [text1]
                if _looks_partial(text1):
                    stitch_deadline = time.time() + 0.55
                    while time.time() < stitch_deadline and self._mic_active:
                        try:
                            with mic as src:
                                audio2 = r.listen(
                                    src,
                                    timeout=stitch_deadline - time.time(),
                                    phrase_time_limit=8,
                                )
                            t2 = _transcribe(audio2)
                            if t2:
                                fragments.append(t2)
                            break
                        except Exception:
                            break

                final = _stitch(fragments)
                if final:
                    self.after(0, lambda t=final: self._voice_fire(t))
                    time.sleep(0.2)

                if self._mic_active:
                    _status("🎤 Listening…")

        except Exception as e:
            self.after(0, lambda err=str(e): self._voice_error(err))

    def _voice_fire(self, text: str):
        """Called on main thread after a successful transcription."""
        if hasattr(self, "_on_transcript"):
            self._on_transcript(f"✓ {text}", False)
        self.insert_text(text)
        self.after(200, self._fire)

    def _voice_error(self, msg: str):
        self._mic_active = False
        self.mic_btn.configure(fg_color=DIM, text="🎤")
        if hasattr(self, "_on_mic_state"):
            self._on_mic_state(False)
        if hasattr(self, "_on_transcript"):
            self._on_transcript(f"⚠ {msg}", False)


# ── Skills Dialog ─────────────────────────────────────────────────────────────

def _is_custom(name: str) -> bool:
    return (Path(__file__).parent / "tools" / "custom" / f"{name}.py").exists()


class SkillsDialog(SafeTopLevel):
    GROUPS = [
        ("⌨  COMPUTER CONTROL",    lambda n: not n.startswith("browser_") and n not in {
            "write_new_tool", "list_tools", "delete_custom_tool", "show_tool_code"}
         and not _is_custom(n)),
        ("🌐  BROWSER AUTOMATION",  lambda n: n.startswith("browser_")),
        ("🔧  SELF-EXTENSION",      lambda n: n in {
            "write_new_tool", "list_tools", "delete_custom_tool", "show_tool_code"}),
        ("✨  CUSTOM / PLUGINS",    _is_custom),
    ]

    def __init__(self, parent):
        super().__init__(parent)
        self.title("HUBERT — Skills & Capabilities")
        self.geometry("660x600")
        self.configure(fg_color=BG_CARD)
        self.resizable(True, True)
        self._build()

    def _build(self):
        hdr = ctk.CTkFrame(self, fg_color=BG_PANEL, corner_radius=0, height=48)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="  ◈  HUBERT SKILLS & CAPABILITIES",
                     font=(_MONO_FONT, 12, "bold"),
                     text_color=ACCENT).pack(side="left", pady=10, padx=10)
        ctk.CTkButton(hdr, text="✕", width=32, height=32,
                      fg_color="transparent", hover_color=DIM,
                      text_color=TEXT_DIM, font=(_MONO_FONT, 12),
                      command=self.destroy).pack(side="right", padx=8)
        tk.Frame(self, bg=DIM, height=1).pack(fill="x")

        sf = ctk.CTkScrollableFrame(self, fg_color=BG_CARD,
                                     scrollbar_button_color=DIM2)
        sf.pack(fill="both", expand=True, padx=10, pady=10)

        import tools as tr
        all_tools = {t["name"]: t for t in tr.get_tool_definitions()}

        for group_name, predicate in self.GROUPS:
            group_tools = [t for name, t in all_tools.items() if predicate(name)]
            if not group_tools:
                continue
            gf = ctk.CTkFrame(sf, fg_color=BG_PANEL, corner_radius=6)
            gf.pack(fill="x", pady=(8, 2))
            ctk.CTkLabel(gf, text=f"  {group_name}  ({len(group_tools)})",
                         font=(_MONO_FONT, 10, "bold"),
                         text_color=ACCENT2).pack(side="left", padx=8, pady=6)
            for tool in sorted(group_tools, key=lambda t: t["name"]):
                row = ctk.CTkFrame(sf, fg_color=BG, corner_radius=4)
                row.pack(fill="x", pady=1, padx=4)
                ctk.CTkLabel(row, text=f"  {tool['name']}",
                             font=(_MONO_FONT, 10, "bold"),
                             text_color=TEXT_TOOL, width=220,
                             anchor="w").pack(side="left", padx=(6, 0), pady=5)
                ctk.CTkLabel(row, text=tool.get("description", "")[:120],
                             font=(_MONO_FONT, 9), text_color=TEXT_DIM,
                             anchor="w", wraplength=370,
                             justify="left").pack(side="left", padx=8, pady=5)

        total = len(all_tools)
        ctk.CTkLabel(self, text=f"  {total} total skills loaded",
                     font=(_MONO_FONT, 9), text_color=TEXT_DIM).pack(
            anchor="w", padx=14, pady=(0, 8))


# ── Sphere Widget ─────────────────────────────────────────────────────────────

class SphereWidget(tk.Canvas):
    """Orange JARVIS-style morphing blob. Idle: slow amber pulse.
    Speaking: faster morph + rings. Muted: frozen indigo. Click to toggle mute."""

    H       = 160
    N_PTS   = 24
    BG_RGB  = (6, 8, 16)   # matches BG = "#060810"

    def __init__(self, parent, on_mute_toggle=None, **kwargs):
        super().__init__(parent, height=self.H, bg=BG,
                         highlightthickness=0, **kwargs)
        self._speaking       = False
        self._muted          = False
        self._t              = 0.0
        self._rings          = [0.0, 0.333, 0.666]
        self._mute_flash     = 0
        self._on_mute_toggle = on_mute_toggle
        self.bind("<Button-1>", self._on_click)
        self._animate()

    # ── Public API ────────────────────────────────────────────────────────────

    def set_speaking(self, active: bool):
        self._speaking = active

    def set_muted(self, active: bool):
        if active and not self._muted:
            self._mute_flash = 30
        self._muted = active

    # ── Interaction ───────────────────────────────────────────────────────────

    def _on_click(self, _event):
        new_state = not self._muted
        self.set_muted(new_state)
        if self._on_mute_toggle:
            self._on_mute_toggle(new_state)

    # ── Animation ─────────────────────────────────────────────────────────────

    def _animate(self):
        try:
            if not self._muted:
                self._t += 2.0 if self._speaking else 1.0
            if self._speaking and not self._muted:
                for i in range(len(self._rings)):
                    self._rings[i] = (self._rings[i] + 0.012) % 1.0
            if self._mute_flash > 0:
                self._mute_flash -= 1
            self._draw()
            self.after(33, self._animate)
        except tk.TclError:
            pass

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _blob_pts(self, cx, cy, base_r):
        """Return flat list of x,y polygon points for a morphing blob."""
        pts = []
        t = self._t
        for i in range(self.N_PTS):
            a = 2 * math.pi * i / self.N_PTS
            r = (base_r
                 + base_r * 0.18 * math.sin(a * 3 + t * 0.05)
                 + base_r * 0.12 * math.sin(a * 5 - t * 0.03)
                 + base_r * 0.08 * math.cos(a * 7 + t * 0.07))
            pts.append(cx + r * math.cos(a))
            pts.append(cy + r * math.sin(a))
        return pts

    def _blend(self, orb_rgb, alpha):
        """Blend orb_rgb toward BG_RGB at given alpha (0=BG, 1=orb)."""
        br, bg_, bb = self.BG_RGB
        r = int(br + (orb_rgb[0] - br) * alpha)
        g = int(bg_ + (orb_rgb[1] - bg_) * alpha)
        b = int(bb + (orb_rgb[2] - bb) * alpha)
        return f"#{r:02x}{g:02x}{b:02x}"

    # ── Draw ──────────────────────────────────────────────────────────────────

    def _draw(self):
        self.delete("all")
        w = self.winfo_width()
        if w < 10:
            return
        cx = w // 2
        cy = self.H // 2

        if self._muted:
            orb_rgb = (106, 0, 255)   # indigo
            base_r  = 30
        elif self._speaking:
            orb_rgb = (255, 170, 0)   # bright amber
            base_r  = 42
        else:
            orb_rgb = (255, 140, 0)   # deep orange
            base_r  = 38

        # Speaking rings (drawn behind blob)
        if self._speaking and not self._muted:
            for phase in self._rings:
                rr  = 24 + phase * 40
                col = self._blend(orb_rgb, (1.0 - phase) * 0.5)
                self.create_oval(cx - rr, cy - rr, cx + rr, cy + rr,
                                 outline=col, width=1)

        # Outer glow layer
        self.create_polygon(*self._blob_pts(cx, cy, base_r * 1.6),
                            fill=self._blend(orb_rgb, 0.10), outline="",
                            smooth=True)

        # Mid glow layer
        self.create_polygon(*self._blob_pts(cx, cy, base_r * 1.3),
                            fill=self._blend(orb_rgb, 0.20), outline="",
                            smooth=True)

        # Core blob
        self.create_polygon(*self._blob_pts(cx, cy, base_r),
                            fill=self._blend(orb_rgb, 0.12),
                            outline=self._blend(orb_rgb, 1.0),
                            width=2, smooth=True)

        # Inner highlight spot
        hl_x = cx - base_r // 3
        hl_y = cy - base_r // 3
        self.create_oval(hl_x - 4, hl_y - 4, hl_x + 4, hl_y + 4,
                         fill=self._blend(orb_rgb, 0.75), outline="")

        # State label
        label_y = cy + base_r + 16
        if self._mute_flash > 0:
            self.create_text(cx, cy, text="🔇",
                             font=(_MONO_FONT, 14),
                             fill=self._blend(orb_rgb, 1.0))
        elif self._muted:
            self.create_text(cx, label_y, text="MUTED",
                             font=(_MONO_FONT, 7),
                             fill=self._blend(orb_rgb, 1.0))
        elif self._speaking:
            self.create_text(cx, label_y, text="SPEAKING",
                             font=(_MONO_FONT, 7),
                             fill=self._blend(orb_rgb, 1.0))
        else:
            self.create_text(cx, label_y, text="STANDBY",
                             font=(_MONO_FONT, 7), fill=TEXT_DIM)


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
        self._expanded    = None   # "cpu" | "ram" | "net" | None
        self._t           = 0
        self._build()
        threading.Thread(target=self._poll_sysinfo, daemon=True).start()
        threading.Thread(target=self._poll_weather, daemon=True).start()
        self._tick_clock()
        self._animate_no_signal()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        HC, HD, HBG = self.HC, self.HD, self.HBG

        # Header
        hdr = tk.Frame(self, bg="#030c0a", height=28)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="  ◈  HUD",
                 font=(_MONO_FONT, 8, "bold"), fg=HC, bg="#030c0a").pack(
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

            lbl = tk.Label(frame, text=label, font=(_MONO_FONT, 9, "bold"),
                           fg=HC, bg=HBG, anchor="w")
            lbl.pack(fill="x")

            val_lbl = tk.Label(frame, text="0%", font=(_MONO_FONT, 13, "bold"),
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
        tk.Frame(inner, bg="#004840", height=1).pack(fill="x", padx=8, pady=8)

        # Clock
        self._clock_lbl = tk.Label(inner, text="00:00",
                                   font=(_MONO_FONT, 22, "bold"),
                                   fg=HC, bg=HBG, anchor="w")
        self._clock_lbl.pack(fill="x", padx=8)
        self._date_lbl = tk.Label(inner, text="",
                                  font=(_MONO_FONT, 9), fg="#00a080", bg=HBG, anchor="w")
        self._date_lbl.pack(fill="x", padx=8)

        # Divider
        tk.Frame(inner, bg="#004840", height=1).pack(fill="x", padx=8, pady=8)

        # Weather
        self._weather_lbl = tk.Label(inner, text="⛅ Fetching…",
                                     font=(_MONO_FONT, 10), fg=HC, bg=HBG,
                                     anchor="w", wraplength=140, justify="left")
        self._weather_lbl.pack(fill="x", padx=8)

        # Divider
        tk.Frame(inner, bg="#004840", height=1).pack(fill="x", padx=8, pady=8)

        # Camera
        cam_hdr = tk.Frame(inner, bg=HBG)
        cam_hdr.pack(fill="x", padx=8, pady=(0, 4))
        tk.Label(cam_hdr, text="◉ CAMERA", font=(_MONO_FONT, 9, "bold"),
                 fg=HC, bg=HBG).pack(side="left")
        # Pop-out button
        tk.Button(
            cam_hdr, text="⤢", font=(_MONO_FONT, 10),
            fg=HC, bg=HBG, activeforeground="#ffffff", activebackground=HBG,
            relief="flat", bd=0, padx=2, pady=0,
            cursor="hand2", command=self._pop_cam,
        ).pack(side="right", padx=(0, 2))
        self._cam_status_dot = tk.Canvas(cam_hdr, width=8, height=8,
                                         bg=HBG, highlightthickness=0)
        self._cam_status_dot.pack(side="right", pady=2)
        # ON/OFF toggle button
        self._cam_toggle_btn = tk.Button(
            cam_hdr, text="OFF",
            font=(_MONO_FONT, 7, "bold"),
            fg="#ff4444", bg=HBG,
            activeforeground="#ffffff", activebackground=HBG,
            relief="flat", bd=0, padx=4, pady=0,
            cursor="hand2", command=self._toggle_camera,
        )
        self._cam_toggle_btn.pack(side="right", padx=(0, 4))
        self._cam_status_dot.create_oval(1, 1, 7, 7, fill="#ff4444", outline="")

        self._cam_canvas = tk.Canvas(inner, bg="#000000", highlightthickness=1,
                                     highlightbackground="#004840",
                                     width=146, height=110)
        self._cam_canvas.pack(pady=(0, 4))

        # Capture button
        self._cam_snap_btn = tk.Button(
            inner, text="⬤  SNAPSHOT → HUBERT",
            font=(_MONO_FONT, 8, "bold"),
            fg=HBG, bg=HC, activebackground="#00a080",
            relief="flat", bd=0, padx=6, pady=3,
            state="disabled",
            command=self._cam_snapshot,
        )
        self._cam_snap_btn.pack(fill="x", padx=8, pady=(0, 4))

        self._cam_available  = False
        self._cam_running    = False   # starts OFF by default
        self._cam_img_ref    = None
        self._cam_last_frame = None   # raw PIL Image for snapshot
        self._cam_on_send    = None   # set by HubertApp after build
        self._cam_sinks      = []     # extra windows receiving live frames
        self._cam_window     = None   # current pop-out window (if any)

        # Divider
        tk.Frame(inner, bg="#004840", height=1).pack(fill="x", padx=8, pady=8)

        # Self Repair header row
        sr_hdr = tk.Frame(inner, bg=HBG)
        sr_hdr.pack(fill="x", padx=8)
        tk.Label(sr_hdr, text="⚕ SELF REPAIR", font=(_MONO_FONT, 9, "bold"),
                 fg=HC, bg=HBG).pack(side="left")
        self._sr_btn = tk.Button(sr_hdr, text="RUN",
                                 font=(_MONO_FONT, 8, "bold"),
                                 fg=HBG, bg=HC, activebackground="#00a080",
                                 relief="flat", bd=0, padx=6, pady=1,
                                 command=self._run_full_repair)
        self._sr_btn.pack(side="right")

        # Self Repair output text area
        self._sr_text = tk.Text(inner, height=6, bg="#020808", fg=HC,
                                font=(_MONO_FONT, 8), relief="flat",
                                bd=0, wrap="word", state="disabled",
                                insertbackground=HC)
        self._sr_text.pack(fill="x", padx=8, pady=(4, 8))
        self._sr_text.tag_configure("ok",   foreground="#00d4aa")
        self._sr_text.tag_configure("fail", foreground="#ff4444")
        self._sr_text.tag_configure("warn", foreground="#ffaa00")
        self._sr_text.tag_configure("dim",  foreground="#004840")

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
        try:
            self.after(0, lambda: self._weather_lbl.configure(text=f"⛅ {txt}"))
        except tk.TclError:
            pass

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
                if w > 1:
                    bar.place(x=0, y=0, relheight=1.0, width=max(1, int(w * pct)))
            if self._expanded:
                self._draw_sparkline(self._expanded)
        except Exception:
            pass

    def _tick_clock(self):
        try:
            now = datetime.datetime.now()
            self._clock_lbl.configure(text=now.strftime("%H:%M"))
            self._date_lbl.configure(text=now.strftime("%A, %B %d"))
            self.after(10_000, self._tick_clock)
        except tk.TclError:
            pass

    # ── Self Repair ───────────────────────────────────────────────────────────

    def log_error(self, msg: str):
        """Append a runtime error to the Self Repair output (thread-safe)."""
        import datetime as _dt
        ts = _dt.datetime.now().strftime("%H:%M:%S")
        self._sr_append(f"[{ts}] {msg}", "fail")

    def _sr_append(self, line: str, tag: str = "ok"):
        """Append a line to the self-repair text area (thread-safe)."""
        def _do():
            try:
                self._sr_text.configure(state="normal")
                self._sr_text.insert("end", line + "\n", tag)
                self._sr_text.see("end")
                self._sr_text.configure(state="disabled")
            except tk.TclError:
                pass
        self.after(0, _do)

    def _run_self_repair(self):
        """Clear output and run all diagnostic checks in a background thread."""
        try:
            self._sr_text.configure(state="normal")
            self._sr_text.delete("1.0", "end")
            self._sr_text.configure(state="disabled")
        except tk.TclError:
            return
        self._sr_btn.configure(state="disabled", text="…")

        def _can_import(n):
            try:
                __import__(n)
                return True
            except ImportError:
                return False

        def _diagnose():
            import importlib.util as _ilu
            import datetime as _dt
            from pathlib import Path as _P
            try:
                import requests as _req
                _req_ok = True
            except ImportError:
                _req = None
                _req_ok = False

            try:
                self._sr_append("── Diagnostics ──", "dim")

                # 1. API key
                try:
                    from config import get_api_key as _gak
                    key = _gak()
                    if key:
                        self._sr_append("✓ API key present", "ok")
                    else:
                        self._sr_append("✗ API key missing", "fail")
                except Exception as e:
                    self._sr_append(f"✗ API key check failed: {e}", "fail")

                # 2. Network
                if _req_ok:
                    try:
                        _req.head("https://api.anthropic.com", timeout=3)
                        self._sr_append("✓ Network reachable", "ok")
                    except Exception:
                        self._sr_append("✗ Network unreachable", "fail")
                else:
                    self._sr_append("⚠ Network: requests not installed", "warn")

                # 3. Tool load check
                tools_dir = _P(__file__).parent / "tools" / "custom"
                this_file = _P(__file__).name
                errors = []
                for f in sorted(tools_dir.glob("*.py")):
                    if f.name == this_file:
                        continue
                    try:
                        spec = _ilu.spec_from_file_location(f.stem, f)
                        mod  = _ilu.module_from_spec(spec)
                        spec.loader.exec_module(mod)
                    except Exception as e:
                        errors.append(f"{f.name}: {e}")
                if errors:
                    for err in errors:
                        self._sr_append(f"✗ Tool: {err}", "fail")
                else:
                    self._sr_append("✓ All tools load OK", "ok")

                # 4. Ollama
                try:
                    from ollama_core import OllamaCore as _OC
                    if _OC().ollama_available():
                        self._sr_append("✓ Ollama online", "ok")
                    else:
                        self._sr_append("⚠ Ollama offline", "warn")
                except Exception:
                    self._sr_append("⚠ Ollama unavailable", "warn")

                # 5. Required packages
                pkg_checks = {
                    "cv2": "opencv-python", "sounddevice": "sounddevice",
                    "edge_tts": "edge-tts", "psutil": "psutil", "PIL": "Pillow",
                }
                missing = [pkg for mod, pkg in pkg_checks.items()
                           if not _can_import(mod)]
                if missing:
                    self._sr_append(f"⚠ Missing: {', '.join(missing)}", "warn")
                else:
                    self._sr_append("✓ All packages present", "ok")

                # 6. Error log
                log_path = _P(__file__).parent / "hubert_errors.log"
                try:
                    if log_path.exists():
                        log_lines = log_path.read_text(
                            encoding="utf-8", errors="replace").splitlines()
                        cutoff = _dt.datetime.now() - _dt.timedelta(hours=24)
                        recent = []
                        for line in log_lines:
                            if line.startswith("[") and len(line) > 20:
                                try:
                                    ts = _dt.datetime.strptime(
                                        line[1:20], "%Y-%m-%d %H:%M:%S")
                                    if ts > cutoff:
                                        recent.append(line)
                                except ValueError:
                                    pass
                        count = len(recent)
                        if count == 0:
                            self._sr_append("✓ No errors in last 24h", "ok")
                        else:
                            self._sr_append(f"⚠ {count} error(s) in 24h", "warn")
                            for entry in recent[-3:]:
                                self._sr_append(f"  {entry[:80]}", "warn")
                    else:
                        self._sr_append("✓ No error log found", "ok")
                except Exception as e:
                    self._sr_append(f"⚠ Log read error: {e}", "warn")

                self._sr_append("── Done ──", "dim")
            except Exception as e:
                self._sr_append(f"✗ Unexpected error: {e}", "fail")
            finally:
                try:
                    self.after(0, lambda: self._sr_btn.configure(
                        state="normal", text="RUN"))
                except tk.TclError:
                    pass

        threading.Thread(target=_diagnose, daemon=True).start()

    def _run_full_repair(self):
        """RUN = diagnostics first; if errors found, auto-fix via Claude Code."""
        try:
            self._sr_text.configure(state="normal")
            self._sr_text.delete("1.0", "end")
            self._sr_text.configure(state="disabled")
        except tk.TclError:
            return
        self._sr_btn.configure(state="disabled", text="…")

        def _chain():
            # Phase 1 — diagnostics (reuse existing logic inline)
            import importlib.util as _ilu
            import datetime as _dt
            from pathlib import Path as _P
            try:
                import requests as _req
                _req_ok = True
            except ImportError:
                _req = None
                _req_ok = False

            errors_found = False
            try:
                self._sr_append("── Diagnostics ──", "dim")
                try:
                    from config import get_api_key as _gak
                    self._sr_append("✓ API key present" if _gak() else "✗ API key missing",
                                    "ok" if _gak() else "fail")
                except Exception as e:
                    self._sr_append(f"✗ API key: {e}", "fail"); errors_found = True

                if _req_ok:
                    try:
                        _req.head("https://api.anthropic.com", timeout=3)
                        self._sr_append("✓ Network reachable", "ok")
                    except Exception:
                        self._sr_append("✗ Network unreachable", "fail"); errors_found = True
                else:
                    self._sr_append("⚠ requests not installed", "warn")

                tools_dir = _P(__file__).parent / "tools" / "custom"
                tool_errors = []
                for f in sorted(tools_dir.glob("*.py")):
                    try:
                        spec = _ilu.spec_from_file_location(f.stem, f)
                        mod  = _ilu.module_from_spec(spec)
                        spec.loader.exec_module(mod)
                    except Exception as e:
                        tool_errors.append(f"{f.name}: {e}")
                if tool_errors:
                    for err in tool_errors:
                        self._sr_append(f"✗ Tool: {err}", "fail")
                    errors_found = True
                else:
                    self._sr_append("✓ All tools load OK", "ok")

                log_path = _P(__file__).parent / "hubert_errors.log"
                recent_errors = []
                if log_path.exists():
                    cutoff = _dt.datetime.now() - _dt.timedelta(hours=24)
                    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
                        if line.startswith("[") and len(line) > 20:
                            try:
                                if _dt.datetime.strptime(line[1:20], "%Y-%m-%d %H:%M:%S") > cutoff:
                                    recent_errors.append(line)
                            except ValueError:
                                pass
                    if recent_errors:
                        self._sr_append(f"⚠ {len(recent_errors)} error(s) in 24h", "warn")
                        for e in recent_errors[-3:]:
                            self._sr_append(f"  {e[:80]}", "warn")
                        errors_found = True
                    else:
                        self._sr_append("✓ No errors in last 24h", "ok")

                self._sr_append("── Done ──", "dim")

                # Phase 2 — auto-fix if issues found
                if errors_found:
                    self._sr_append("⚡ Issues found — running Auto-Fix…", "warn")
                    self.after(0, self._run_auto_fix)
                else:
                    self._sr_append("✓ No issues — no fix needed", "ok")
                    self.after(0, lambda: self._sr_btn.configure(state="normal", text="RUN"))

            except Exception as e:
                self._sr_append(f"✗ Unexpected: {e}", "fail")
                self.after(0, lambda: self._sr_btn.configure(state="normal", text="RUN"))

        threading.Thread(target=_chain, daemon=True).start()

    def _run_auto_fix(self):
        """Spawn Claude Code CLI to diagnose, fix, and optionally restart HUBERT."""
        import subprocess
        import sys
        import os
        import datetime as _dt
        from pathlib import Path as _P

        # Clear SR text
        try:
            self._sr_text.configure(state="normal")
            self._sr_text.delete("1.0", "end")
            self._sr_text.configure(state="disabled")
        except tk.TclError:
            return

        self._sr_btn.configure(state="disabled", text="…")

        def _auto_fix():
            try:
                jarvis_dir = str(_P(__file__).parent)
                log_path   = _P(__file__).parent / "hubert_errors.log"

                # Read recent errors from log
                error_snippet = ""
                if log_path.exists():
                    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
                    cutoff = _dt.datetime.now() - _dt.timedelta(hours=24)
                    recent = []
                    for line in lines:
                        if line.startswith("[") and len(line) > 20:
                            try:
                                ts = _dt.datetime.strptime(line[1:20], "%Y-%m-%d %H:%M:%S")
                                if ts > cutoff:
                                    recent.append(line)
                            except ValueError:
                                recent.append(line)
                    # Last 30 lines max
                    error_snippet = "\n".join(recent[-30:])

                if not error_snippet:
                    self._sr_append("⚠ No recent errors found in log — running general audit", "warn")
                    error_snippet = "(no recent errors — do a general health check on all Python files)"

                prompt = f"""You are performing an automated self-repair of the HUBERT AI assistant.
Project directory: {jarvis_dir}

Recent errors from hubert_errors.log:
{error_snippet}

Tasks:
1. Read the relevant source files to understand the error.
2. Fix the bug(s) causing the errors.
3. Verify the fix by checking related code.
4. Print a summary: what was broken, what you changed, and whether a restart is needed (write RESTART_REQUIRED on its own line if so).
Be concise. Make only necessary changes."""

                self._sr_append("── Claude Code Auto-Fix ──", "dim")
                self._sr_append("Spawning Claude Code…", "ok")

                # Find claude binary
                claude_bin = "claude"
                for candidate in [
                    "/usr/local/bin/claude",
                    "/opt/homebrew/bin/claude",
                    os.path.expanduser("~/.npm-global/bin/claude"),
                    os.path.expanduser("~/.local/bin/claude"),
                ]:
                    if os.path.isfile(candidate):
                        claude_bin = candidate
                        break

                proc = subprocess.Popen(
                    [claude_bin, "--print", prompt],
                    cwd=jarvis_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )

                restart_needed = False
                for line in proc.stdout:
                    line = line.rstrip()
                    if not line:
                        continue
                    if "RESTART_REQUIRED" in line:
                        restart_needed = True
                        self._sr_append("⚡ Restart flagged — will relaunch after fix", "warn")
                    elif line.startswith("✓") or "fixed" in line.lower() or "done" in line.lower():
                        self._sr_append(line, "ok")
                    elif line.startswith("✗") or "error" in line.lower() or "fail" in line.lower():
                        self._sr_append(line, "fail")
                    else:
                        self._sr_append(line, "dim")

                proc.wait()
                rc = proc.returncode

                if rc != 0:
                    self._sr_append(f"✗ Claude Code exited with code {rc}", "fail")
                else:
                    self._sr_append("✓ Claude Code finished", "ok")

                self._sr_append("── Done ──", "dim")

                # Restart if flagged
                if restart_needed and rc == 0:
                    self._sr_append("Restarting HUBERT in 3s…", "warn")
                    import time as _t
                    _t.sleep(3)
                    python = sys.executable
                    main_path = str(_P(__file__))
                    os.execv(python, [python, main_path])

            except FileNotFoundError:
                self._sr_append("✗ claude CLI not found — install Claude Code first", "fail")
                self._sr_append("  brew install claude  or  npm i -g @anthropic-ai/claude-code", "warn")
            except Exception as e:
                self._sr_append(f"✗ Auto-fix error: {e}", "fail")
            finally:
                try:
                    self.after(0, lambda: self._sr_btn.configure(state="normal", text="RUN"))
                except tk.TclError:
                    pass

        threading.Thread(target=_auto_fix, daemon=True).start()

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
        # Fill under curve first (lower z-order), then line on top
        fill_pts = [0, h] + pts + [w, h]
        spark.create_polygon(*fill_pts, fill=self.HD, outline="")
        if len(pts) >= 4:
            spark.create_line(*pts, fill=self.HC, width=1, smooth=True)

    # ── Camera ────────────────────────────────────────────────────────────────

    def _toggle_camera(self):
        """Turn the camera feed on or off."""
        if self._cam_running:
            self._stop_camera()
        else:
            self._cam_running = True
            self._cam_toggle_btn.configure(text="ON", fg=self.HC)
            self._start_camera()

    def _stop_camera(self):
        """Signal the capture loop to exit and clear the feed."""
        self._cam_running = False
        self._cam_available = False
        self._cam_last_frame = None
        try:
            self._cam_toggle_btn.configure(text="OFF", fg="#ff4444")
        except (tk.TclError, AttributeError):
            pass
        self._set_cam_live(False)
        self._animate_no_signal()

    def _start_camera(self):
        """Request macOS camera permission (main thread), then start capture thread."""
        self._cam_running = True
        try:
            self._cam_toggle_btn.configure(text="ON", fg=self.HC)
        except (tk.TclError, AttributeError):
            pass
        try:
            import cv2 as _cv2  # noqa: F401
        except ImportError:
            self._cam_available = False
            self._cam_running = False
            self._animate_no_signal()
            return

        # On Mac, request camera permission via AVFoundation (must be main thread).
        if _IS_MAC:
            try:
                import AVFoundation as _AVF
                import objc as _objc

                auth = _AVF.AVCaptureDevice.authorizationStatusForMediaType_(
                    _AVF.AVMediaTypeVideo
                )
                # 0 = not determined, 3 = authorized
                if auth == 0:
                    # Request permission; callback fires when user responds.
                    def _on_auth(granted):
                        if granted:
                            threading.Thread(target=self._capture_loop, daemon=True).start()
                        else:
                            self.after(0, self._animate_no_signal)
                    _AVF.AVCaptureDevice.requestAccessForMediaType_completionHandler_(
                        _AVF.AVMediaTypeVideo, _on_auth
                    )
                    return
                elif auth != 3:
                    # Denied or restricted
                    self._animate_no_signal()
                    return
                # auth == 3 → already authorized, fall through
            except Exception:
                pass  # fallback: let OpenCV try directly

        threading.Thread(target=self._capture_loop, daemon=True).start()

    def _capture_loop(self):
        """Background thread: open camera and push frames to the canvas."""
        import cv2 as _cv2
        import os as _os
        # Tell OpenCV to skip its own auth dialog (we already handled it above)
        _os.environ.setdefault("OPENCV_AVFOUNDATION_SKIP_AUTH", "1")
        cap = None
        try:
            cap = _cv2.VideoCapture(0)
            if not cap.isOpened():
                self._cam_available = False
                self.after(0, self._animate_no_signal)
                return
            self._cam_available = True
            self.after(0, self._set_cam_live, True)
            import time as _time
            while self._cam_running:
                ret, frame = cap.read()
                if not ret:
                    break
                try:
                    from PIL import Image, ImageTk
                    rgb  = _cv2.cvtColor(frame, _cv2.COLOR_BGR2RGB)
                    pil  = Image.fromarray(rgb)
                    self._cam_last_frame = pil.copy()
                    # HUD thumbnail
                    thumb  = pil.resize((146, 110), Image.LANCZOS)
                    img_tk = ImageTk.PhotoImage(thumb)
                    self.after(0, self._show_cam_frame, img_tk)
                    # Push to any open pop-out windows
                    for sink in list(self._cam_sinks):
                        try:
                            sink(pil)
                        except Exception:
                            pass
                except Exception:
                    pass
                _time.sleep(0.033)
        except Exception:
            pass
        finally:
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass
            self._cam_available = False
            self._cam_last_frame = None
            self.after(0, self._set_cam_live, False)
            self.after(0, self._animate_no_signal)

    def _set_cam_live(self, live: bool):
        """Update the status dot and snapshot button (main thread)."""
        try:
            color = self.HC if live else "#ff4444"
            self._cam_status_dot.delete("all")
            self._cam_status_dot.create_oval(1, 1, 7, 7, fill=color, outline="")
            self._cam_snap_btn.configure(
                state="normal" if live else "disabled",
                bg=self.HC if live else "#004840",
            )
        except (tk.TclError, AttributeError):
            pass

    def _show_cam_frame(self, img_tk):
        """Display a camera frame on the canvas (main thread only)."""
        try:
            self._cam_img_ref = img_tk
            self._cam_canvas.delete("all")
            self._cam_canvas.create_image(0, 0, anchor="nw", image=img_tk)
        except tk.TclError:
            pass

    def _animate_no_signal(self):
        """Animate NO SIGNAL placeholder on 250ms loop (slow — camera is off)."""
        if self._cam_available:
            return   # camera came back online, stop this loop
        try:
            c = self._cam_canvas
            c.delete("all")
            c.create_rectangle(0, 0, 146, 110, fill="#000000", outline="")
            for i in range(8):
                y = (self._t * 3 + i * 14) % 110
                alpha = int(10 + 5 * math.sin(i))
                c.create_line(0, y, 146, y, fill=f"#0{alpha:x}1a18", width=1)
            c.create_text(73, 48, text="NO SIGNAL",
                          font=(_MONO_FONT, 9, "bold"), fill="#004840")
            c.create_text(73, 64, text="camera offline",
                          font=(_MONO_FONT, 7), fill="#003030")
            if self._t % 6 < 3:
                c.create_oval(136, 4, 144, 12, fill="#330000", outline="")
            self._t += 1
            self.after(250, self._animate_no_signal)
        except tk.TclError:
            pass

    def _cam_snapshot(self):
        """Capture current frame and send it to HUBERT via on_send callback."""
        if not self._cam_available or self._cam_last_frame is None:
            return
        try:
            import tempfile, os
            from PIL import Image
            # Save to temp file
            tmp = tempfile.NamedTemporaryFile(
                suffix=".jpg", delete=False,
                prefix="hubert_snap_",
                dir=Path.home() / "Jarvis"
            )
            self._cam_last_frame.save(tmp.name, "JPEG", quality=90)
            tmp.close()
            # Flash the button
            self._cam_snap_btn.configure(bg="#ffffff", fg="#000000", text="✓  CAPTURED")
            self.after(600, lambda: self._cam_snap_btn.configure(
                bg=self.HC, fg=self.HBG, text="⬤  SNAPSHOT → HUBERT"))
            # Deliver to app
            if self._cam_on_send:
                self._cam_on_send(tmp.name)
        except Exception as e:
            print(f"[camera] snapshot error: {e}")

    def _pop_cam(self):
        """Open (or focus) the floating camera window."""
        # If already open, just bring it to front
        if self._cam_window is not None:
            try:
                self._cam_window.lift()
                self._cam_window.focus_force()
                return
            except tk.TclError:
                self._cam_window = None

        win = CameraWindow(
            self,
            on_close=self._on_cam_window_close,
            on_snapshot=self._cam_snapshot_from_window,
        )
        self._cam_window = win
        # Register as a frame sink
        self._cam_sinks.append(win.push_frame)

    def _on_cam_window_close(self, win):
        """Called when the pop-out window is closed."""
        try:
            self._cam_sinks.remove(win.push_frame)
        except ValueError:
            pass
        self._cam_window = None

    def _cam_snapshot_from_window(self):
        """Snapshot triggered from the pop-out window — reuse existing logic."""
        self._cam_snapshot()


# ── Camera Pop-out Window ──────────────────────────────────────────────────────

class CameraWindow(tk.Toplevel):
    """Floating, resizable camera feed window."""

    MIN_W, MIN_H = 320, 260

    def __init__(self, hud: "HUDPanel", on_close, on_snapshot):
        super().__init__(hud)
        self._hud        = hud
        self._on_close   = on_close
        self._on_snap    = on_snapshot
        self._img_ref    = None

        self.title("HUBERT — Camera")
        self.configure(bg="#000000")
        self.minsize(self.MIN_W, self.MIN_H)
        self.geometry("640x520")
        self.resizable(True, True)
        self.protocol("WM_DELETE_WINDOW", self._close)

        self._build()

    def _build(self):
        # Title bar strip
        hdr = tk.Frame(self, bg="#030c0a", height=30)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="  ◉  CAMERA FEED",
                 font=(_MONO_FONT, 9, "bold"),
                 fg="#00d4aa", bg="#030c0a").pack(side="left", pady=6)
        tk.Button(
            hdr, text="✕",
            font=(_MONO_FONT, 10, "bold"),
            fg="#ff4444", bg="#030c0a",
            activeforeground="#ffffff", activebackground="#330000",
            relief="flat", bd=0, padx=10,
            command=self._close,
        ).pack(side="right")

        # Canvas — expands to fill the window
        self._canvas = tk.Canvas(self, bg="#000000", highlightthickness=0)
        self._canvas.pack(fill="both", expand=True)
        self._canvas.bind("<Configure>", self._on_resize)

        # Bottom controls
        bar = tk.Frame(self, bg="#030c0a", height=36)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        self._snap_btn = tk.Button(
            bar, text="⬤  SNAPSHOT → HUBERT",
            font=(_MONO_FONT, 9, "bold"),
            fg="#000000", bg="#00d4aa",
            activebackground="#00a080",
            relief="flat", bd=0, padx=12, pady=4,
            command=self._snap,
        )
        self._snap_btn.pack(side="left", padx=10, pady=4)
        self._status_lbl = tk.Label(
            bar, text="● LIVE",
            font=(_MONO_FONT, 8), fg="#00d4aa", bg="#030c0a",
        )
        self._status_lbl.pack(side="right", padx=10)

        # Show NO SIGNAL until first frame arrives
        self._cw = 640
        self._ch = 480
        self._draw_no_signal()

    def _on_resize(self, event):
        self._cw = event.width
        self._ch = event.height
        # Rescale last frame to new size immediately
        if self._img_ref is not None:
            self._canvas.coords(self._canvas.find_all()[0] if self._canvas.find_all() else "all", 0, 0)

    def push_frame(self, pil_frame):
        """Receive a PIL Image from the capture thread (called from bg thread)."""
        try:
            from PIL import ImageTk
            w = max(self._cw, self.MIN_W)
            h = max(self._ch - 66, self.MIN_H - 66)  # subtract hdr+bar height
            resized = pil_frame.resize((w, h), 0)     # NEAREST — fast enough at 30fps
            img_tk  = ImageTk.PhotoImage(resized)
            self.after(0, self._display, img_tk)
        except Exception:
            pass

    def _display(self, img_tk):
        try:
            self._img_ref = img_tk
            self._canvas.delete("all")
            self._canvas.create_image(0, 0, anchor="nw", image=img_tk)
        except tk.TclError:
            pass

    def _draw_no_signal(self):
        try:
            self._canvas.delete("all")
            self._canvas.create_rectangle(
                0, 0, self._cw, self._ch, fill="#000000", outline="")
            self._canvas.create_text(
                self._cw // 2, self._ch // 2,
                text="NO SIGNAL", font=(_MONO_FONT, 14, "bold"), fill="#004840")
            self._canvas.create_text(
                self._cw // 2, self._ch // 2 + 26,
                text="camera offline", font=(_MONO_FONT, 10), fill="#003030")
        except tk.TclError:
            pass

    def _snap(self):
        self._snap_btn.configure(bg="#ffffff", fg="#000000", text="✓  CAPTURED")
        self.after(600, lambda: self._snap_btn.configure(
            bg="#00d4aa", fg="#000000", text="⬤  SNAPSHOT → HUBERT"))
        self._on_snap()

    def _close(self):
        self._on_close(self)
        self.destroy()


# ── Swarm Panel ───────────────────────────────────────────────────────────────

class SwarmPanel(ctk.CTkFrame):
    """Permanent left-side agent swarm visualization: node graph + activity feed."""

    HUB_R  = 30
    AGT_R  = 22
    TOOL_R = 16
    W      = 300

    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color=BG_PANEL, corner_radius=0,
                         border_width=0, width=self.W, **kwargs)
        self.pack_propagate(False)
        self._nodes: dict  = {}
        self._edges: list  = []   # [(fid, tid)]
        self._pulses: list = []   # [{fid, tid, t, max_t, color}]
        self._t      = 0
        self._visible = True
        # Viewport state for pan/zoom
        self._pan_x  = 0.0
        self._pan_y  = 0.0
        self._zoom   = 1.0
        self._drag_start    = None   # (x, y) screen coords at drag start
        self._pan_start     = None   # (pan_x, pan_y) at drag start
        self._hovered_node  = None   # nid under cursor
        self._inspected_node = None  # nid of pinned inspector
        self._build()
        self._add_hub()
        self._animate()
        self._start_daily_token_refresh()

    def _build(self):
        # Header bar
        hdr = tk.Frame(self, bg=BG_CARD, height=30)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="  ◈  SWARM MONITOR",
                 font=(_MONO_FONT, 8, "bold"), fg=ACCENT, bg=BG_CARD).pack(
            side="left", pady=6)
        self._token_label = tk.Label(hdr, text="--%",
                                     font=(_MONO_FONT, 7), fg="#00a080", bg=BG_CARD)
        self._token_label.pack(side="left", padx=4)
        # Zoom controls
        for sym, cmd in [("−", lambda: self._zoom_step(-0.2)),
                         ("⊙", self._zoom_reset),
                         ("+", lambda: self._zoom_step(0.2))]:
            tk.Button(hdr, text=sym, font=(_MONO_FONT, 8),
                      fg=TEXT_DIM, bg=BG_CARD, relief="flat", bd=0,
                      activebackground=BG_CARD, activeforeground=ACCENT,
                      command=cmd).pack(side="right", padx=2)

        # Right border separator
        tk.Frame(self, bg=DIM, width=1).pack(side="right", fill="y")

        # Tool-group badge row — shows which groups are active for the current task
        self._group_bar = tk.Frame(self, bg=BG_PANEL)
        self._group_bar.pack(fill="x", padx=4, pady=(2, 0))
        self._group_labels: dict[str, tk.Label] = {}
        self._model_label = tk.Label(
            self._group_bar, text="", font=(_MONO_FONT, 7),
            fg=ACCENT2, bg=BG_PANEL, anchor="w"
        )
        self._model_label.pack(side="left", padx=(0, 4))
        ALL_GROUPS = [
            "computer", "browser", "swarm", "github", "memory",
            "web", "productivity", "creative", "supabase", "meta", "eonet",
        ]
        for g in ALL_GROUPS:
            lbl = tk.Label(
                self._group_bar, text=g[:3], font=(_MONO_FONT, 6),
                fg="#1a2e50", bg=BG_PANEL, padx=2, pady=1,
                relief="flat", cursor="arrow",
            )
            lbl.pack(side="left", padx=1)
            self._group_labels[g] = lbl

        # Node graph canvas
        self._canvas = tk.Canvas(self, bg=BG, highlightthickness=0, height=300)
        self._canvas.pack(fill="x")
        self._canvas.bind("<Button-1>",       self._on_canvas_click)
        self._canvas.bind("<B1-Motion>",       self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_drag_end)
        self._canvas.bind("<Motion>",          self._on_hover)
        self._canvas.bind("<MouseWheel>",      self._on_scroll)
        self._canvas.bind("<Button-4>",        self._on_scroll)
        self._canvas.bind("<Button-5>",        self._on_scroll)

        # Divider
        tk.Frame(self, bg=DIM, height=1).pack(fill="x")

        # Activity feed header
        lbl_row = tk.Frame(self, bg=BG_PANEL)
        lbl_row.pack(fill="x", padx=6, pady=(4, 1))
        tk.Label(lbl_row, text="ACTIVITY FEED",
                 font=(_MONO_FONT, 7, "bold"), fg=ACCENT2, bg=BG_PANEL).pack(side="left")
        tk.Button(lbl_row, text="⟳", font=(_MONO_FONT, 7),
                  fg=TEXT_DIM, bg=BG_PANEL, relief="flat", bd=0,
                  activebackground=BG_PANEL, activeforeground=ACCENT,
                  command=self._clear_log).pack(side="right", padx=2)

        # Activity log
        self._log = tk.Text(self, bg=BG, fg=TEXT_DIM,
                            font=(_MONO_FONT, 8), state="disabled",
                            relief="flat", borderwidth=0,
                            padx=6, pady=4, wrap="word")
        self._log.pack(fill="both", expand=True, padx=2, pady=(0, 2))

        # Text tags
        self._log.tag_configure("tool",   foreground=TEXT_TOOL)
        self._log.tag_configure("agent",  foreground=PURPLE)
        self._log.tag_configure("comm",   foreground=ACCENT)
        self._log.tag_configure("result", foreground="#2e4468")
        self._log.tag_configure("ts",     foreground="#1a2e50")
        self._log.tag_configure("err",    foreground=TEXT_ERR)
        self._log.tag_configure("sys",    foreground=ACCENT2)

    def _add_hub(self):
        cx, cy = self.W // 2, 148
        self._nodes["HUBERT"] = {
            "x": cx, "y": cy, "kind": "hub",
            "label": "HUBERT", "last_active": 0,
        }

    # ── Viewport helpers ──────────────────────────────────────────────────────

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

    def _animate(self):
        self._t += 1
        self._render()
        self.after(35, self._animate)

    def _render(self):
        c = self._canvas
        c.delete("all")
        w = c.winfo_width() or self.W
        h = c.winfo_height() or 300

        # Background grid dots (screen-space, not affected by pan/zoom)
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
            x, y   = self._g2s(nd["x"], nd["y"])
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

            # Highlight hovered/inspected node
            if nid == self._hovered_node or nid == self._inspected_node:
                c.create_oval(x-r-4, y-r-4, x+r+4, y+r+4, outline=ACCENT, width=1)

            c.create_oval(x-r, y-r, x+r, y+r, fill=fill, outline=base_col, width=2)
            c.create_text(x, y-3, text=icon,
                          font=(_MONO_FONT, fsz, "bold"), fill=base_col)
            short = label[:13] if len(label) <= 13 else label[:12] + "…"
            c.create_text(x, y + r + int(9 * z), text=short,
                          font=(_MONO_FONT, max(5, int(6 * z))), fill=TEXT_DIM,
                          width=int(88 * z), justify="center")

        # Hover tooltip (only when not pinned)
        if self._hovered_node and self._hovered_node != self._inspected_node:
            self._draw_tooltip(self._hovered_node)

        # Pinned inspector
        if self._inspected_node:
            self._draw_inspector(self._inspected_node)

    def _draw_tooltip(self, nid: str):
        nd = self._nodes.get(nid)
        if not nd:
            return
        c   = self._canvas
        sx, sy = self._g2s(nd["x"], nd["y"])
        r   = {"hub": self.HUB_R, "agent": self.AGT_R,
               "tool": self.TOOL_R}.get(nd["kind"], self.AGT_R) * self._zoom
        tx, ty = sx + r + 6, sy - 30
        lines  = [
            nd["label"][:18],
            f"status: {'ACTIVE' if self._t - nd.get('last_active', 0) < 80 else 'idle'}",
            f"kind:   {nd['kind']}",
        ]
        box_w, box_h = 130, len(lines) * 14 + 10
        cw = c.winfo_width() or self.W
        if tx + box_w > cw - 4:
            tx = sx - r - box_w - 6
        c.create_rectangle(tx, ty, tx + box_w, ty + box_h,
                           fill="#0a0f1e", outline=ACCENT, width=1)
        for i, line in enumerate(lines):
            color = ACCENT if i == 0 else TEXT_DIM
            c.create_text(tx + 6, ty + 6 + i * 14, text=line,
                          font=(_MONO_FONT, 7), fill=color, anchor="nw")

    def _draw_inspector(self, nid: str):
        nd = self._nodes.get(nid)
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
                      font=(_MONO_FONT, 8, "bold"), fill=ACCENT, anchor="nw")
        c.create_text(bx + 6, by + 20, text=f"kind:    {nd['kind']}",
                      font=(_MONO_FONT, 7), fill=TEXT_DIM, anchor="nw")
        col = GREEN if status == "ACTIVE" else TEXT_DIM
        c.create_text(bx + 6, by + 32, text=f"status:  {status}",
                      font=(_MONO_FONT, 7), fill=col, anchor="nw")
        c.create_text(bx + 6, by + 44, text=f"age:     {age} ticks",
                      font=(_MONO_FONT, 7), fill=TEXT_DIM, anchor="nw")
        c.create_text(bx + 6, by + 56,
                      text="[click node again or outside to close]",
                      font=(_MONO_FONT, 6), fill=TEXT_DIM, anchor="nw")

    def _place_node(self, kind: str):
        hub = self._nodes["HUBERT"]
        cx, cy = hub["x"], hub["y"]
        w = self._canvas.winfo_width() or self.W
        count = sum(1 for nd in self._nodes.values() if nd["kind"] == kind)
        if kind == "tool":
            radius, step = 88, 42
        else:
            radius, step = 148, 65
        angle = math.radians(count * step - (0 if kind == "tool" else 90))
        x = max(20, min(w - 20, cx + radius * math.cos(angle)))
        y = max(20, min(280,    cy + radius * math.sin(angle)))
        return x, y

    # ── Pan / Zoom / Interaction ──────────────────────────────────────────────

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
                self._inspected_node = None
            else:
                self._inspected_node = hit
        else:
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
        if event.num == 5 or event.delta < 0:
            direction = -1
        else:
            direction = 1
        old_zoom   = self._zoom
        self._zoom = max(0.5, min(3.0, self._zoom + direction * 0.15))
        scale      = self._zoom / old_zoom
        self._pan_x = event.x - scale * (event.x - self._pan_x)
        self._pan_y = event.y - scale * (event.y - self._pan_y)

    def _add_edge(self, fid, tid):
        if not any(f == fid and t == tid for f, t in self._edges):
            self._edges.append((fid, tid))

    def _fire_pulse(self, fid, tid, color):
        self._pulses.append({"fid": fid, "tid": tid, "t": 0, "max_t": 35, "color": color})

    def _log_event(self, tag, text):
        self._log.configure(state="normal")
        ts_str = time.strftime("%H:%M:%S")
        self._log.insert("end", f"{ts_str} ", "ts")
        self._log.insert("end", text + "\n", tag)
        lines = int(self._log.index("end-1c").split(".")[0])
        if lines > 60:
            self._log.delete("1.0", "3.0")
        self._log.configure(state="disabled")
        self._log.see("end")

    def _clear_log(self):
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")

    # ── Public API ────────────────────────────────────────────────────────────

    _SESSION_BUDGET = 80_000  # matches SESSION_TOKEN_BUDGET in jarvis_core

    def update_token_pct(self, session_tokens_used: int):
        """Update the token indicator with both session and daily totals."""
        try:
            from jarvis_core import _token_stats
            daily = _token_stats.get("daily", session_tokens_used)
        except Exception:
            daily = session_tokens_used
        pct = min(session_tokens_used / self._SESSION_BUDGET * 100, 100)
        if pct < 50:
            color = "#00a080"
        elif pct < 70:
            color = "#ffaa00"
        else:
            color = "#ff4444"

        def _fmt(n):
            return f"{n/1000:.1f}k" if n >= 1000 else str(n)

        label = f"session {_fmt(session_tokens_used)}  today {_fmt(daily)}"
        try:
            self._token_label.configure(text=label, fg=color)
        except tk.TclError:
            pass

    def _start_daily_token_refresh(self):
        """Refresh daily token display at midnight to reset the counter."""
        import datetime as _dt
        def _tick():
            try:
                from jarvis_core import _token_stats, _load_daily_tokens
                today = _dt.date.today().isoformat()
                # If it's a new day, reload (jarvis_core already handles reset)
                refreshed = _load_daily_tokens()
                _token_stats["daily"] = refreshed
                # Update label
                session = _token_stats.get("input", 0) + _token_stats.get("output", 0)
                self.update_token_pct(session)
            except Exception:
                pass
            # Schedule next check at next midnight
            now = _dt.datetime.now()
            tomorrow = _dt.datetime.combine(now.date() + _dt.timedelta(days=1),
                                            _dt.time(0, 0, 1))
            ms = int((tomorrow - now).total_seconds() * 1000)
            try:
                self.after(ms, _tick)
            except tk.TclError:
                pass
        # First call in 60s (let boot finish), then midnight-aligned
        try:
            self.after(60_000, _tick)
        except tk.TclError:
            pass

    def on_tool_call(self, tool_name: str, source: str = "HUBERT"):
        if source not in self._nodes:
            return
        nid = f"tool_{tool_name}"
        if nid not in self._nodes:
            x, y = self._place_node("tool")
            self._nodes[nid] = {
                "x": x, "y": y, "kind": "tool",
                "label": tool_name.replace("_", " "),
                "last_active": self._t,
            }
            self._add_edge(source, nid)
        else:
            self._nodes[nid]["last_active"] = self._t
        self._fire_pulse(source, nid, GREEN)
        self._log_event("tool", f"⚙  {tool_name}")

    def add_cc_node(self):
        """Add a Claude Code CLI node connected to HUBERT (call when entering CC mode)."""
        if "CC" in self._nodes:
            return
        hub = self._nodes["HUBERT"]
        x = hub["x"]
        y = hub["y"] + 70
        self._nodes["CC"] = {
            "x": x, "y": y, "kind": "agent",
            "label": "CC", "last_active": self._t,
        }
        self._add_edge("HUBERT", "CC")

    def remove_cc_node(self):
        """Remove the CC node and all its edges (call when leaving CC mode)."""
        self._nodes.pop("CC", None)
        self._edges = [(f, t) for f, t in self._edges if f != "CC" and t != "CC"]
        self._pulses = [p for p in self._pulses if p["fid"] != "CC" and p["tid"] != "CC"]

    def on_cc_tool_call(self, tool_name: str):
        """Route a CC-mode tool call through the CC node instead of HUBERT."""
        self.on_tool_call(tool_name, source="CC")

    def on_tool_result(self, tool_name: str, result: str):
        nid = f"tool_{tool_name}"
        if nid in self._nodes:
            self._nodes[nid]["last_active"] = self._t
            self._fire_pulse(nid, "HUBERT", TEXT_TOOL)
        r = result[:55].replace("\n", " ")
        self._log_event("result", f"   → {r}")

    def on_agent_spawn(self, agent_name: str):
        nid = f"agent_{agent_name}"
        if nid not in self._nodes:
            x, y = self._place_node("agent")
            self._nodes[nid] = {
                "x": x, "y": y, "kind": "agent",
                "label": agent_name,
                "last_active": self._t,
            }
            self._add_edge("HUBERT", nid)
        else:
            self._nodes[nid]["last_active"] = self._t
        self._fire_pulse("HUBERT", nid, ACCENT2)
        self._log_event("agent", f"▶  AGENT  {agent_name}")

    def on_comm(self, from_name: str, to_name: str, msg: str = ""):
        fid = "HUBERT" if from_name == "HUBERT" else f"agent_{from_name}"
        tid = "HUBERT" if to_name   == "HUBERT" else f"agent_{to_name}"
        self._add_edge(fid, tid)
        self._fire_pulse(fid, tid, ACCENT)
        short = msg[:50].replace("\n", " ")
        self._log_event("comm", f"↔  {from_name} → {to_name}  {short}")

    def set_active_tool_groups(self, groups: list):
        """Highlight active tool groups in the badge bar and dim inactive ones."""
        active = set(groups or [])
        for name, lbl in self._group_labels.items():
            if name in active:
                lbl.configure(fg=ACCENT, bg=BG_CARD)
            else:
                lbl.configure(fg="#1a2e50", bg=BG_PANEL)
        self._log_event("sys", f"tools: core+{','.join(sorted(active)) or 'none'}")

    def dispatch(self, cmd: dict):
        """Handle a live UI command from ui_bridge."""
        c = cmd.get("cmd", "")
        if c == "add_agent":
            self.on_agent_spawn(cmd["name"])
        elif c == "add_comm":
            self.on_comm(cmd.get("from", "HUBERT"),
                         cmd.get("to",   "HUBERT"),
                         cmd.get("msg",  ""))
        elif c == "log":
            self._log_event(cmd.get("type", "sys"), cmd.get("text", ""))
        elif c == "clear_tools":
            self.clear_tools()
        elif c == "add_tool":
            self.on_tool_call(cmd["name"])
        elif c == "tool_groups_active":
            groups = cmd.get("groups", [])
            model  = cmd.get("model", "")
            count  = cmd.get("tool_count", 0)
            self.set_active_tool_groups(groups)
            short_model = "haiku" if "haiku" in model else "sonnet"
            self._model_label.configure(
                text=f"[{short_model}·{count}t]",
                fg="#00c896" if short_model == "haiku" else ACCENT,
            )

    def clear_tools(self):
        to_rm = [nid for nid, nd in self._nodes.items() if nd["kind"] == "tool"]
        for nid in to_rm:
            del self._nodes[nid]
        self._edges = [(f, t) for f, t in self._edges
                       if f not in to_rm and t not in to_rm]

    def toggle_visibility(self):
        try:
            paned = self.master
            if self._visible:
                paned.remove(self)
                self._visible = False
            else:
                paned.add(self, minsize=180, width=300, stretch="never")
                self._visible = True
        except Exception:
            pass


# ── Menu Drawer ───────────────────────────────────────────────────────────────

class MenuDrawer(ctk.CTkFrame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color=BG_CARD,
                         corner_radius=0, width=268, height=600, **kwargs)
        self._visible   = False
        self._subagents = []
        self._build()

    def _build(self):
        hdr = ctk.CTkFrame(self, fg_color=BG_PANEL, corner_radius=0, height=50)
        hdr.pack(fill="x", side="top")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="  ≡  HUBERT MENU",
                     font=(_MONO_FONT, 11, "bold"),
                     text_color=ACCENT).pack(side="left", padx=8, pady=12)
        ctk.CTkButton(hdr, text="✕", width=32, height=32,
                      fg_color="transparent", hover_color=DIM,
                      text_color=TEXT_DIM, font=(_MONO_FONT, 12),
                      command=self.hide).pack(side="right", padx=6, pady=8)
        tk.Frame(self, bg=DIM, height=1).pack(fill="x")

        sf = ctk.CTkScrollableFrame(self, fg_color=BG_CARD,
                                     scrollbar_button_color=DIM2,
                                     corner_radius=0)
        sf.pack(fill="both", expand=True)

        self._section(sf, "SUBAGENTS")
        self.sub_list = tk.Text(sf, bg=BG, fg=TEXT_TOOL,
                                font=(_MONO_FONT, 9), height=5,
                                state="disabled", relief="flat",
                                borderwidth=0, padx=8, pady=4)
        self.sub_list.pack(fill="x", padx=6, pady=(0,6))

        self._section(sf, "RECENT OPERATIONS")
        self.ops_list = tk.Text(sf, bg=BG, fg=TEXT_DIM,
                                font=(_MONO_FONT, 9), height=10,
                                state="disabled", relief="flat",
                                borderwidth=0, padx=8, pady=4)
        self.ops_list.pack(fill="x", padx=6, pady=(0,6))

        self._section(sf, "MEMORY")
        ctk.CTkButton(sf, text="🧠  Open Memory Map", height=30,
                      fg_color=DIM, hover_color=DIM2, text_color="#a78bfa",
                      font=F_SMALL, corner_radius=4, anchor="w",
                      command=self._open_memory_map).pack(fill="x", padx=8, pady=2)

        self._section(sf, "SKILLS")
        ctk.CTkButton(sf, text="◈  View All Skills", height=30,
                      fg_color=DIM, hover_color=DIM2, text_color=ACCENT,
                      font=F_SMALL, corner_radius=4, anchor="w",
                      command=self._open_skills).pack(fill="x", padx=8, pady=2)

        self._section(sf, "SETTINGS")
        ctk.CTkButton(sf, text="⚙  Change API Key", height=30,
                      fg_color=DIM, hover_color=DIM2, text_color=TEXT,
                      font=F_SMALL, corner_radius=4, anchor="w",
                      command=self._api_key_dialog).pack(fill="x", padx=8, pady=2)

        self._autostart_var = tk.BooleanVar(value=is_autostart_enabled())
        as_row = ctk.CTkFrame(sf, fg_color="transparent")
        as_row.pack(fill="x", padx=8, pady=(6,2))
        ctk.CTkLabel(as_row, text="⏻  Auto-start on login",
                     font=F_SMALL, text_color=TEXT).pack(side="left")
        ctk.CTkSwitch(as_row, text="", width=44,
                      variable=self._autostart_var,
                      onvalue=True, offvalue=False,
                      progress_color=ACCENT2,
                      command=self._toggle_autostart).pack(side="right")

    def _section(self, parent, title):
        ctk.CTkLabel(parent, text=f"  {title}",
                     font=(_MONO_FONT, 8, "bold"),
                     text_color=ACCENT2).pack(anchor="w", pady=(10,2), padx=4)

    def _open_memory_map(self):
        self.hide()
        import subprocess
        # Ensure Obsidian is open on HUBERT_Vault with the canvas
        subprocess.Popen(
            ["open", "obsidian://open?vault=HUBERT_Vault&file=HUBERT_Memory_Map.canvas"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

    def _open_skills(self):
        self.hide()
        SkillsDialog(self.winfo_toplevel())

    def _api_key_dialog(self):
        self.hide()
        if hasattr(self, "_on_api_key"): self._on_api_key()

    def _toggle_autostart(self):
        enabled = self._autostart_var.get()
        try:
            set_autostart(enabled)
        except Exception:
            self._autostart_var.set(not enabled)

    def log_op(self, tool_name):
        self.ops_list.configure(state="normal")
        self.ops_list.insert("end", f"  ⚙  {ts()}  {tool_name}\n")
        self.ops_list.configure(state="disabled")
        self.ops_list.see("end")

    def add_subagent(self, name):
        self._subagents.append(name)
        self.sub_list.configure(state="normal")
        self.sub_list.insert("end", f"  ▶  {name}\n")
        self.sub_list.configure(state="disabled")

    def toggle(self):
        self.hide() if self._visible else self.show()

    def show(self):
        self._visible = True
        self.place(x=0, y=0, relheight=1.0)
        self.lift()
        self.focus_set()

    def hide(self):
        self._visible = False
        self.place_forget()


# ── Weather Card ──────────────────────────────────────────────────────────────

class WeatherCard(ctk.CTkFrame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color=BG_CARD, corner_radius=12,
                         border_width=1, border_color=DIM2,
                         width=226, **kwargs)
        self._build()
        self._start_clock()
        threading.Thread(target=self._fetch_weather, daemon=True).start()

    def _build(self):
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=10, pady=(8,0))
        ctk.CTkLabel(hdr, text="◈ HUBERT STATUS",
                     font=(_MONO_FONT, 8, "bold"),
                     text_color=ACCENT).pack(side="left")
        ctk.CTkButton(hdr, text="✕", width=20, height=20,
                      fg_color="transparent", hover_color=DIM,
                      text_color=TEXT_DIM, font=(_MONO_FONT, 10),
                      command=self.destroy).pack(side="right")
        self.time_lbl = ctk.CTkLabel(self, text="",
                                      font=(_MONO_FONT, 22, "bold"),
                                      text_color=ACCENT)
        self.time_lbl.pack(pady=(4,0))
        self.date_lbl = ctk.CTkLabel(self, text="",
                                      font=(_MONO_FONT, 9),
                                      text_color=TEXT_DIM)
        self.date_lbl.pack()
        tk.Frame(self, bg=DIM, height=1).pack(fill="x", padx=10, pady=6)
        self.weather_lbl = ctk.CTkLabel(self, text="Fetching weather…",
                                         font=(_MONO_FONT, 10),
                                         text_color=TEXT_DIM, wraplength=190)
        self.weather_lbl.pack(padx=10, pady=(0,10))

    def _start_clock(self):
        def _tick():
            now = datetime.datetime.now()
            self.time_lbl.configure(text=now.strftime("%H:%M:%S"))
            self.date_lbl.configure(text=now.strftime("%A, %B %d %Y"))
            self.after(1000, _tick)
        _tick()

    def _fetch_weather(self):
        w = get_weather()
        self.after(0, lambda: self.weather_lbl.configure(
            text=f"⛅  {w}", text_color=TEXT))


# ── API Key Dialog ────────────────────────────────────────────────────────────

class APIKeyDialog(SafeTopLevel):
    def __init__(self, parent, on_save):
        super().__init__(parent)
        self.title("API Key")
        self.geometry("400x180")
        self.resizable(False, False)
        self.configure(fg_color=BG_CARD)
        self.grab_set()
        ctk.CTkLabel(self, text="Anthropic API Key",
                     font=(_MONO_FONT, 13, "bold"),
                     text_color=ACCENT).pack(pady=(18,4))
        ctk.CTkLabel(self, text="console.anthropic.com",
                     font=F_SUB, text_color=TEXT_DIM).pack(pady=(0,10))
        self.e = ctk.CTkEntry(self, width=340, show="•",
                               placeholder_text="sk-ant-...",
                               fg_color=BG, text_color=TEXT, font=F_MONO)
        self.e.pack(pady=(0,12))
        ctk.CTkButton(self, text="CONNECT", width=160,
                      fg_color=ACCENT2, hover_color="#4422cc",
                      command=lambda: on_save(self.e.get(), self)).pack()


# ── Camera Preview ────────────────────────────────────────────────────────────

class VideoPreviewDialog(SafeTopLevel):
    def __init__(self, parent, video_path, on_send):
        super().__init__(parent)
        self.title("Video Recording")
        self.geometry("420x200")
        self.configure(fg_color=BG_CARD)
        self.grab_set()
        self._video_path = video_path
        self._on_send    = on_send
        ctk.CTkLabel(self, text="📹  Recording saved",
                     font=(_MONO_FONT, 13, "bold"),
                     text_color=ACCENT).pack(pady=(18,4))
        ctk.CTkLabel(self, text=Path(video_path).name,
                     font=F_SUB, text_color=TEXT_DIM).pack(pady=(0,10))
        self.caption = ctk.CTkEntry(self, width=360, fg_color=BG,
                                     text_color=TEXT, font=F_MONO,
                                     placeholder_text="Describe the recording…")
        self.caption.pack(pady=(0,12))
        self.caption.bind("<Return>", lambda e: self._send())
        ctk.CTkButton(self, text="SEND TO HUBERT", width=200,
                      fg_color=ACCENT2, hover_color="#4422cc",
                      command=self._send).pack()

    def _send(self):
        caption = self.caption.get().strip() or "I just recorded a video. Please note it."
        self.destroy()
        self._on_send(self._video_path, caption)



# ── Main App ──────────────────────────────────────────────────────────────────

class HubertApp(ctk.CTk):
    CHAT_MAX_W = 780

    LAST_SESSION_FILE = Path(__file__).parent / "last_session.md"

    def __init__(self):
        super().__init__()
        global _app_instance
        _app_instance = self
        self._muted: bool = False
        self.title("H.U.B.E.R.T.")
        self.geometry("1420x820")
        self.minsize(1000, 620)
        self.configure(fg_color=BG)
        self._claude_core      = JarvisCore()
        self._ollama_core      = None
        self._ollama_mode      = False
        self._claude_code_mode = True        # Claude Code CLI is the default mode
        self.core              = self._claude_core
        self._last_file_path   = None   # set by _send() when a non-image file is attached
        self._session_files: dict[str, dict] = {}   # path → metadata; persists whole chat
        self._cc_history:   list[dict] = []          # conversation history for CC mode
        self._cc_buf:       str = ""                 # accumulates current CC response
        self._q: queue.Queue = queue.Queue()
        self._build_ui()
        self._process_q()
        self.after(200, self._run_boot)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def speak(self, text: str):
        """Speak text via ElevenLabs (British JARVIS voice). Serialised through
        a single background queue. Falls back to en-GB-RyanNeural edge-tts,
        then pyttsx3."""
        if self._muted:
            return
        import re
        # Strip markdown noise
        text = re.sub(r'[*_`#>~]', '', text).strip()
        # Pronounce HUBERT as the word, not the acronym
        text = re.sub(r'\bH\.U\.B\.E\.R\.T\.?\b', 'Hubert', text)
        text = re.sub(r'\bHUBERT\b', 'Hubert', text)
        if not text:
            return

        _ensure_tts_worker()

        def _play():
            import ui_bridge as _ub
            _ub.push("sphere_speaking", active=True)
            try:
                import tempfile as _tf, os as _os
                from config import get_elevenlabs_config

                tmp = None

                # 1. Try ElevenLabs (primary — British JARVIS voice)
                el_cfg = get_elevenlabs_config()
                if el_cfg:
                    try:
                        import requests as _req
                        resp = _req.post(
                            f"https://api.elevenlabs.io/v1/text-to-speech/{el_cfg['voice_id']}",
                            headers={
                                "xi-api-key": el_cfg["api_key"],
                                "Content-Type": "application/json",
                            },
                            json={
                                "text": text,
                                "model_id": "eleven_turbo_v2_5",
                                "voice_settings": {
                                    "stability": 0.45,
                                    "similarity_boost": 0.85,
                                    "style": 0.35,
                                    "use_speaker_boost": True,
                                },
                            },
                            timeout=10,
                        )
                        if resp.status_code == 200:
                            fd, tmp = _tf.mkstemp(suffix=".mp3")
                            _os.close(fd)
                            with open(tmp, "wb") as _f:
                                _f.write(resp.content)
                        else:
                            import sys as _sys
                            print(f"[HUBERT TTS] ElevenLabs {resp.status_code}: {resp.text[:120]}", file=_sys.stderr)
                    except Exception:
                        tmp = None

                # 2. Fall back to edge-tts with British voice
                if tmp is None:
                    import asyncio
                    import edge_tts

                    async def _synth():
                        tts = edge_tts.Communicate(text, "en-GB-RyanNeural",
                                                   rate="+5%")
                        fd, path = _tf.mkstemp(suffix=".mp3")
                        _os.close(fd)
                        try:
                            await tts.save(path)
                        except Exception:
                            try:
                                _os.unlink(path)
                            except Exception:
                                pass
                            raise
                        return path

                    loop = asyncio.new_event_loop()
                    try:
                        tmp = loop.run_until_complete(_synth())
                    finally:
                        loop.close()

                # 3. Play the mp3 (sounddevice → pygame)
                played = False
                try:
                    import sounddevice as sd
                    from pydub import AudioSegment
                    import numpy as np
                    seg  = AudioSegment.from_mp3(tmp)
                    pcm  = np.array(seg.get_array_of_samples(), dtype=np.float32)
                    pcm /= 2 ** (seg.sample_width * 8 - 1)
                    if seg.channels == 2:
                        pcm = pcm.reshape(-1, 2)
                    sd.play(pcm, seg.frame_rate)
                    sd.wait()
                    played = True
                except Exception:
                    pass

                if not played:
                    try:
                        import pygame
                        pygame.mixer.init()
                        pygame.mixer.music.load(tmp)
                        pygame.mixer.music.play()
                        while pygame.mixer.music.get_busy():
                            time.sleep(0.05)
                        played = True
                    except Exception:
                        pass

                try:
                    _os.unlink(tmp)
                except Exception:
                    pass

                if not played:
                    raise RuntimeError("no audio backend")

            except Exception:
                try:
                    import pyttsx3
                    e = pyttsx3.init()
                    e.setProperty("rate", 185)
                    e.say(text)
                    e.runAndWait()
                except Exception:
                    pass
            finally:
                _ub.push("sphere_speaking", active=False)

        _tts_enqueue(_play)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Header ──
        hdr = ctk.CTkFrame(self, fg_color=BG_PANEL, corner_radius=0, height=58)
        hdr.pack(fill="x", side="top")
        hdr.pack_propagate(False)

        # Menu button
        self.menu_btn = ctk.CTkButton(
            hdr, text="≡", width=42, height=42,
            fg_color=DIM, hover_color=DIM2, text_color=ACCENT,
            font=(_MONO_FONT, 18, "bold"), corner_radius=8,
            command=self._toggle_menu)
        self.menu_btn.pack(side="left", padx=10, pady=8)

        # Logo + title centred
        mid = ctk.CTkFrame(hdr, fg_color="transparent")
        mid.pack(side="left", expand=True)
        logo_row = ctk.CTkFrame(mid, fg_color="transparent")
        logo_row.pack()
        self.logo = AnimatedLogo(logo_row, size=46)
        self.logo.pack(side="left", padx=(0, 10))
        title_col = ctk.CTkFrame(logo_row, fg_color="transparent")
        title_col.pack(side="left")
        ctk.CTkLabel(title_col, text="H.U.B.E.R.T.",
                     font=F_TITLE, text_color=ACCENT).pack(anchor="w")
        ctk.CTkLabel(title_col,
                     text="Highly Unified Brilliant Experimental Research Terminal",
                     font=F_SUB, text_color=TEXT_DIM).pack(anchor="w")

        # Right controls
        right = ctk.CTkFrame(hdr, fg_color="transparent")
        right.pack(side="right", padx=12)
        self.status_dot = StatusDot(right)
        self.status_dot.pack(side="left", padx=(0, 5))
        self.status_lbl = ctk.CTkLabel(right, text="OFFLINE",
                                        font=(_MONO_FONT, 8),
                                        text_color=TEXT_DIM)
        self.status_lbl.pack(side="left")
        ctk.CTkButton(right, text="◈", width=32, height=32,
                      fg_color=DIM, hover_color=DIM2, text_color=ACCENT,
                      font=(_MONO_FONT, 13), corner_radius=6,
                      command=self._toggle_map).pack(side="left", padx=(10,0))
        ctk.CTkButton(right, text="⟳", width=32, height=32,
                      fg_color=DIM, hover_color=DIM2, text_color=TEXT_DIM,
                      font=(_MONO_FONT, 11), corner_radius=6,
                      command=self._clear).pack(side="left", padx=(6,0))
        # Claude Code / Ollama mode toggle
        self._mode_btn = ctk.CTkButton(
            right, text="CLAUDE", width=80, height=28,
            fg_color="#5500cc", hover_color="#3300aa", text_color="#ffffff",
            font=(_MONO_FONT, 8, "bold"), corner_radius=6,
            command=self._toggle_ollama_mode,
        )
        self._mode_btn.pack(side="left", padx=(8, 0))

        # ── Body: three-column PanedWindow ──
        self._paned = tk.PanedWindow(self, orient="horizontal",
                                     sashwidth=5, sashrelief="flat",
                                     bg=DIM, showhandle=False)
        self._paned.pack(fill="both", expand=True)

        # Col 0 — Swarm panel
        self.swarm_panel = SwarmPanel(self._paned)
        self._paned.add(self.swarm_panel, minsize=180, width=300, stretch="never")
        self.swarm_panel.add_cc_node()   # CC is the default mode

        # Col 1 — Chat column (sphere + chat + voice + input)
        center = tk.Frame(self._paned, bg=BG)
        self._paned.add(center, minsize=360, stretch="always")

        self.sphere = SphereWidget(center,
                                   on_mute_toggle=self._on_sphere_mute)
        self.sphere.pack(fill="x", pady=(0, 0))

        self.chat = ChatDisplay(center)
        self.chat.pack(fill="both", expand=True, pady=(0, 4), padx=8)

        self.voice_panel = VoicePanel(center, height=72)
        self.voice_panel.pack(fill="x", padx=8, pady=(0, 4))
        self.voice_panel.pack_propagate(False)

        self.input_bar = InputBar(center, on_send=self._send,
                                  on_camera=self._on_video)
        self.input_bar.pack(fill="x", padx=8, pady=(0, 8))
        self._voice_listening = False

        def _on_mic_state(active: bool):
            self._voice_listening = active
            self.voice_panel.set_active(active)

        self.input_bar._on_mic_state   = _on_mic_state
        self.input_bar._on_transcript  = self.voice_panel.set_transcript

        # Col 2 — HUD panel
        self.hud_panel = HUDPanel(self._paned)
        self._paned.add(self.hud_panel, minsize=162, width=200, stretch="never")
        # Wire camera snapshot → chat
        self.hud_panel._cam_on_send = self._on_cam_snapshot

        # Double-click any sash → reset column widths
        self._paned.bind("<Double-Button-1>", self._reset_pane_widths)

        import tools as _tr
        _tr.on_new_tool(lambda name: self._q_put(self._on_new_tool, name))

        self.drawer = MenuDrawer(self)
        self.drawer._on_api_key = self._prompt_api_key

    def _on_sphere_mute(self, muted: bool):
        self._muted = muted

    def _reset_pane_widths(self, event=None):
        total = self._paned.winfo_width()
        self._paned.sash_place(0, 300, 1)
        self._paned.sash_place(1, total - 200, 1)

    def _on_resize(self, event=None):
        pass  # grid handles layout; swarm panel is fixed width, chat expands

    # ── Boot ──────────────────────────────────────────────────────────────────

    def _run_boot(self):
        # CC mode uses the claude CLI — no Anthropic API key needed
        from claude_code_backend import _find_claude_bin
        if self._claude_code_mode and _find_claude_bin():
            self._set_status("thinking", "BOOTING")
            BootScreen(self, on_complete=self._boot_done)
            return
        if not self.core.is_ready():
            self.after(100, self._prompt_api_key)
            self._set_status("offline")
            return
        self._set_status("thinking", "BOOTING")
        BootScreen(self, on_complete=self._boot_done)

    def _boot_done(self):
        self._set_status("ready")
        self.chat.system("Hubert online — all systems operational.")
        self._show_weather_card()
        self._start_dream_scheduler()
        # Preload Whisper + mic index in background
        threading.Thread(target=_get_whisper,   daemon=True).start()
        threading.Thread(target=_get_mic_index, daemon=True).start()
        # Inject last session context into conversation history for all modes
        self._prime_memory()
        # Show recap in chat and pipeline report
        self._show_last_session()
        self._show_pipeline_report()
        # Initialize project engine
        try:
            from project_engine import ProjectEngine
            self._project_engine = ProjectEngine(on_status=self._set_status)
        except Exception:
            self._project_engine = None

    def _prime_memory(self):
        """
        Inject last-session context into conversation histories for all modes
        so HUBERT remembers previous conversations from the first message.
        """
        try:
            if not self.LAST_SESSION_FILE.exists():
                return
            recap = self.LAST_SESSION_FILE.read_text(encoding="utf-8").strip()
            if not recap:
                return

            primer_user = (
                "[SYSTEM: Context from previous session — read and remember this.]\n"
                + recap
            )
            primer_assistant = (
                "Understood. I've reviewed our previous session and will maintain continuity."
            )

            # Prime JarvisCore (Claude API mode)
            if hasattr(self, "_claude_core") and self._claude_core:
                if not self._claude_core.conversation_history:
                    self._claude_core.conversation_history.append(
                        {"role": "user", "content": primer_user}
                    )
                    self._claude_core.conversation_history.append(
                        {"role": "assistant", "content": primer_assistant}
                    )

            # Prime Ollama core if already initialized
            if self._ollama_core and not self._ollama_core.conversation_history:
                self._ollama_core.conversation_history.append(
                    {"role": "user", "content": primer_user}
                )
                self._ollama_core.conversation_history.append(
                    {"role": "assistant", "content": primer_assistant}
                )

            # CC history primed lazily at first message (see _send())
        except Exception:
            pass

    def _show_last_session(self):
        """Display last session recap in chat — no voice to avoid stacking on boot greeting."""
        try:
            if not self.LAST_SESSION_FILE.exists():
                return
            recap = self.LAST_SESSION_FILE.read_text(encoding="utf-8").strip()
            if not recap:
                return
            self.chat.system(f"Last session recap:\n{recap}")
        except Exception:
            pass

    def _show_pipeline_report(self):
        """Show nightly memory pipeline status on boot — ran or skipped."""
        try:
            from pathlib import Path as _Path
            import datetime as _dt
            last_run_file = _Path(__file__).parent / ".memory_pipeline_last_run"
            if not last_run_file.exists():
                return
            last_run = _dt.date.fromisoformat(last_run_file.read_text().strip())
            today = _dt.date.today()
            yesterday = today - _dt.timedelta(days=1)
            if last_run not in (today, yesterday):
                return
            # Count what was written overnight
            vault = _Path.home() / "HUBERT_Vault"
            counts = {}
            for folder, label in [
                ("Memory/Decisions",    "decisions"),
                ("Memory/Action Items", "action items"),
                ("Memory/People",       "people"),
                ("Memory/Facts",        "facts"),
                ("Memory/Insights",     "insights"),
            ]:
                notes = list((vault / folder).glob(f"{last_run}*.md"))
                if notes:
                    counts[label] = len(notes)
            if counts:
                summary = ", ".join(f"{v} {k}" for k, v in counts.items())
                self.chat.system(
                    f"Nightly pipeline ran ({last_run}) — extracted: {summary}. "
                    f"Memory map updated."
                )
            else:
                self.chat.system(
                    f"Nightly pipeline ran ({last_run}) — no new entities extracted from sessions."
                )
        except Exception:
            pass

    def _on_close(self):
        """Save session to last_session.md and Obsidian vault before exiting."""
        try:
            # Build a rich session log from whichever mode was active
            if self._claude_code_mode and self._cc_history:
                history_source = self._cc_history
            else:
                history_source = self.core.conversation_history

            lines = []
            import datetime as _dt
            lines.append(f"Session: {_dt.datetime.now().strftime('%Y-%m-%d %H:%M')}")
            for turn in history_source[-30:]:   # last 30 turns
                role = turn.get("role", "")
                content = turn.get("content", "")
                if not isinstance(content, str):
                    # Anthropic message blocks — extract text
                    if isinstance(content, list):
                        content = " ".join(
                            b.get("text", "") for b in content
                            if isinstance(b, dict) and b.get("type") == "text"
                        )
                    else:
                        continue
                if not content.strip():
                    continue
                label = "User" if role == "user" else "HUBERT"
                lines.append(f"{label}: {content[:500]}")

            if len(lines) > 1:  # more than just the timestamp
                self.LAST_SESSION_FILE.write_text("\n".join(lines), encoding="utf-8")
        except Exception:
            pass
        # Persist session to Obsidian vault + dream if in Ollama mode
        if self._ollama_mode and self._ollama_core:
            try:
                self._ollama_core._save_session_to_obsidian()
                # Dream runs in a thread so the window closes immediately
                import threading as _th
                _th.Thread(
                    target=self._ollama_core._run_end_of_session_dream,
                    daemon=True,
                ).start()
            except Exception:
                pass
        else:
            try:
                from jarvis_core import _save_session_to_obsidian
                _save_session_to_obsidian(self.core.conversation_history)
            except Exception:
                pass
        self.destroy()

    def _start_dream_scheduler(self):
        """Background thread: trigger a deep dream at 2 AM nightly."""
        def _scheduler():
            dreamed_date = None
            while True:
                try:
                    now = datetime.datetime.now()
                    if now.hour == 2 and dreamed_date != now.date():
                        dreamed_date = now.date()
                        try:
                            # Run memory pipeline first (entity extraction, canvas rebuild)
                            from memory_pipeline import run_nightly
                            run_nightly()
                        except Exception:
                            pass
                        try:
                            if self._ollama_mode and self._ollama_core:
                                # Local dream via Gemma 4 — zero tokens
                                self._ollama_core._run_end_of_session_dream()
                            else:
                                from tools.custom.dream_engine import run_dream
                                run_dream({"topic": "recent conversations and goals", "depth": "deep"})
                            self._q.put((self.chat.system,
                                         ("HUBERT dreamed tonight — insights written to Obsidian.",)))
                        except Exception:
                            pass
                except Exception:
                    pass
                time.sleep(60)
        threading.Thread(target=_scheduler, daemon=True).start()

    def _show_weather_card(self):
        if hasattr(self, "_weather_card") and self._weather_card.winfo_exists():
            return
        self._weather_card = WeatherCard(self)
        self._weather_card.place(relx=1.0, x=-234, y=68)
        self._weather_card.lift()

    # ── Status ────────────────────────────────────────────────────────────────

    def _set_status(self, s, label=None):
        labels = {"ready": "READY", "thinking": "THINKING",
                  "error": "ERROR", "offline": "OFFLINE"}
        self.status_dot.set_status(s)
        self.status_lbl.configure(text=label or labels.get(s, s.upper()))

    # ── Queue ──────────────────────────────────────────────────────────────────

    def _q_put(self, fn, *args):
        self._q.put((fn, args))

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

    # ── Send ──────────────────────────────────────────────────────────────────

    def _send(self, text: str = None, image_path: str = None, voice: bool = False,
              file_path: str = None, file_paths: list = None):
        # Normalise: merge legacy file_path + file_paths into one list
        all_files: list[str] = list(file_paths or [])
        if file_path and file_path not in all_files:
            all_files.append(file_path)

        if text is None:
            text = self.input_bar.entry.get("1.0", "end").strip()

        # Process all attached files — register them, extract context for LLM
        new_file_paths: set[str] = set()
        context_blocks: list[str] = []
        pending_cards: list[dict] = []   # shown in chat after user bubble

        if all_files:
            from file_upload_utils import classify_file, build_context_block
            for fp in all_files:
                if classify_file(fp) == "image" and not image_path:
                    image_path = fp
                    # Also register as session file for memory
                    info = self._register_file(fp)
                    new_file_paths.add(fp)
                    pending_cards.append(info)
                else:
                    self._last_file_path = fp
                    info = self._register_file(fp)
                    new_file_paths.add(fp)
                    context_blocks.append(build_context_block(fp))
                    pending_cards.append(info)

        # For PDF files: pass rendered thumbnail to Claude API vision (not Ollama/CC — no vision)
        _vision_mode = not self._ollama_mode and not self._claude_code_mode
        if not image_path and all_files and _vision_mode:
            for fp in all_files:
                if fp in self._session_files and self._session_files[fp].get("thumb"):
                    image_path = self._session_files[fp]["thumb"]
                    break

        # api_text = typed message + full context for NEW files + session reminder for old ones
        api_text = text or ""
        if context_blocks:
            api_text += "".join(context_blocks)
        session_ctx = self._build_session_context(exclude_paths=new_file_paths)
        if session_ctx:
            api_text += session_ctx

        if not api_text.strip() and not image_path:
            # No text and no image — but may have session files, inject reminder
            if self._session_files:
                api_text = self._build_session_context()
            else:
                return
        if not api_text.strip():
            api_text = "What do you see in this image?"

        # display_text = clean message shown in chat bubble (no extracted document text)
        display_text = text or ("[Image attached]" if image_path and not all_files else "")
        if not display_text and pending_cards:
            display_text = f"[{len(pending_cards)} file(s) attached]"

        # Voice mode: append spoken-style instruction to api_text
        if voice or getattr(self, "_voice_listening", False):
            api_text += (
                "\n\n[VOICE MODE: Reply in 1-2 short sentences. "
                "Confirm the action or give a brief answer. "
                "No lists, no markdown, no long explanations.]"
            )
        # Project engine intercept — handle before normal dispatch
        if getattr(self, "_project_engine", None):
            project_response = self._project_engine.intercept(text or "")
            if project_response is not None:
                self.input_bar.set_enabled(True)
                self.chat.add_user(display_text or "")
                for info in pending_cards:
                    self._show_file_card(info)
                self.chat.system(project_response)
                return
        self.input_bar.set_enabled(False)
        self.chat.set_working(True)
        self._set_status("thinking")
        self.chat.add_user(display_text or "")
        # Show file cards below the user bubble
        for info in pending_cards:
            self._show_file_card(info)
        self.chat.show_typing()
        self._tts_buf = ""   # reset sentence buffer for this response
        _tts_cancel()        # discard any stale queued sentences from prior response

        def _on_text(c):
            self._q_put(self.chat.stream, c)
            self._tts_feed(c)   # stream into TTS sentence splitter

        # ── CC mode history tracking ──────────────────────────────────────────
        if self._claude_code_mode:
            # Record user turn before sending
            self._cc_history.append({"role": "user", "content": display_text or api_text[:400]})
            self._cc_buf = ""

            def _on_text_cc(chunk):
                self._cc_buf += chunk
                _on_text(chunk)

            def _on_done_cc():
                # Record assistant response in history
                if self._cc_buf.strip():
                    self._cc_history.append({"role": "assistant", "content": self._cc_buf.strip()})
                self._cc_buf = ""
                self._q_put(self._done)

        # Pick the right chat_in_thread depending on active mode
        if self._claude_code_mode:
            from claude_code_backend import chat_in_thread as _cc_chat
            # Load last session recap once (first CC message in session)
            _last_sess = None
            if len(self._cc_history) <= 1 and self.LAST_SESSION_FILE.exists():
                try:
                    _last_sess = self.LAST_SESSION_FILE.read_text(encoding="utf-8").strip() or None
                except Exception:
                    pass
            _cc_chat(
                api_text,
                history        = self._cc_history[:-1],  # exclude the turn we just appended
                last_session   = _last_sess,
                on_text        = _on_text_cc,
                on_done        = _on_done_cc,
                on_error       = lambda e: self._q_put(self._error, e),
                on_tool_start  = lambda n, p: self._q_put(self.swarm_panel.on_cc_tool_call, n),
                on_tool_result = lambda n, r: self._q_put(self.swarm_panel.on_tool_result, n, r),
                on_status      = lambda s: self._q_put(self.swarm_panel._log_event, "sys", s),
            )
        elif self._ollama_mode:
            from ollama_orchestrator import chat_in_thread as _oll_chat
            _oll_chat(
                self.core, api_text,
                image_path      = image_path,
                on_text         = _on_text,
                on_tool_start   = lambda n, p: self._q_put(self._tool_start, n, p),
                on_tool_result  = lambda n, r: self._q_put(self._tool_result, n, r),
                on_done         = lambda: self._q_put(self._done),
                on_error        = lambda e: self._q_put(self._error, e),
                on_status       = lambda s: self._q_put(self._status, s),
            )
        else:
            chat_in_thread(
                self.core, api_text,
                image_path      = image_path,
                on_text         = _on_text,
                on_tool_start   = lambda n, p: self._q_put(self._tool_start, n, p),
                on_tool_result  = lambda n, r: self._q_put(self._tool_result, n, r),
                on_done         = lambda: self._q_put(self._done),
                on_error        = lambda e: self._q_put(self._error, e),
                on_status       = lambda s: self._q_put(self._status, s),
                on_usage        = lambda t: self._q_put(self.swarm_panel.update_token_pct, t),
                on_tool_groups  = lambda g: self._q_put(self.swarm_panel.set_active_tool_groups, g),
            )

    def _show_file_card(self, info: dict):
        """Show a file card in chat for an attached or generated document."""
        name  = info.get("name", "file")
        path  = info.get("path", "")
        thumb = info.get("thumb")
        parts = []
        if info.get("page_count"):
            parts.append(f"{info['page_count']} pages")
        if info.get("size_kb"):
            parts.append(f"{info['size_kb']} KB")
        if info.get("char_count"):
            parts.append(f"{info['char_count']:,} chars extracted")
        desc = "  ·  ".join(parts) if parts else ""
        self.chat.file_card(name, path, info=desc, thumb_path=thumb)

    def _tool_start(self, name, params):
        self.chat.end_hubert()
        self.chat.tool_call(name, params)
        self.drawer.log_op(name)
        self.swarm_panel.on_tool_call(name)

    def _tool_result(self, name, result):
        self.chat.tool_result(name, result)
        self.swarm_panel.on_tool_result(name, result)
        # Detect document creation tools → show a file card with Open button
        if name in ("create_document", "reformat_document", "combine_documents"):
            import re
            m = re.search(r"saved:\s*(.+?)(?:\s*\(|$)", result)
            if m:
                out_path = m.group(1).strip()
                from pathlib import Path as _P
                if _P(out_path).exists():
                    from file_upload_utils import get_file_info
                    info = get_file_info(out_path)
                    info["thumb"] = None  # no thumbnail for output docs
                    self._show_file_card(info)
        if "agent" in name.lower() or "spawn" in name.lower():
            label = f"{name} @ {ts()}"
            self.drawer.add_subagent(label)
            self.swarm_panel.on_agent_spawn(label)

    def _done(self):
        self.chat.end_hubert()
        self._set_status("ready")
        self.chat.set_working(False)
        self.input_bar.set_enabled(True)
        # Flush any remaining TTS buffer (short trailing text that had no sentence-end)
        self._tts_flush()

    def _tts_flush(self):
        """Speak whatever is left in the TTS sentence buffer."""
        buf = getattr(self, "_tts_buf", "").strip()
        if buf:
            self._tts_buf = ""
            self.speak(buf)

    def _tts_feed(self, chunk: str):
        """
        Called on every streaming text chunk. Accumulates into _tts_buf and fires
        speak() as soon as a sentence boundary is detected, so the first sentence
        starts playing while the rest of the response is still being generated.
        Only active when the mic listen toggle is ON (voice mode).
        """
        if not getattr(self, "_voice_listening", False):
            return
        if not hasattr(self, "_tts_buf"):
            self._tts_buf = ""
        self._tts_buf += chunk
        # Fire on sentence boundary — period/!/?  followed by space or end
        import re
        sentences = re.split(r'(?<=[.!?])\s+', self._tts_buf)
        if len(sentences) > 1:
            # Speak all complete sentences, keep the trailing fragment
            to_speak   = " ".join(sentences[:-1]).strip()
            self._tts_buf = sentences[-1]
            if to_speak:
                self.speak(to_speak)

    def _status(self, msg: str):
        """Show a non-fatal status message (e.g. retry notice) in the chat."""
        self.chat.add_status(msg)

    def _error(self, err):
        self.chat.end_hubert()
        self._set_status("error")
        self.chat.set_working(False)
        self.input_bar.set_enabled(True)
        try:
            self.hud_panel.log_error(err)
        except Exception:
            pass

        # Auto-switch to Claude Code CLI if Anthropic API credits are exhausted
        err_lower = str(err).lower()
        if ("credit balance" in err_lower or "too low" in err_lower) and not self._ollama_mode and not self._claude_code_mode:
            from claude_code_backend import _find_claude_bin
            if _find_claude_bin():
                self._claude_code_mode = True
                self._mode_btn.configure(
                    text="🔗 CC",
                    fg_color="#5500cc", hover_color="#3300aa",
                )
                self.chat.system(
                    "🔗 Anthropic API credits depleted — auto-switched to Claude Code CLI mode. "
                    "Using your Claude.ai subscription. "
                    "Top up at console.anthropic.com to re-enable direct API mode."
                )
                return
            self.chat.error(
                "Anthropic API credits depleted. Top up at console.anthropic.com "
                "→ Plans & Billing, or switch to 🔗 CC (Claude Code CLI) / ⚡ GEMMA4 mode."
            )

    def _on_new_tool(self, name: str):
        self.chat.system(f"New skill loaded: {name}  —  synced from Claude Code")
        self.speak(f"New skill loaded: {name.replace('_', ' ')}")

    # ── Session file registry ─────────────────────────────────────────────────

    def _register_file(self, path: str) -> dict:
        """Register a file in the session, extract text, render PDF thumbnail."""
        from file_upload_utils import get_file_info, render_pdf_page
        info = get_file_info(path)
        thumb = None
        if info["ext"] == "pdf":
            thumb = render_pdf_page(path)
        info["thumb"] = thumb
        self._session_files[path] = info
        return info

    def _build_session_context(self, exclude_paths: set = None) -> str:
        """
        Build a context reminder block for all previously registered session files.
        Injected into every API message so HUBERT always knows what files are loaded.
        """
        if not self._session_files:
            return ""
        exclude = exclude_paths or set()
        parts = []
        for path, info in self._session_files.items():
            if path in exclude:
                continue  # already included as full context block
            preview = (info.get("text") or "")[:400].replace("\n", " ")
            desc = f"- {info['name']} ({info['size_kb']} KB"
            if info.get("page_count"):
                desc += f", {info['page_count']} pages"
            desc += f") — preview: {preview[:200]}…" if preview else ")"
            parts.append(desc)
        if not parts:
            return ""
        return (
            "\n\n[Session files available — you can reference, reformat, or combine these:\n"
            + "\n".join(parts)
            + "\nUse reformat_document(source_path, format, ...) or combine_documents(source_paths, ...) to work with them.]"
        )

    def _clear(self):
        self.core.clear_history()
        self.chat.clear()
        self._session_files.clear()
        self._cc_history.clear()
        self._cc_buf = ""
        self.chat.system("Conversation cleared.")

    # ── Overlays ──────────────────────────────────────────────────────────────

    def _toggle_menu(self): self.drawer.toggle()
    def _toggle_map(self):  self.swarm_panel.toggle_visibility()

    # ── Ollama / Claude mode toggle ────────────────────────────────────────────

    def _try_default_ollama(self):
        """On startup, silently switch to Gemma if Ollama is available.
        This means HUBERT never touches the Anthropic API unless you toggle to Claude."""
        try:
            from ollama_orchestrator import OllamaOrchestrator
            if self._ollama_core is None:
                self._ollama_core = OllamaOrchestrator()
            if self._ollama_core.is_ready():
                self._ollama_mode = True
                self.core = self._ollama_core
                model = self._ollama_core.get_model_name()
                self._mode_btn.configure(
                    text=f"⚡ {model.split(':')[0].upper()}",
                    fg_color="#00aa44", hover_color="#007733",
                )
                self.chat.system(
                    f"⚡ Running on local {model} — zero Anthropic tokens. "
                    "Click ⚡ to switch to ☁ Claude."
                )
        except Exception:
            pass   # Ollama not available — stay on Claude silently

    def _toggle_ollama_mode(self):
        # Toggle: CLAUDE (CC) ↔ GEMMA (Ollama)
        if not self._ollama_mode:
            # Switch to Ollama
            try:
                from ollama_orchestrator import OllamaOrchestrator
            except ImportError as e:
                self.chat.error(f"OllamaOrchestrator not found: {e}")
                return
            if self._ollama_core is None:
                self._ollama_core = OllamaOrchestrator()
            if not self._ollama_core.is_ready():
                self.chat.error(
                    "Ollama is not running or no compatible model found.\n"
                    "Run: ollama serve\n"
                    "Then pull a model: ollama pull gemma4:31b  (or gemma3:12b for a lighter option)"
                )
                return
            self._ollama_mode      = True
            self._claude_code_mode = False
            self.swarm_panel.remove_cc_node()
            self.core = self._ollama_core
            model = self._ollama_core.get_model_name()
            self._mode_btn.configure(
                text=f"⚡ {model.split(':')[0].upper()}",
                fg_color="#00aa44", hover_color="#007733",
            )
            self.chat.system(f"Switched to LOCAL mode — {model}. Zero Anthropic tokens.")
        else:
            # Switch back to Claude Code
            self._ollama_mode      = False
            self._claude_code_mode = True
            self.swarm_panel.add_cc_node()
            self.core = self._claude_core
            self._mode_btn.configure(
                text="CLAUDE",
                fg_color="#5500cc", hover_color="#3300aa",
            )
            self.chat.system("Switched back to Claude.")


    # ── Video ──────────────────────────────────────────────────────────────────

    def _on_video(self, path):
        VideoPreviewDialog(self, path, on_send=self._send_with_video)

    def _send_with_video(self, path, caption):
        self.chat.add_user(f"[📹 Video: {Path(path).name}] {caption}")
        self._send(caption + f" (I just recorded a video saved at: {path})")

    def _on_cam_snapshot(self, img_path: str):
        """Called when the HUD camera snapshot button is pressed."""
        self.chat.add_user(f"[📷 Camera snapshot]")
        self._send("What do you see in this camera snapshot?", image_path=img_path)

    # ── API Key ────────────────────────────────────────────────────────────────

    def _prompt_api_key(self):
        APIKeyDialog(self, on_save=self._save_key)

    def _save_key(self, key, dialog):
        key = key.strip()
        if not key.startswith("sk-"): return
        self.core.set_api_key(key)
        dialog.destroy()
        self._set_status("ready")
        self.chat.system("API key saved. H.U.B.E.R.T. is now online.")
        self.input_bar.set_enabled(True)
        self._show_weather_card()


# ── Single-instance lock ──────────────────────────────────────────────────────

def _ensure_single_instance():
    """
    Enforce a single running instance.
    Windows: named mutex via ctypes.windll
    Mac/Linux: fcntl file lock on a PID file
    Returns a handle/fd that must be kept alive for the process lifetime.
    """
    if _IS_WIN:
        import ctypes, ctypes.wintypes
        MUTEX_NAME = "Global\\HUBERT_SingleInstance"
        ERROR_ALREADY_EXISTS = 183
        mutex = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
        if ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            print("HUBERT is already running.")
            sys.exit(0)
        return mutex
    else:
        import fcntl
        lock_file = Path(os.path.expanduser("~")) / ".hubert.lock"
        fd = open(lock_file, "w")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            print("HUBERT is already running.")
            sys.exit(0)
        fd.write(str(os.getpid()))
        fd.flush()
        return fd  # keep open so lock is held


# ── Entry ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    _mutex = _ensure_single_instance()   # exits here if already running
    app = HubertApp()
    app.mainloop()
