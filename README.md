# AirPin

Spatial display app for **RayNeo Air** AR glasses. Pins your screen in 3D space with head tracking — turn your head and the content stays where it is.

Create a multi-monitor workspace with virtual displays — all visible through your AR glasses while using just one laptop. No external monitors needed.

> **Note:** Built for personal use, tested on one hardware setup. Expect bugs. Contributions welcome.

## What you can do

### Spatial head tracking
- Your screen is **pinned in space** — turn your head left/right and the content stays where it is
- Look back at the same spot — everything is exactly where you left it
- **No drift** — Smooth Follow algorithm masks gyroscope drift automatically
- **No jitter** — heartbeat, breathing, micro-sway filtered out

### Multi-monitor workspace (virtual displays)
- **Add virtual monitors** left or right of your main screen (`Ctrl+Alt+Left/Right`)
- Each virtual display is a **real Windows monitor** (via Parsec VDD)
- **Drag windows** between monitors normally (or `Win+Shift+Left/Right`)
- **Mouse moves natively** between all monitors — no hacks, Windows handles it
- Turn your head to see side monitors through the glasses
- Works with RDP sessions — connect 3 laptops, put each on a virtual display

### Transparent overlay
- The app is **invisible** to your game/desktop — doesn't interfere with anything
- **Mouse clicks pass through** to your game (WS_EX_LAYERED + WS_EX_TRANSPARENT)
- **Keyboard focus stays** with your game — hotkeys work globally
- Custom cursor that moves correctly with zoomed/shifted content
- **Not captured** by screen recording or screenshots (WDA_EXCLUDEFROMCAPTURE)

### Zoom
- **Zoom in/out** (`Ctrl+Alt++/-`) — magnify content from 50% to 300%
- Cursor position adjusts automatically with zoom level

### Audio routing
- Routes system audio to glasses speaker (SmartGlasses via WASAPI)

## Compatibility

| Device | Status |
|--------|--------|
| **RayNeo Air 4 Pro** | Tested, fully working |
| **RayNeo Air 3s Pro** | Should work (same USB protocol and SDK) |
| **RayNeo Air 3s** | Should work (same SDK) |
| **Other RayNeo Air** | Not tested, may need VID/PID change in config.py |
| **XREAL / Rokid / other** | Not supported (different SDK) |

## Installation

### Prerequisites

- Windows 10/11
- RayNeo Air glasses connected via USB-C
- [Parsec VDD](https://github.com/nomi-san/parsec-vdd) installed (for virtual displays)
- Python 3.10+

### Setup

```bash
git clone <repo-url>
cd AirPin
pip install -r requirements.txt
python main.py
```

The repo includes `RayNeoSDK.dll` and `libusb-1.0.dll` — no additional SDK setup needed.

## Controls

All hotkeys are global — work while your game has focus.

| Hotkey | Action |
|--------|--------|
| `Ctrl+Alt+R` | Recenter head tracking |
| `Ctrl+Alt+T` | Toggle yaw tracking on/off |
| `Ctrl+Alt+P` | Toggle pitch tracking on/off |
| `Ctrl+Alt+Left` | Add virtual display LEFT (captures focused window) |
| `Ctrl+Alt+Right` | Add virtual display RIGHT |
| `Ctrl+Alt++` | Zoom in |
| `Ctrl+Alt+-` | Zoom out |
| `Ctrl+Alt+0` | Reset zoom to 100% |
| `Ctrl+Alt+I` | Invert yaw direction |
| `Ctrl+Alt+H` | Toggle HUD overlay |
| `Ctrl+Alt+Shift+F` | Give keyboard focus to game |
| `Ctrl+Alt+Q` | Quit (auto-removes virtual displays) |

### Adding virtual displays

1. **Click on the window** you want on the side display (give it focus)
2. Press `Ctrl+Alt+Left` or `Ctrl+Alt+Right`
3. A virtual monitor appears — the focused window moves to it
4. **Turn your head** to see the side display
5. Use `Win+Shift+Left/Right` to move other windows between monitors
6. Mouse moves between monitors naturally (Windows handles it)

## How it works

```
Your laptop screen
    │
    │ BitBlt screen capture (120 FPS)
    │ (overlay excluded via WDA_EXCLUDEFROMCAPTURE)
    ▼
┌─────────────────────────────────────────────────┐
│                    AirPin                       │
│                                                 │
│  RayNeo IMU ──► Smooth Follow ──► Pixel offset  │
│  (500 Hz)       (hysteresis)     (1:1 mapping)  │
│                                                 │
│  Fullscreen transparent overlay:                │
│  • Mouse/keyboard pass through to game          │
│  • Custom cursor shifts with content            │
│  • Invisible to screenshots/recordings          │
│                                                 │
│  Virtual displays (Parsec VDD):                 │
│  • Real Windows monitors via IOCTL              │
│  • Same resolution as primary (120Hz)           │
│  • Mouse moves natively between them            │
│  • Auto-removed on exit                         │
└─────────────────────────────────────────────────┘
    │
    ▼
Glasses (duplicate mode) show the spatial view
```

### Head tracking details

- **Complementary filter**: gyro (99.9%) + accel (0.1%) for orientation
- **Smooth Follow**: start tracking at >3°/s, stop at <0.9°/s after 15 frames
- **No calibration needed** — works immediately on startup
- **Drift masked** by Smooth Follow (output frozen when still)
- `Ctrl+Alt+R` to recenter if drift accumulates

## Command-line options

```
python main.py [options]

  --no-imu          Run without head tracking
  --no-audio        Disable audio routing
  --monitor N       Capture monitor N (default: 0)
  --sensitivity F   Head tracking multiplier (default: 1.0)
  --fps N           Capture FPS (default: 120)
```

## Project structure

```
AirPin/
├── main.py                  # Entry point, render loop
├── config.py                # All settings
├── airpin/                  # Core modules
│   ├── imu_tracker.py       #   RayNeoSDK → gyro/accel → orientation
│   ├── smooth_follow.py     #   Movement detection, drift masking
│   ├── spatial_renderer.py  #   OpenGL overlay, panels, HUD, cursor
│   ├── window_capture.py    #   BitBlt screen capture
│   ├── virtual_display.py   #   Parsec VDD virtual monitors
│   ├── panel_manager.py     #   Side panel capture and layout
│   ├── hotkey_manager.py    #   Global hotkeys (GetAsyncKeyState)
│   └── audio_router.py      #   WASAPI audio to glasses
├── lib/                     # Runtime DLLs
│   ├── RayNeoSDK.dll        #   IMU SDK (from verncat/RayNeo-Air-3S-Pro-OpenVR)
│   └── libusb-1.0.dll       #   USB communication
└── tests/                   # Test scripts
```

## Known limitations

- **Duplicate mode only** — glasses mirror the laptop screen (not detected as separate display)
- **Yaw drift** — no magnetometer. Smooth Follow masks it, `Ctrl+Alt+R` to recenter
- **Pitch tracking off by default** — enabling it causes cursor position mismatch
- **BitBlt capture** — may not capture exclusive fullscreen games. Use borderless windowed
- **Audio** — needs manual audio output switch to SmartGlasses in some cases

## Tested setup

| Component | Details |
|-----------|---------|
| Glasses | RayNeo Air 4 Pro (board_id 0x3A, firmware Jan 2026) |
| Laptop | Lenovo Legion, RTX 5080, 2560x1600 |
| OS | Windows 11 Pro 26200 |
| Connection | USB-C (DisplayPort Alt Mode + USB HID) |
| Virtual displays | Parsec Virtual Display Adapter v0.45 |
| Python | 3.14 |

## License

Personal use. No warranty. Use at your own risk.

## Credits

- [RayNeo-Air-3S-Pro-OpenVR](https://github.com/verncat/RayNeo-Air-3S-Pro-OpenVR) — RayNeoSDK
- [Parsec VDD](https://github.com/nomi-san/parsec-vdd) — Virtual display driver
- [Breezy Desktop](https://github.com/wheaney/breezy-desktop) — Smooth Follow algorithm reference
- Built with [Claude Code](https://claude.ai/claude-code) (Anthropic)
