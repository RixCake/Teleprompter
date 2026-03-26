# AV Teleprompter

A Python/Tkinter teleprompter for macOS — built for live event AV work.
Voice-activated scrolling, floating borderless window, screen-share invisible.

---

## Quick Start

```bash
# 1. Clone / copy this folder, then:
bash setup.sh

# 2. Activate venv and run
source .venv/bin/activate
python teleprompter.py
```

---

## Features

| Feature | Status |
|---|---|
| Floating borderless window | ✅ |
| Always-on-top | ✅ |
| Drag to reposition | ✅ |
| Resize handle | ✅ |
| Voice-activated scrolling | ✅ (sounddevice) |
| VU meter | ✅ |
| Mic sensitivity slider | ✅ |
| Manual speed control | ✅ |
| Countdown timer | ✅ |
| Built-in script editor | ✅ |
| Word count + duration estimate | ✅ |
| Screen-share invisible | ✅ (pyobjc required) |
| MIDI control | 🔜 (see roadmap) |
| Mirror/flip mode | 🔜 (see roadmap) |
| Dual display output | 🔜 (see roadmap) |

---

## Keyboard Shortcuts

| Key | Action |
|---|---|
| `Space` / `Esc` | Pause / Resume |
| `↑` / `↓` | Speed up / Slow down |
| `←` / `→` | Manual scroll back / forward |
| `Home` | Reset to top |
| `Q` | Quit |

---

## Configuration

Edit `Config` class at the top of `teleprompter.py`:

```python
class Config:
    FONT_SIZE        = 32           # text size
    SCROLL_SPEED_DEF = 1.5          # default scroll speed (px/tick)
    VOICE_THRESHOLD  = 0.015        # raise for noisy environments
    VOICE_HOLD_MS    = 600          # how long to keep scrolling after speech stops
    COUNTDOWN_SEC    = 3            # countdown before start
```

---

## Roadmap — AV Engineer Extras

### MIDI Control
Uncomment `python-rtmidi` in requirements.txt then add to `teleprompter.py`:

```python
import rtmidi

class MidiController:
    """Map MIDI CC/notes to prompter controls."""
    def __init__(self, prompter):
        self.midi_in = rtmidi.MidiIn()
        ports = self.midi_in.get_ports()
        if ports:
            self.midi_in.open_port(0)
            self.midi_in.set_callback(self._on_midi, prompter)

    def _on_midi(self, message, prompter):
        msg, _ = message
        status, note, velocity = msg
        # Note 60 = pause/resume
        if note == 60 and velocity > 0:
            prompter.toggle_pause()
        # CC 1 (mod wheel) = speed
        if status == 0xB0 and note == 1:
            speed = (velocity / 127) * Config.SCROLL_SPEED_MAX
            prompter.scroll_speed = max(Config.SCROLL_SPEED_MIN, speed)
```

### Mirror / Flip Mode (for beam-splitter rigs)
```python
# In _draw_text, transform the canvas:
self.canvas.scale("all", w/2, h/2, -1, 1)   # horizontal mirror
```

### Dual Display Output
```python
screens = self.win.winfo_screen()
# Launch a second PrompterWindow on the second display
# Pass same Script object — updates automatically
```

### File Import
```python
from tkinter import filedialog
filepath = filedialog.askopenfilename(filetypes=[("Text", "*.txt"), ("All", "*.*")])
with open(filepath) as f:
    self.script.load(f.read())
```

---

## macOS Permissions

On first run, macOS will prompt for **Microphone** access.
Grant it in: **System Settings → Privacy & Security → Microphone → Terminal (or Python)**

Without it, voice-scroll is disabled — manual scroll still works.

---

## Screen-Share Invisibility

Requires `pyobjc`. When installed, the prompter window is excluded from:
- Zoom screen share
- Google Meet / Teams / WebEx
- OBS capture
- macOS screenshots (`Cmd+Shift+3/4`)

If pyobjc is not installed, the window is visible but still floats on top.

---

## File Structure

```
teleprompter/
├── teleprompter.py     ← main application
├── requirements.txt    ← pip dependencies
├── setup.sh            ← one-time setup script
└── README.md           ← this file
```
