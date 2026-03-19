"""
AirPin — Multi-monitor AR workspace for RayNeo Air 4 Pro.

Creates virtual displays via Parsec VDD. Windows natively manages
cursor movement between monitors. Each monitor is captured via DXGI
and rendered with head-tracking offset.

Global Hotkeys (Ctrl+Alt+...):
  R          Recenter         T   Track on/off
  P          Pitch on/off     I   Invert yaw
  Left/Right Add virtual display left/right
  +/-        Zoom             0   Reset zoom
  H          HUD              Shift+F  Focus game
  Q          Quit (removes all virtual displays)
"""

import ctypes
import ctypes.wintypes
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

import sys
import os
import time
import math
import argparse

import numpy as np
import pygame
from pygame.locals import *

import config
from airpin.imu_tracker import ImuTracker
from airpin.window_capture import WindowManager
from airpin.spatial_renderer import SpatialRenderer
from airpin.smooth_follow import SmoothFollow
from airpin.hotkey_manager import HotkeyManager
from airpin.audio_router import AudioRouter
from airpin.virtual_display import VirtualDisplayManager


def main():
    parser = argparse.ArgumentParser(description="AirPin for RayNeo Air 4 Pro")
    parser.add_argument("--no-imu", action="store_true")
    parser.add_argument("--no-audio", action="store_true")
    parser.add_argument("--monitor", type=int, default=0)
    parser.add_argument("--sensitivity", type=float, default=None)
    parser.add_argument("--fps", type=int, default=None)
    args = parser.parse_args()

    if args.sensitivity is not None:
        config.HEAD_TRACKING_SENSITIVITY = args.sensitivity
    capture_fps = args.fps or config.WINDOW_CAPTURE_FPS

    # ── IMU tracker ──────────────────────────────────────────────────────
    tracker = None
    if not args.no_imu:
        print("Connecting to RayNeo Air 4 Pro...")
        tracker = ImuTracker()
        try:
            tracker.start()
            time.sleep(0.1)
            tracker.recenter()
            print("  Connected!")
        except Exception as e:
            print(f"  WARNING: IMU failed: {e}")
            tracker = None

    # ── Virtual Display Manager (Parsec VDD) ─────────────────────────────
    vdd = VirtualDisplayManager()
    print("Starting Virtual Display Manager...")
    if not vdd.start():
        print("  WARNING: Virtual displays not available. Side panels disabled.")
        vdd = None

    # ── Screen capture (DXGI — primary monitor) ──────────────────────────
    print(f"Starting screen capture (monitor {args.monitor})...")
    win_mgr = WindowManager(capture_fps=capture_fps, monitor_index=args.monitor)
    if not win_mgr.start():
        print("ERROR: Screen capture failed.")
        if vdd:
            vdd.stop()
        if tracker:
            tracker.stop()
        return

    # Wait for first frame
    print("  Waiting for first frame...")
    for _ in range(50):
        if win_mgr.slot.pixel_data is not None:
            break
        time.sleep(0.1)
    if win_mgr.slot.pixel_data is not None:
        print(f"  Got first frame: {win_mgr.slot.width}x{win_mgr.slot.height}")
    else:
        print("  WARNING: No frame captured yet, continuing anyway")

    # ── Side panel captures (background thread) ─────────────────────────
    from airpin.window_capture import WindowSlot, capture_screen
    import threading
    side_captures = {}  # vdd_index -> (info_dict, WindowSlot)
    side_capture_running = True

    def side_capture_loop():
        while side_capture_running:
            for vdd_idx, (info, slot) in list(side_captures.items()):
                result = capture_screen(info['x'], 0, info['width'], info['height'])
                if result is not None:
                    w, h, data = result
                    slot.width = w
                    slot.height = h
                    slot.pixel_data = data
                    slot.texture_dirty = True
            time.sleep(1.0 / config.WINDOW_CAPTURE_FPS)

    side_thread = threading.Thread(target=side_capture_loop, daemon=True)
    side_thread.start()

    # ── Audio ────────────────────────────────────────────────────────────
    audio = AudioRouter()
    if not args.no_audio and config.AUDIO_ENABLED:
        print("Starting audio routing...")
        if not audio.start():
            print("  Tip: Set 'SmartGlasses' as audio output in Windows Settings")

    # ── Renderer ─────────────────────────────────────────────────────────
    renderer = SpatialRenderer()
    renderer.init()

    # ── Hotkeys ──────────────────────────────────────────────────────────
    hotkeys = HotkeyManager()
    for name, (mod, key) in config.HOTKEYS.items():
        hotkeys.register(name, mod, key)

    time.sleep(0.3)
    renderer.release_focus_once()

    print("\n=== AirPin Running ===")
    print("Ctrl+Alt+...")
    print("  R        Recenter        T   Track on/off")
    print("  P        Pitch on/off    I   Invert yaw")
    print("  Left     Add display L   Right  Add display R")
    print("  +/-      Zoom            0   Zoom reset")
    print("  H        HUD            Shift+F  Focus game")
    print("  Q        Quit (removes virtual displays)")
    print()

    # ── Main loop ────────────────────────────────────────────────────────
    clock = pygame.time.Clock()
    running = True
    show_hud = True
    tracking_enabled = True
    zoom = config.ZOOM_DEFAULT
    follow = SmoothFollow()
    last_time = time.time()

    while running:
        pygame.event.pump()
        triggered = hotkeys.poll()

        if 'quit' in triggered:
            running = False
        if 'recenter' in triggered and tracker:
            tracker.recenter()
            follow.reset()
            print("  Recentered!")
        if 'toggle_tracking' in triggered:
            tracking_enabled = not tracking_enabled
            if tracking_enabled and tracker:
                tracker.recenter()
            print(f"  Tracking: {'ON' if tracking_enabled else 'OFF'}")
        if 'toggle_hud' in triggered:
            show_hud = not show_hud
        if 'invert_yaw' in triggered:
            config.INVERT_YAW = not config.INVERT_YAW
            print(f"  Yaw invert: {config.INVERT_YAW}")
        if 'focus_game' in triggered:
            renderer.release_focus_once()
        if 'zoom_in' in triggered:
            zoom = min(zoom + config.ZOOM_STEP, config.ZOOM_MAX)
        if 'zoom_out' in triggered:
            zoom = max(zoom - config.ZOOM_STEP, config.ZOOM_MIN)
        if 'zoom_reset' in triggered:
            zoom = config.ZOOM_DEFAULT
        if 'toggle_pitch' in triggered:
            config.PITCH_ENABLED = not config.PITCH_ENABLED
            print(f"  Pitch: {'ON' if config.PITCH_ENABLED else 'OFF'}")

        # ── Add virtual displays ──
        if ('panel_left' in triggered or 'panel_right' in triggered) and vdd:
            direction = 'left' if 'panel_left' in triggered else 'right'
            # Match primary monitor resolution for consistent quality
            primary_w = ctypes.windll.user32.GetSystemMetrics(0)
            primary_h = ctypes.windll.user32.GetSystemMetrics(1)
            info = vdd.add_display(primary_w, primary_h, 120, position=direction)
            if info:
                slot = WindowSlot(f"VDD-{direction}")
                side_captures[info['index']] = (info, slot)
                time.sleep(1.0)  # let Windows settle
                # Resize overlay (recreates GL context — all textures invalidated)
                renderer.reinit_size()
                # Reset all slot texture references (old GL context is dead)
                win_mgr.slot.gl_texture_id = None
                win_mgr.slot.texture_dirty = True
                for _, (_, s) in side_captures.items():
                    s.gl_texture_id = None
                    s.texture_dirty = True
                print(f"  Use Win+Shift+{'Left' if direction == 'left' else 'Right'} to move windows to it.")

        # ── Head orientation with Smooth Follow ──
        now = time.time()
        dt_ms = (now - last_time) * 1000.0
        last_time = now

        if tracker and tracking_enabled and tracker.imu_count > 0:
            raw_yaw, raw_pitch, roll = tracker.get_orientation()
            # Get gyro magnitude for movement detection
            gc = tracker._gyro_bias  # just to get the corrected gyro
            import numpy as np
            raw_gyro = np.array([0.0, 0.0, 0.0])
            if hasattr(tracker, '_last_gyro_mag'):
                gyro_mag = tracker._last_gyro_mag
            else:
                gyro_mag = 0.0
            yaw = follow.update(raw_yaw, dt_ms, gyro_mag)
            pitch = raw_pitch if config.PITCH_ENABLED else 0.0
        else:
            yaw, pitch, roll = 0.0, 0.0, 0.0

        # ── Build panel list: main + virtual displays ──
        panels_render = []
        main_slot = win_mgr.slot
        panels_render.append((0, main_slot))

        if vdd:
            gap = getattr(config, 'PANEL_GAP', 50)
            left_count = 0
            right_count = 0
            for idx, device_name, position, actual_x, actual_w, actual_h in vdd.get_displays():
                # Visual gap: increases with each panel in that direction
                # so gap exists between ALL panels, not just main<->side
                if position == 'left':
                    left_count += 1
                    offset = actual_x - gap * left_count
                else:
                    right_count += 1
                    offset = actual_x + gap * right_count

                if idx in side_captures:
                    panels_render.append((offset, side_captures[idx][1]))
                else:
                    panels_render.append((offset, main_slot))

        # ── Render all panels ──
        offsets = [p[0] for p in panels_render]
        slots = [p[1] for p in panels_render]
        renderer.render_panels(slots, offsets, yaw, pitch, zoom)

        # ── Cursor ──
        ppd_rad = renderer.primary_width / math.radians(config.FOV_HORIZONTAL_DEG)
        yaw_sign = -1.0 if config.INVERT_YAW else 1.0
        pitch_sign = -1.0 if config.INVERT_PITCH else 1.0
        cur_offset_x = yaw_sign * yaw * ppd_rad
        cur_offset_y = pitch_sign * pitch * ppd_rad
        renderer.draw_cursor(cur_offset_x, cur_offset_y, zoom)

        # ── HUD ──
        if show_hud:
            n_vdd = len(vdd.get_displays()) if vdd else 0
            renderer.draw_hud({
                'tracking': tracking_enabled,
                'pitch_enabled': config.PITCH_ENABLED,
                'zoom': zoom,
                'yaw': math.degrees(yaw),
                'pitch': math.degrees(pitch),
                'cap_w': win_mgr.capture.width,
                'cap_h': win_mgr.capture.height,
                'panels': [f"Main"] + [f"VDD-{d[2]}" for d in (vdd.get_displays() if vdd else [])],
            })

        pygame.display.flip()
        clock.tick(config.TARGET_FPS)

    # ── Cleanup (cursor first, then VDD, then everything else) ───────────
    print("\nShutting down...")
    renderer._show_system_cursor()
    side_capture_running = False
    side_captures.clear()
    if vdd:
        vdd.stop()
    hotkeys.unregister_all()
    audio.stop()
    win_mgr.stop()
    renderer.cleanup()
    if tracker:
        tracker.stop()
    pygame.quit()
    print("Done.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nCRASH: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # ALWAYS restore cursor + remove virtual displays
        try:
            ctypes.windll.user32.SystemParametersInfoW(0x0057, 0, None, 0)
        except Exception:
            pass
