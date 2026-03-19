# AirPin v1.0 — AR Spatial Display for RayNeo Air 4 Pro

## What this project does

Pins the desktop screen in 3D space for RayNeo Air 4 Pro AR glasses.
Works in **duplicate mode** (glasses mirror the laptop screen).
The app captures the screen via DXGI, applies head-tracking offset, and renders
a fullscreen overlay that is invisible to screen capture and transparent to mouse input.

## Architecture

```
Monitor (game/desktop)
    │
    │ DXGI Desktop Duplication (GPU-level capture)
    │ Our overlay window is EXCLUDED from capture (WDA_EXCLUDEFROMCAPTURE)
    ▼
┌──────────────┐      ┌──────────────┐
│ window_      │      │ imu_tracker  │
│ capture.py   │      │ .py          │
│              │      │              │
│ dxcam grabs  │      │ RayNeoSDK    │
│ screen BGRA  │      │ → gyro/accel │
│ at 120 FPS   │      │ → comp.filter│
│              │      │ → yaw/pitch  │
└──────┬───────┘      └──────┬───────┘
       │                     │
       ▼                     ▼
┌─────────────────────────────────────┐
│ spatial_renderer.py                 │
│                                     │
│ Fullscreen TOPMOST overlay:         │
│ • WS_EX_LAYERED + TRANSPARENT      │
│   (mouse passes through to game)   │
│ • DwmExtendFrameIntoClientArea     │
│   (OpenGL works with LAYERED)      │
│ • WDA_EXCLUDEFROMCAPTURE           │
│   (DXGI doesn't see our window)    │
│                                     │
│ Renders: BGRA texture + pixel      │
│ offset from head tracking           │
│ Orthographic 1:1 projection        │
└─────────────────────────────────────┘
       │
       ▼
Glasses (duplicate mode) see the shifted image
```

## File responsibilities

| File | Purpose |
|------|---------|
| `main.py` | Entry point. DPI awareness, init all systems, main render loop, hotkey dispatch |
| `config.py` | All settings: FOV, FPS, hotkeys, zoom limits, IMU params, audio device name |
| `imu_tracker.py` | Connects to RayNeo Air 4 Pro via RayNeoSDK.dll (USB HID). Reads gyro/accel at 500Hz. Complementary filter → yaw/pitch/roll. EMA smoothing. Bias calibration at startup |
| `spatial_renderer.py` | Creates fullscreen overlay window with LAYERED+TRANSPARENT+TOPMOST+EXCLUDEFROMCAPTURE. Orthographic OpenGL rendering. Uploads BGRA textures directly (no copy). Draws HUD panel |
| `window_capture.py` | DXGI Desktop Duplication via dxcam. Captures entire monitor at native resolution. Returns BGRA numpy arrays. Background thread |
| `hotkey_manager.py` | Polls keyboard via GetAsyncKeyState. Works regardless of focus. No message queue dependency |
| `audio_router.py` | Routes system audio to glasses via sounddevice (WASAPI). Finds "SmartGlasses" output device |
| `requirements.txt` | Python dependencies |
| `.gitignore` | Excludes DLLs, pycache |

## Key technical decisions

### Why DXGI instead of PrintWindow?
PrintWindow uses GDI — can't capture DirectX/Vulkan games (black screen).
DXGI Desktop Duplication captures at GPU level — works with everything.

### Why WS_EX_LAYERED + WS_EX_TRANSPARENT?
WS_EX_TRANSPARENT alone doesn't fully pass mouse input on all configs.
WS_EX_LAYERED is required for WS_EX_TRANSPARENT to affect mouse hit testing.
DwmExtendFrameIntoClientArea makes OpenGL work with LAYERED windows.

### Why orthographic instead of perspective?
Perspective projection distorts pixels (quality loss).
Orthographic gives 1:1 pixel mapping — maximum quality.
Head tracking = pixel offset, not 3D rotation.

### Why complementary filter instead of Madgwick?
Simpler, fewer axis-mapping bugs.
Accel corrects pitch/roll drift (gravity reference).
Yaw has no absolute reference (no magnetometer) — only gyro integration.
Deadzone + bias calibration handle drift.

### Why GL_BGRA?
dxcam returns BGRA natively. Passing BGRA directly to OpenGL avoids
an 8MB/frame copy + channel swap.

### Why pitch is disabled by default?
Head tracking shifts the rendered image, but mouse clicks go to REAL screen
coordinates. Vertical shift (pitch) causes cursor-to-button mismatch.
Horizontal shift (yaw) is less noticeable. All pro AR apps (Nebula, INAIR)
track only yaw by default.

## Runtime dependencies (not in git)

These DLLs must be in the project directory:
- `RayNeoSDK.dll` — from https://github.com/verncat/RayNeo-Air-3S-Pro-OpenVR
- `libusb-1.0.dll` — bundled with the SDK above

Source: `C:\Users\seval\OneDrive\Desktop\package\bin\RayNeoSDK.dll`
Source: `C:\Users\seval\OneDrive\Desktop\package\examples\libusb-1.0.dll`

## IMU protocol

RayNeo Air 4 Pro (board_id=0x3A) communicates over USB HID:
- VID=0x1BBB PID=0xAF50
- Single HID interface (interface 0), endpoints 0x01 OUT + 0x81 IN
- 64-byte frames. Send magic=0x66, receive magic=0x99
- IMU data type=0x65: 3x float acc, 3x float gyro, temp, magnet, tick
- Command ack type=0xC8
- Device axes: X=right, Y=up (gravity), Z=forward

## Config parameters that matter

| Parameter | Default | What it does |
|-----------|---------|-------------|
| `FOV_HORIZONTAL_DEG` | 46.0 | Glasses FOV. Controls pixels-per-degree mapping |
| `GYRO_DEADZONE` | 0.015 rad/s | Below this, gyro reading is zeroed (anti-jitter) |
| `EMA_ALPHA` | 0.035 | Smoothing at 500Hz. Higher = more responsive, more jitter |
| `YAW_DECAY` | 1.0 | 1.0 = no decay (true spatial pin). <1.0 = returns to center |
| `INVERT_YAW` | False | Flip yaw direction if tracking feels inverted |
| `PITCH_ENABLED` | False | Enable pitch tracking (causes cursor offset bug) |
| `ZOOM_DEFAULT` | 1.0 | Initial zoom level |

## Hotkeys (all Ctrl+Alt+...)

| Key | Action |
|-----|--------|
| R | Recenter head tracking |
| T | Toggle yaw tracking on/off |
| P | Toggle pitch tracking on/off |
| +/- | Zoom in/out (10% steps) |
| 0 | Reset zoom to 100% |
| H | Toggle HUD |
| I | Invert yaw direction |
| Shift+F | Give keyboard focus to game |
| Q | Quit |

## Known limitations

1. **Duplicate mode only** — glasses don't appear as separate display
2. **Cursor offset with pitch** — pitch tracking shifts image but not cursor
3. **Yaw drift** — no magnetometer reference. Use Ctrl+Alt+R to recenter
4. **Audio** — needs WASAPI loopback device or manual audio output switch
5. **Game must be borderless windowed** — exclusive fullscreen may not capture
