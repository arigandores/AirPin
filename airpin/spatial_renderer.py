"""
Fullscreen overlay renderer for duplicate-mode AR glasses.
- Excluded from DXGI capture (no feedback loop)
- WS_EX_LAYERED + WS_EX_TRANSPARENT + DWM = true mouse passthrough
- Orthographic 1:1 rendering for maximum quality
- Head tracking shifts the image in pixels
"""

import os
import math
import ctypes
import numpy as np

import pygame
from pygame.locals import *
from OpenGL.GL import *
from OpenGL.GLU import *
import win32gui
import win32con

import config

user32 = ctypes.windll.user32
WDA_EXCLUDEFROMCAPTURE = 0x00000011


class SpatialRenderer:
    """Fullscreen overlay with orthographic rendering and mouse passthrough."""

    def __init__(self):
        self.textures = {}
        self._tex_sizes = {}
        self._hud_font = None
        self._hud_tex = None
        self._cursor_tex = None
        self._hwnd = None
        self._initialized = False
        self._cursor_hidden = False
        # Use virtual screen (covers ALL monitors)
        self.virt_x = user32.GetSystemMetrics(76)  # SM_XVIRTUALSCREEN
        self.virt_y = user32.GetSystemMetrics(77)  # SM_YVIRTUALSCREEN
        self.width = user32.GetSystemMetrics(78) or user32.GetSystemMetrics(0)   # SM_CXVIRTUALSCREEN
        self.height = user32.GetSystemMetrics(79) or user32.GetSystemMetrics(1)  # SM_CYVIRTUALSCREEN
        self.primary_width = user32.GetSystemMetrics(0)

    def reinit_size(self):
        """Recreate overlay to cover the current virtual desktop."""
        new_x = user32.GetSystemMetrics(76)
        new_y = user32.GetSystemMetrics(77)
        new_w = user32.GetSystemMetrics(78) or user32.GetSystemMetrics(0)
        new_h = user32.GetSystemMetrics(79) or user32.GetSystemMetrics(1)
        if new_w == self.width and new_h == self.height and new_x == self.virt_x:
            return

        self.virt_x = new_x
        self.virt_y = new_y
        self.width = new_w
        self.height = new_h

        # Recreate pygame display at new size (OpenGL context is recreated)
        os.environ['SDL_VIDEO_WINDOW_POS'] = f'{self.virt_x},{self.virt_y}'
        flags = DOUBLEBUF | OPENGL | NOFRAME
        pygame.display.set_mode((self.width, self.height), flags)

        wm_info = pygame.display.get_wm_info()
        hwnd = wm_info.get('window')
        self._hwnd = hwnd

        if hwnd:
            user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
            ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            ex_style |= (win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT |
                         win32con.WS_EX_NOACTIVATE | win32con.WS_EX_TOOLWINDOW |
                         win32con.WS_EX_TOPMOST)
            win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, ex_style)

            class MARGINS(ctypes.Structure):
                _fields_ = [('left', ctypes.c_int), ('right', ctypes.c_int),
                            ('top', ctypes.c_int), ('bottom', ctypes.c_int)]
            margins = MARGINS(-1, -1, -1, -1)
            ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins))

            win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST,
                                  self.virt_x, self.virt_y, self.width, self.height,
                                  win32con.SWP_NOACTIVATE | win32con.SWP_SHOWWINDOW)

        self._setup_gl()
        # Invalidate all textures (GL context was recreated)
        self.invalidate_textures()
        self._hud_font = pygame.font.SysFont("segoeui", 18)
        self._hud_font_big = pygame.font.SysFont("segoeui", 24, bold=True)
        self._hud_tex = glGenTextures(1)
        self._cursor_tex = self._create_cursor_texture()
        self._hide_system_cursor()
        print(f"  Overlay resized: {self.width}x{self.height} at ({self.virt_x},{self.virt_y})")

    def init(self):
        os.environ['SDL_VIDEO_WINDOW_POS'] = f'{self.virt_x},{self.virt_y}'
        pygame.init()
        pygame.display.set_caption("AirPin")

        flags = DOUBLEBUF | OPENGL | NOFRAME
        pygame.display.set_mode((self.width, self.height), flags)

        wm_info = pygame.display.get_wm_info()
        hwnd = wm_info.get('window')
        self._hwnd = hwnd

        if hwnd:
            # 1. Invisible to DXGI capture (no feedback loop)
            user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)

            # 2. LAYERED + TRANSPARENT = real mouse passthrough
            #    LAYERED is required for TRANSPARENT to affect mouse input
            ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            ex_style |= (win32con.WS_EX_LAYERED |
                         win32con.WS_EX_TRANSPARENT |
                         win32con.WS_EX_NOACTIVATE |
                         win32con.WS_EX_TOOLWINDOW |
                         win32con.WS_EX_TOPMOST)
            win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, ex_style)

            # 3. DWM compositing: allows OpenGL to render through LAYERED window
            class MARGINS(ctypes.Structure):
                _fields_ = [('left', ctypes.c_int), ('right', ctypes.c_int),
                            ('top', ctypes.c_int), ('bottom', ctypes.c_int)]
            margins = MARGINS(-1, -1, -1, -1)
            ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins))

            # 4. Stay on top of everything
            win32gui.SetWindowPos(
                hwnd, win32con.HWND_TOPMOST,
                0, 0, self.width, self.height,
                win32con.SWP_NOACTIVATE | win32con.SWP_SHOWWINDOW
            )

        self._setup_gl()
        self._hud_font = pygame.font.SysFont("segoeui", 18)
        self._hud_font_big = pygame.font.SysFont("segoeui", 24, bold=True)
        self._hud_tex = glGenTextures(1)
        self._cursor_tex = self._create_cursor_texture()
        self._initialized = True

        # Hide the system cursor — we render our own shifted with content
        self._hide_system_cursor()
        print(f"  Overlay: {self.width}x{self.height}, LAYERED+TRANSPARENT, custom cursor")

    def _setup_gl(self):
        glEnable(GL_TEXTURE_2D)
        glDisable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glClearColor(0.0, 0.0, 0.0, 1.0)

        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glOrtho(self.virt_x, self.virt_x + self.width,
                self.virt_y + self.height, self.virt_y, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        glViewport(0, 0, self.width, self.height)

    def _create_cursor_texture(self):
        """Create a simple arrow cursor as a GL texture."""
        size = 24
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        surf.fill((0, 0, 0, 0))
        # White arrow with black outline
        points = [(0, 0), (0, 20), (5, 15), (9, 22), (12, 21), (8, 14), (14, 14)]
        pygame.draw.polygon(surf, (0, 0, 0), points)  # outline
        inner = [(1, 2), (1, 18), (5, 14), (9, 20), (11, 19), (7, 13), (12, 13)]
        pygame.draw.polygon(surf, (255, 255, 255), inner)  # fill
        data = pygame.image.tostring(surf, "RGBA", True)
        tex = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, tex)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, size, size, 0,
                     GL_RGBA, GL_UNSIGNED_BYTE, data)
        return tex

    def _hide_system_cursor(self):
        """Replace all system cursors with blank ones (system-wide)."""
        # Create a 1x1 blank cursor
        and_mask = (ctypes.c_ubyte * 1)(0xFF)
        xor_mask = (ctypes.c_ubyte * 1)(0x00)
        blank = user32.CreateCursor(None, 0, 0, 1, 1, and_mask, xor_mask)
        if not blank:
            return

        # Replace all standard cursor types with blank
        # OCR_ constants for SetSystemCursor
        cursor_ids = [
            32512,  # OCR_NORMAL (arrow)
            32513,  # OCR_IBEAM (text)
            32514,  # OCR_WAIT (hourglass)
            32515,  # OCR_CROSS
            32516,  # OCR_UP
            32642,  # OCR_SIZENWSE
            32643,  # OCR_SIZENESW
            32644,  # OCR_SIZEWE
            32645,  # OCR_SIZENS
            32646,  # OCR_SIZEALL
            32648,  # OCR_NO
            32649,  # OCR_HAND
            32650,  # OCR_APPSTARTING
        ]
        for cid in cursor_ids:
            # CopyImage to create a copy (SetSystemCursor destroys the handle)
            copy = user32.CopyImage(blank, 2, 0, 0, 0)  # IMAGE_CURSOR=2
            if copy:
                user32.SetSystemCursor(copy, cid)

        user32.DestroyCursor(blank)
        self._cursor_hidden = True

    def _show_system_cursor(self):
        """Restore all system cursors to defaults."""
        if self._cursor_hidden:
            # SPI_SETCURSORS reloads all system cursors from registry
            user32.SystemParametersInfoW(0x0057, 0, None, 0)  # SPI_SETCURSORS
            self._cursor_hidden = False

    def draw_cursor(self, offset_x, offset_y, zoom=1.0):
        """Draw cursor at correct visual position (legacy single-panel API)."""
        pt = ctypes.wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        cx = pt.x * zoom + self.width * (1 - zoom) * 0.5 + offset_x
        cy = pt.y * zoom + self.height * (1 - zoom) * 0.5 + offset_y
        self.draw_cursor_at(cx, cy)

    def draw_cursor_at(self, cx, cy):
        """Draw the cursor sprite at the given screen coordinates."""
        glEnable(GL_TEXTURE_2D)
        glEnable(GL_BLEND)
        glBindTexture(GL_TEXTURE_2D, self._cursor_tex)
        glColor4f(1, 1, 1, 1)
        s = 24
        glBegin(GL_QUADS)
        glTexCoord2f(0, 1); glVertex2f(cx, cy)
        glTexCoord2f(1, 1); glVertex2f(cx + s, cy)
        glTexCoord2f(1, 0); glVertex2f(cx + s, cy + s)
        glTexCoord2f(0, 0); glVertex2f(cx, cy + s)
        glEnd()

    def update_texture(self, slot):
        if slot.pixel_data is None or not slot.texture_dirty:
            return
        data = slot.pixel_data
        if data is None:
            return
        h, w = data.shape[:2]

        slot_id = id(slot)
        if slot_id not in self.textures:
            tex_id = glGenTextures(1)
            self.textures[slot_id] = tex_id
        else:
            tex_id = self.textures[slot_id]

        glBindTexture(GL_TEXTURE_2D, tex_id)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)

        prev_size = self._tex_sizes.get(slot_id)
        if prev_size == (w, h):
            glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, w, h,
                            GL_BGRA, GL_UNSIGNED_BYTE, data)
        else:
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, w, h, 0,
                         GL_BGRA, GL_UNSIGNED_BYTE, data)
            self._tex_sizes[slot_id] = (w, h)

        slot.gl_texture_id = tex_id
        slot.texture_dirty = False

    def render_panels(self, panels, panel_offsets, head_yaw, head_pitch, zoom=1.0):
        """
        Render multiple panels arranged horizontally.
        panels: list of Panel objects (from panel_manager)
        panel_offsets: list of x pixel offsets for each panel
        """
        glClear(GL_COLOR_BUFFER_BIT)
        glLoadIdentity()

        ppd_rad = self.primary_width / math.radians(config.FOV_HORIZONTAL_DEG)
        yaw_sign = -1.0 if config.INVERT_YAW else 1.0
        pitch_sign = -1.0 if config.INVERT_PITCH else 1.0
        head_offset_x = yaw_sign * head_yaw * ppd_rad
        head_offset_y = pitch_sign * head_pitch * ppd_rad

        for panel, panel_x_offset in zip(panels, panel_offsets):
            if panel.pixel_data is None:
                continue
            self.update_texture(panel)
            if panel.gl_texture_id is None:
                continue

            data = panel.pixel_data
            if data is None:
                continue

            # Panel size from actual captured data (not virtual desktop size)
            tex_h, tex_w = data.shape[:2]
            sw = float(tex_w) * zoom
            sh = float(tex_h) * zoom

            # Position: panel_x_offset is the real Windows x coordinate
            # Head tracking shifts everything relative to primary monitor center
            primary_cx = float(self.primary_width) * 0.5
            primary_cy = float(user32.GetSystemMetrics(1)) * 0.5
            x = panel_x_offset * zoom + head_offset_x + primary_cx * (1 - zoom)
            y = head_offset_y + primary_cy - sh * 0.5

            glEnable(GL_TEXTURE_2D)
            glBindTexture(GL_TEXTURE_2D, panel.gl_texture_id)
            glColor4f(1.0, 1.0, 1.0, 1.0)

            glBegin(GL_QUADS)
            glTexCoord2f(0, 0); glVertex2f(x, y)
            glTexCoord2f(1, 0); glVertex2f(x + sw, y)
            glTexCoord2f(1, 1); glVertex2f(x + sw, y + sh)
            glTexCoord2f(0, 1); glVertex2f(x, y + sh)
            glEnd()

    def draw_hud(self, hud_data):
        """
        Draw a clean, readable HUD panel.
        hud_data: dict with keys like 'tracking', 'zoom', 'yaw', 'pitch', 'fps', etc.
        """
        if not hud_data:
            return

        pad = 16
        font_big = self._hud_font_big
        font_sm = self._hud_font

        # Build HUD surface
        hud_w = 560
        hud_h = 200
        s = pygame.Surface((hud_w, hud_h), pygame.SRCALPHA)

        # Background: rounded-ish dark panel
        s.fill((0, 0, 0, 0))
        pygame.draw.rect(s, (15, 15, 25, 200), (0, 0, hud_w, hud_h), border_radius=12)
        pygame.draw.rect(s, (60, 130, 220, 100), (0, 0, hud_w, hud_h), width=2, border_radius=12)

        y = pad

        # Title bar
        title = "AirPin"
        ts = font_big.render(title, True, (100, 180, 255))
        s.blit(ts, (pad, y))

        # Status pills
        pills = []
        track_on = hud_data.get('tracking', False)
        pills.append(("YAW " + ("ON" if track_on else "OFF"),
                       (40, 180, 80) if track_on else (180, 60, 60)))
        pitch_on = hud_data.get('pitch_enabled', False)
        pills.append(("PITCH " + ("ON" if pitch_on else "OFF"),
                       (40, 160, 80) if pitch_on else (100, 100, 100)))

        px = hud_w - pad
        for pill_text, pill_color in reversed(pills):
            pill_surf = font_sm.render(pill_text, True, (255, 255, 255))
            pw, ph = pill_surf.get_size()
            px -= pw + 16
            pygame.draw.rect(s, pill_color, (px - 2, y + 2, pw + 8, ph + 4), border_radius=8)
            s.blit(pill_surf, (px + 2, y + 4))
        y += 36

        # Separator
        pygame.draw.line(s, (60, 80, 120, 80), (pad, y), (hud_w - pad, y))
        y += 10

        # Info rows
        zoom = hud_data.get('zoom', 1.0)
        yaw_deg = hud_data.get('yaw', 0.0)
        pitch_deg = hud_data.get('pitch', 0.0)
        cap_w = hud_data.get('cap_w', 0)
        cap_h = hud_data.get('cap_h', 0)

        panel_names = hud_data.get('panels', [])

        rows = [
            (f"Zoom: {zoom:.0%}   Panels: {len(panel_names)}", (200, 220, 255)),
            (f"Yaw: {yaw_deg:+6.1f}    Pitch: {pitch_deg:+6.1f}", (170, 200, 230)),
        ]
        if len(panel_names) > 1:
            panels_str = " | ".join(panel_names)
            rows.append((f"[{panels_str}]", (160, 180, 200)))
        for text, color in rows:
            ts = font_sm.render(text, True, color)
            s.blit(ts, (pad, y))
            y += 24

        # Hotkeys row
        y += 4
        keys = [
            ("R", "Recenter"),
            ("T", "Track"),
            ("P", "Pitch"),
            ("+/-", "Zoom"),
            ("H", "HUD"),
        ]
        x = pad
        for key, label in keys:
            # Key badge
            badge = font_sm.render(key, True, (200, 200, 200))
            bw, bh = badge.get_size()
            pygame.draw.rect(s, (40, 50, 70, 180), (x - 2, y, bw + 6, bh + 4), border_radius=4)
            s.blit(badge, (x + 1, y + 2))
            x += bw + 12

        # Upload to GL
        data = pygame.image.tostring(s, "RGBA", True)
        glBindTexture(GL_TEXTURE_2D, self._hud_tex)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, hud_w, hud_h, 0,
                     GL_RGBA, GL_UNSIGNED_BYTE, data)
        glEnable(GL_TEXTURE_2D)
        glEnable(GL_BLEND)
        glColor4f(1, 1, 1, 1)

        # Position: top-left with margin
        margin = 20
        glBegin(GL_QUADS)
        glTexCoord2f(0, 1); glVertex2f(margin, margin)
        glTexCoord2f(1, 1); glVertex2f(margin + hud_w, margin)
        glTexCoord2f(1, 0); glVertex2f(margin + hud_w, margin + hud_h)
        glTexCoord2f(0, 0); glVertex2f(margin, margin + hud_h)
        glEnd()

    def release_focus_once(self):
        """Give focus to the largest visible window (the game)."""
        if not self._hwnd:
            return
        try:
            best_hwnd = None
            best_area = 0
            def _enum_cb(hwnd, _):
                nonlocal best_hwnd, best_area
                if hwnd == self._hwnd:
                    return True
                if not win32gui.IsWindowVisible(hwnd):
                    return True
                if win32gui.GetWindowTextLength(hwnd) == 0:
                    return True
                r = win32gui.GetWindowRect(hwnd)
                w, h = r[2] - r[0], r[3] - r[1]
                area = w * h
                if area > best_area and w > 200 and h > 200:
                    best_area = area
                    best_hwnd = hwnd
                return True
            win32gui.EnumWindows(_enum_cb, None)
            if best_hwnd:
                title = win32gui.GetWindowText(best_hwnd)
                print(f"  Focus -> {title[:50]}")
                win32gui.SetForegroundWindow(best_hwnd)
        except Exception as e:
            print(f"  Focus release failed: {e}")

    def invalidate_textures(self):
        for tex_id in self.textures.values():
            try:
                glDeleteTextures([tex_id])
            except Exception:
                pass
        self.textures.clear()
        self._tex_sizes.clear()
        self._hud_tex = glGenTextures(1)

    def remove_texture(self, slot):
        slot_id = id(slot)
        if slot_id in self.textures:
            try:
                glDeleteTextures([self.textures[slot_id]])
            except Exception:
                pass
            del self.textures[slot_id]
        self._tex_sizes.pop(slot_id, None)

    def cleanup(self):
        self._show_system_cursor()
        for tex_id in self.textures.values():
            try:
                glDeleteTextures([tex_id])
            except Exception:
                pass
        self.textures.clear()
        self._tex_sizes.clear()
        if self._hud_tex is not None:
            try:
                glDeleteTextures([self._hud_tex])
            except Exception:
                pass
        self._hud_tex = None
        self._hud_font = None
        self._initialized = False
