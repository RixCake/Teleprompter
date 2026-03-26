"""
AV Teleprompter - Python/Tkinter macOS Teleprompter
Voice-activated scrolling, floating window, screen-share invisible via CGWindowLevel

Requirements (install via pip):
    pip install sounddevice numpy pyobjc-core pyobjc-framework-Cocoa pyobjc-framework-Quartz

Usage:
    python teleprompter.py
"""

import tkinter as tk
from tkinter import font as tkfont
import threading
import time
import math
import sys
import os

# ── Optional: pyobjc for screen-share invisibility & true floating ────────────
try:
    from Cocoa import NSApplication, NSApp, NSFloatingWindowLevel, NSWindow
    from Quartz import CGWindowLevelForKey, kCGMaximumWindowLevelKey
    HAS_PYOBJC = True
except ImportError:
    HAS_PYOBJC = False
    print("[INFO] pyobjc not found — window will float but won't be screen-share invisible.")
    print("       Install with: pip install pyobjc-core pyobjc-framework-Cocoa pyobjc-framework-Quartz")

# ── Optional: sounddevice for voice-activated scrolling ───────────────────────
try:
    import sounddevice as sd
    import numpy as np
    HAS_AUDIO = True
except ImportError:
    HAS_AUDIO = False
    print("[INFO] sounddevice/numpy not found — voice scroll disabled.")
    print("       Install with: pip install sounddevice numpy")


# ─────────────────────────────────────────────────────────────────────────────
#  CONFIGURATION — tune these to your taste / room
# ─────────────────────────────────────────────────────────────────────────────
class Config:
    # Window defaults
    WIN_WIDTH        = 800
    WIN_HEIGHT       = 220
    WIN_X            = 100          # initial position
    WIN_Y            = 40           # near top of screen (near camera)
    BG_COLOR         = "#0d0d0d"
    TEXT_COLOR       = "#ffffff"
    FONT_FAMILY      = "Helvetica Neue"
    FONT_SIZE        = 32
    FONT_WEIGHT      = "bold"
    LINE_SPACING     = 1.6

    # Scrolling
    SCROLL_SPEED_MIN = 0.3          # pixels per tick (slowest)
    SCROLL_SPEED_MAX = 6.0          # pixels per tick (fastest)
    SCROLL_SPEED_DEF = 1.5          # default
    SCROLL_TICK_MS   = 30           # ~33 fps scroll update

    # Voice activation
    MIC_SAMPLE_RATE  = 16000
    MIC_BLOCK_SIZE   = 512
    VOICE_THRESHOLD  = 0.015        # RMS threshold — raise if noisy room
    VOICE_HOLD_MS    = 600          # keep scrolling N ms after speech stops

    # Countdown
    COUNTDOWN_SEC    = 3

    # Colors
    HIGHLIGHT_COLOR  = "#ffd700"    # current-line highlight
    CARET_COLOR      = "#ff4444"
    METER_COLOR      = "#00e5ff"
    METER_BG         = "#1a1a1a"
    OVERLAY_BG       = "#111111"


# ─────────────────────────────────────────────────────────────────────────────
#  AUDIO ENGINE  — runs in background thread, publishes is_speaking flag
# ─────────────────────────────────────────────────────────────────────────────
class AudioEngine:
    def __init__(self, config: Config):
        self.cfg = config
        self.is_speaking = False
        self.rms_level   = 0.0          # 0.0–1.0, for VU meter
        self._last_voice  = 0.0
        self._stream      = None
        self._running     = False
        self.sensitivity  = 1.0         # multiplier adjusted by slider

    def start(self):
        if not HAS_AUDIO:
            return
        self._running = True
        self._stream = sd.InputStream(
            samplerate  = self.cfg.MIC_SAMPLE_RATE,
            blocksize   = self.cfg.MIC_BLOCK_SIZE,
            channels    = 1,
            dtype       = "float32",
            callback    = self._callback,
        )
        self._stream.start()

    def stop(self):
        self._running = False
        if self._stream:
            self._stream.stop()
            self._stream.close()

    def _callback(self, indata, frames, time_info, status):
        rms = float(np.sqrt(np.mean(indata ** 2)))
        self.rms_level = min(rms * 8.0, 1.0)           # scale for display
        threshold = self.cfg.VOICE_THRESHOLD / self.sensitivity
        if rms > threshold:
            self._last_voice = time.time()
            self.is_speaking = True
        else:
            hold = self.cfg.VOICE_HOLD_MS / 1000.0
            if time.time() - self._last_voice > hold:
                self.is_speaking = False


# ─────────────────────────────────────────────────────────────────────────────
#  SCRIPT MODEL
# ─────────────────────────────────────────────────────────────────────────────
class Script:
    def __init__(self):
        self.text = ""

    def load(self, text: str):
        self.text = text.strip()

    def word_count(self):
        return len(self.text.split())

    def estimated_duration(self, wpm=130):
        return self.word_count() / wpm  # minutes


# ─────────────────────────────────────────────────────────────────────────────
#  EDITOR WINDOW
# ─────────────────────────────────────────────────────────────────────────────
class EditorWindow:
    def __init__(self, master, script: Script, on_load_callback):
        self.script   = script
        self.callback = on_load_callback
        self.win      = tk.Toplevel(master)
        self.win.title("Script Editor")
        self.win.configure(bg="#1a1a1a")
        self.win.geometry("700x500")
        self._build()

    def _build(self):
        toolbar = tk.Frame(self.win, bg="#111", pady=6)
        toolbar.pack(fill=tk.X)

        tk.Button(toolbar, text="▶  Load into Prompter", command=self._load,
                  bg="#00e5ff", fg="#000", font=("Helvetica Neue", 13, "bold"),
                  relief=tk.FLAT, padx=14, pady=4).pack(side=tk.LEFT, padx=10)

        tk.Button(toolbar, text="Clear", command=self._clear,
                  bg="#333", fg="#aaa", font=("Helvetica Neue", 11),
                  relief=tk.FLAT, padx=10, pady=4).pack(side=tk.LEFT)

        self.wc_label = tk.Label(toolbar, text="0 words", bg="#111", fg="#555",
                                  font=("Helvetica Neue", 11))
        self.wc_label.pack(side=tk.RIGHT, padx=14)

        frame = tk.Frame(self.win, bg="#1a1a1a")
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        scrollbar = tk.Scrollbar(frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.text_area = tk.Text(
            frame,
            font=("Helvetica Neue", 15),
            bg="#1a1a1a", fg="#e0e0e0",
            insertbackground="#fff",
            selectbackground="#333",
            relief=tk.FLAT,
            wrap=tk.WORD,
            yscrollcommand=scrollbar.set,
            padx=16, pady=12,
        )
        self.text_area.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.text_area.yview)

        if self.script.text:
            self.text_area.insert("1.0", self.script.text)

        self.text_area.bind("<KeyRelease>", self._update_wc)
        self._update_wc()

    def _update_wc(self, event=None):
        text = self.text_area.get("1.0", tk.END).strip()
        words = len(text.split()) if text else 0
        mins  = words / 130
        self.wc_label.config(text=f"{words} words · ~{mins:.1f} min @ 130 wpm")

    def _load(self):
        text = self.text_area.get("1.0", tk.END)
        self.script.load(text)
        self.callback()
        self.win.destroy()

    def _clear(self):
        self.text_area.delete("1.0", tk.END)
        self._update_wc()


# ─────────────────────────────────────────────────────────────────────────────
#  CONTROL BAR  — separate always-on-top toolbar
# ─────────────────────────────────────────────────────────────────────────────
class ControlBar:
    def __init__(self, master, prompter):
        self.prompter = prompter
        self.win = tk.Toplevel(master)
        self.win.title("Teleprompter Controls")
        self.win.configure(bg="#111")
        self.win.geometry("620x90+100+310")
        self.win.resizable(False, False)
        self.win.attributes("-topmost", True)
        self._build()

    def _build(self):
        p = self.prompter
        btn_cfg = dict(bg="#1e1e1e", fg="#ddd", relief=tk.FLAT,
                       font=("Helvetica Neue", 12), padx=10, pady=6,
                       activebackground="#333", activeforeground="#fff",
                       bd=0)

        row1 = tk.Frame(self.win, bg="#111")
        row1.pack(fill=tk.X, padx=10, pady=(8, 0))

        tk.Button(row1, text="✏  Edit Script", command=p.open_editor, **btn_cfg).pack(side=tk.LEFT, padx=2)
        tk.Button(row1, text="▶  Start", command=p.start_countdown, **btn_cfg).pack(side=tk.LEFT, padx=2)
        tk.Button(row1, text="⏸  Pause", command=p.toggle_pause, **btn_cfg).pack(side=tk.LEFT, padx=2)
        tk.Button(row1, text="⏮  Reset", command=p.reset_scroll, **btn_cfg).pack(side=tk.LEFT, padx=2)

        # Voice toggle
        self.voice_var = tk.BooleanVar(value=True)
        tk.Checkbutton(row1, text="🎙 Voice", variable=self.voice_var,
                       command=lambda: setattr(p, "voice_active", self.voice_var.get()),
                       bg="#111", fg="#aaa", selectcolor="#333",
                       font=("Helvetica Neue", 12), relief=tk.FLAT,
                       activebackground="#111").pack(side=tk.LEFT, padx=8)

        row2 = tk.Frame(self.win, bg="#111")
        row2.pack(fill=tk.X, padx=10, pady=(4, 6))

        tk.Label(row2, text="Speed", bg="#111", fg="#666",
                 font=("Helvetica Neue", 11)).pack(side=tk.LEFT)
        self.speed_slider = tk.Scale(
            row2, from_=0.3, to=6.0, resolution=0.1, orient=tk.HORIZONTAL,
            command=lambda v: setattr(p, "scroll_speed", float(v)),
            bg="#111", fg="#aaa", highlightthickness=0,
            troughcolor="#222", activebackground="#00e5ff",
            length=140, sliderlength=16, width=10,
        )
        self.speed_slider.set(p.scroll_speed)
        self.speed_slider.pack(side=tk.LEFT, padx=(4, 16))

        tk.Label(row2, text="Mic Sens", bg="#111", fg="#666",
                 font=("Helvetica Neue", 11)).pack(side=tk.LEFT)
        self.sens_slider = tk.Scale(
            row2, from_=0.5, to=5.0, resolution=0.1, orient=tk.HORIZONTAL,
            command=self._set_sensitivity,
            bg="#111", fg="#aaa", highlightthickness=0,
            troughcolor="#222", activebackground="#00e5ff",
            length=120, sliderlength=16, width=10,
        )
        self.sens_slider.set(1.0)
        self.sens_slider.pack(side=tk.LEFT, padx=(4, 16))

        # VU meter canvas
        tk.Label(row2, text="Level", bg="#111", fg="#666",
                 font=("Helvetica Neue", 11)).pack(side=tk.LEFT)
        self.meter = tk.Canvas(row2, width=100, height=12,
                                bg=Config.METER_BG, highlightthickness=0)
        self.meter.pack(side=tk.LEFT, padx=4)
        self.meter_bar = self.meter.create_rectangle(0, 0, 0, 12,
                                                      fill=Config.METER_COLOR, outline="")

        self._update_meter()

    def _set_sensitivity(self, val):
        self.prompter.audio.sensitivity = float(val)

    def _update_meter(self):
        if HAS_AUDIO:
            level = self.prompter.audio.rms_level
            w = int(level * 100)
            color = "#ff4444" if level > 0.8 else Config.METER_COLOR
            self.meter.coords(self.meter_bar, 0, 0, w, 12)
            self.meter.itemconfig(self.meter_bar, fill=color)
        self.win.after(60, self._update_meter)


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN PROMPTER WINDOW
# ─────────────────────────────────────────────────────────────────────────────
class PrompterWindow:
    def __init__(self, root: tk.Tk, script: Script, audio: AudioEngine):
        self.root         = root
        self.script       = script
        self.audio        = audio
        self.cfg          = Config()

        # State
        self.scroll_y     = 0.0         # current scroll offset in pixels
        self.scroll_speed = Config.SCROLL_SPEED_DEF
        self.paused       = True
        self.voice_active = True
        self._dragging    = False
        self._drag_start  = (0, 0)
        self._win_start   = (0, 0)

        # Build window
        self.win = tk.Toplevel(root)
        self.win.title("Prompter")
        self.win.geometry(
            f"{Config.WIN_WIDTH}x{Config.WIN_HEIGHT}+{Config.WIN_X}+{Config.WIN_Y}"
        )
        self.win.configure(bg=Config.BG_COLOR)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.94)
        self.win.overrideredirect(True)       # borderless

        # Canvas for all rendering
        self.canvas = tk.Canvas(
            self.win,
            bg=Config.BG_COLOR,
            highlightthickness=0,
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self._setup_drag()
        self._setup_keyboard()
        self._setup_resize()
        self._render_frame()
        self._scroll_loop()

    # ── Screen-share invisibility (macOS pyobjc) ──────────────────────────
    def apply_screen_share_invisible(self):
        """
        Call after window is fully realized on macOS.
        Sets CGWindowSharingType to kCGWindowSharingNone so the window
        is excluded from screen capture, screenshots, and screen sharing.
        """
        if not HAS_PYOBJC:
            return
        try:
            from Quartz import CGWindowID
            # Get the native NSWindow for this Tk window
            wid = self.win.winfo_id()
            # Use Cocoa to find the NSWindow and set sharingType
            # This requires pyobjc-framework-Quartz
            import ctypes
            import ctypes.util
            qlib = ctypes.cdll.LoadLibrary(
                "/System/Library/Frameworks/QuartzCore.framework/QuartzCore"
            )
            # Simpler path: use AppKit NSWindow sharing type
            from AppKit import NSApp, NSWindow, NSWindowSharingNone
            for nswin in NSApp.windows():
                if nswin.windowNumber() > 0:
                    nswin.setSharingType_(NSWindowSharingNone)
        except Exception as e:
            print(f"[WARN] Screen-share invisibility not applied: {e}")

    # ── Drag to move (borderless window) ─────────────────────────────────
    def _setup_drag(self):
        self.canvas.bind("<ButtonPress-1>",   self._drag_start_cb)
        self.canvas.bind("<B1-Motion>",       self._drag_motion)
        self.canvas.bind("<ButtonRelease-1>", self._drag_stop)

    def _drag_start_cb(self, e):
        self._dragging  = True
        self._drag_start = (e.x_root, e.y_root)
        self._win_start  = (self.win.winfo_x(), self.win.winfo_y())

    def _drag_motion(self, e):
        if self._dragging:
            dx = e.x_root - self._drag_start[0]
            dy = e.y_root - self._drag_start[1]
            self.win.geometry(
                f"+{self._win_start[0]+dx}+{self._win_start[1]+dy}"
            )

    def _drag_stop(self, e):
        self._dragging = False

    # ── Keyboard shortcuts ────────────────────────────────────────────────
    def _setup_keyboard(self):
        self.win.bind("<space>",      lambda e: self.toggle_pause())
        self.win.bind("<Escape>",     lambda e: self.toggle_pause())
        self.win.bind("<Up>",         lambda e: self._nudge_speed(0.2))
        self.win.bind("<Down>",       lambda e: self._nudge_speed(-0.2))
        self.win.bind("<Left>",       lambda e: self._manual_scroll(-40))
        self.win.bind("<Right>",      lambda e: self._manual_scroll(40))
        self.win.bind("<Home>",       lambda e: self.reset_scroll())
        self.win.bind("<q>",          lambda e: self.root.quit())
        self.win.focus_set()

    def _nudge_speed(self, delta):
        self.scroll_speed = max(Config.SCROLL_SPEED_MIN,
                                 min(Config.SCROLL_SPEED_MAX,
                                     self.scroll_speed + delta))

    def _manual_scroll(self, px):
        self.scroll_y = max(0, self.scroll_y + px)

    # ── Resize handle ─────────────────────────────────────────────────────
    def _setup_resize(self):
        handle = tk.Label(self.win, text="◢", bg=Config.BG_COLOR,
                           fg="#333", font=("Helvetica Neue", 14), cursor="bottom_right_corner")
        handle.place(relx=1.0, rely=1.0, anchor="se")
        handle.bind("<ButtonPress-1>",   self._resize_start)
        handle.bind("<B1-Motion>",       self._resize_drag)

    def _resize_start(self, e):
        self._r_start = (e.x_root, e.y_root)
        self._r_size  = (self.win.winfo_width(), self.win.winfo_height())

    def _resize_drag(self, e):
        dw = e.x_root - self._r_start[0]
        dh = e.y_root - self._r_start[1]
        nw = max(400, self._r_size[0] + dw)
        nh = max(80,  self._r_size[1] + dh)
        self.win.geometry(f"{nw}x{nh}")

    # ── Rendering ─────────────────────────────────────────────────────────
    def _render_frame(self):
        self.canvas.delete("all")
        w = self.win.winfo_width()
        h = self.win.winfo_height()

        # Background
        self.canvas.create_rectangle(0, 0, w, h,
                                      fill=Config.BG_COLOR, outline="")

        # Top/bottom fade gradients (simulate vignette)
        fade_h = 40
        for i in range(fade_h):
            alpha_hex = format(int((1 - i/fade_h) * 180), "02x")
            color = f"#{alpha_hex}0d0d"   # approximation
        # Use a simpler approach — rectangles with stipple
        self.canvas.create_rectangle(0, 0, w, 36,
            fill=Config.BG_COLOR, stipple="gray50", outline="")
        self.canvas.create_rectangle(0, h-36, w, h,
            fill=Config.BG_COLOR, stipple="gray50", outline="")

        # Script text
        if self.script.text:
            self._draw_text(w, h)
        else:
            self.canvas.create_text(
                w//2, h//2,
                text="← Open editor and load a script →",
                fill="#333", font=(Config.FONT_FAMILY, 18),
            )

        # Status indicators
        self._draw_status(w, h)

        self.win.after(Config.SCROLL_TICK_MS, self._render_frame)

    def _draw_text(self, w, h):
        fnt = tkfont.Font(
            family=Config.FONT_FAMILY,
            size=Config.FONT_SIZE,
            weight=Config.FONT_WEIGHT,
        )
        line_h  = int(fnt.metrics("linespace") * Config.LINE_SPACING)
        pad_x   = 40
        max_w   = w - pad_x * 2

        # Word-wrap manually
        words   = self.script.text.split()
        lines   = []
        current = []
        for word in words:
            test = " ".join(current + [word])
            if fnt.measure(test) <= max_w:
                current.append(word)
            else:
                if current:
                    lines.append(" ".join(current))
                current = [word]
        if current:
            lines.append(" ".join(current))

        total_h  = len(lines) * line_h
        center_y = h // 2

        for i, line in enumerate(lines):
            y = center_y - int(self.scroll_y) + i * line_h
            if y < -line_h or y > h + line_h:
                continue
            # Highlight line nearest center
            dist = abs(y - center_y)
            if dist < line_h:
                brightness = int(255 - (dist / line_h) * 80)
                color = f"#{brightness:02x}{brightness:02x}{brightness:02x}"
            else:
                color = "#666666"

            self.canvas.create_text(
                w // 2, y,
                text=line,
                fill=color,
                font=fnt,
                anchor="center",
            )

        # Caret line at center
        self.canvas.create_rectangle(
            pad_x, center_y - 1, w - pad_x, center_y + 1,
            fill=Config.CARET_COLOR, outline="",
        )

    def _draw_status(self, w, h):
        # Pause indicator
        if self.paused:
            self.canvas.create_text(
                w - 16, 16,
                text="⏸", fill="#ff4444",
                font=(Config.FONT_FAMILY, 18), anchor="ne",
            )
        # Voice indicator
        if HAS_AUDIO and self.voice_active:
            color = "#00e5ff" if self.audio.is_speaking else "#333"
            self.canvas.create_oval(w-38, 8, w-24, 22, fill=color, outline="")

    # ── Scroll loop ───────────────────────────────────────────────────────
    def _scroll_loop(self):
        if not self.paused:
            should_scroll = True
            if self.voice_active and HAS_AUDIO:
                should_scroll = self.audio.is_speaking
            if should_scroll:
                self.scroll_y += self.scroll_speed
        self.win.after(Config.SCROLL_TICK_MS, self._scroll_loop)

    # ── Public controls ───────────────────────────────────────────────────
    def toggle_pause(self):
        self.paused = not self.paused

    def reset_scroll(self):
        self.scroll_y = 0
        self.paused   = True

    def start_countdown(self):
        self.reset_scroll()
        self._countdown(Config.COUNTDOWN_SEC)

    def _countdown(self, n):
        w = self.win.winfo_width()
        h = self.win.winfo_height()
        self.canvas.delete("countdown")
        if n > 0:
            self.canvas.create_text(
                w//2, h//2,
                text=str(n), fill="#ffd700",
                font=(Config.FONT_FAMILY, 80, "bold"),
                tags="countdown",
            )
            self.win.after(1000, lambda: self._countdown(n - 1))
        else:
            self.paused = False

    def open_editor(self):
        EditorWindow(self.root, self.script, self._on_script_loaded)

    def _on_script_loaded(self):
        self.reset_scroll()
        print(f"[INFO] Script loaded: {self.script.word_count()} words, "
              f"~{self.script.estimated_duration():.1f} min")


# ─────────────────────────────────────────────────────────────────────────────
#  APPLICATION ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────
class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()           # hide the root window — we use Toplevels

        self.script = Script()
        self.audio  = AudioEngine(Config())
        self.audio.start()

        self.prompter = PrompterWindow(self.root, self.script, self.audio)
        self.controls = ControlBar(self.root, self.prompter)

        # Attempt screen-share invisibility after windows are realized
        self.root.after(500, self.prompter.apply_screen_share_invisible)

        self._setup_global_keys()

        print("\n╔══════════════════════════════════════╗")
        print("║   AV Teleprompter  —  ready          ║")
        print("╠══════════════════════════════════════╣")
        print("║  Space / Esc  → pause / resume       ║")
        print("║  ↑ / ↓        → speed up / down      ║")
        print("║  ← / →        → scroll back / fwd    ║")
        print("║  Home         → reset to top         ║")
        print("║  Q            → quit                 ║")
        print("║  Drag window  → reposition           ║")
        print("╚══════════════════════════════════════╝\n")

    def _setup_global_keys(self):
        # Bind q to root as well for safety
        self.root.bind("<q>", lambda e: self.quit())

    def run(self):
        try:
            self.root.mainloop()
        finally:
            self.audio.stop()

    def quit(self):
        self.audio.stop()
        self.root.quit()


if __name__ == "__main__":
    app = App()
    app.run()
