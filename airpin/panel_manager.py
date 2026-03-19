"""
Multi-panel virtual workspace.
Each panel captures a window and is positioned at a yaw offset.
Head tracking scrolls through panels. Mouse works on the visible panel.
"""

import ctypes
import ctypes.wintypes
import threading
import time
import numpy as np

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

SRCCOPY = 0x00CC0020
BI_RGB = 0
DIB_RGB_COLORS = 0
PW_RENDERFULLCONTENT = 0x00000002


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", ctypes.wintypes.DWORD), ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long), ("biPlanes", ctypes.wintypes.WORD),
        ("biBitCount", ctypes.wintypes.WORD), ("biCompression", ctypes.wintypes.DWORD),
        ("biSizeImage", ctypes.wintypes.DWORD), ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", ctypes.wintypes.DWORD),
        ("biClrImportant", ctypes.wintypes.DWORD),
    ]

class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER)]

class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


def capture_region_bgra(x, y, w, h):
    """Capture a screen region as BGRA numpy array. Returns (w, h, data) or None."""
    try:
        if w <= 0 or h <= 0:
            return None
        hwnd_dc = user32.GetDC(None)
        mem_dc = gdi32.CreateCompatibleDC(hwnd_dc)
        bitmap = gdi32.CreateCompatibleBitmap(hwnd_dc, w, h)
        old_bmp = gdi32.SelectObject(mem_dc, bitmap)

        gdi32.BitBlt(mem_dc, 0, 0, w, h, hwnd_dc, x, y, SRCCOPY)

        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = w
        bmi.bmiHeader.biHeight = -h
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = BI_RGB
        buf = ctypes.create_string_buffer(w * h * 4)
        gdi32.GetDIBits(mem_dc, bitmap, 0, h, buf, ctypes.byref(bmi), DIB_RGB_COLORS)

        gdi32.SelectObject(mem_dc, old_bmp)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(None, hwnd_dc)

        data = np.frombuffer(buf.raw, dtype=np.uint8).reshape(h, w, 4).copy()
        return w, h, data
    except Exception:
        return None


def capture_window_bgra(hwnd):
    """Capture a window as BGRA numpy array. Returns (w, h, data) or None."""
    try:
        if not user32.IsWindow(hwnd):
            return None
        rect = RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        w = rect.right - rect.left
        h = rect.bottom - rect.top
        if w <= 0 or h <= 0:
            return None

        # Use BitBlt instead of PrintWindow to avoid deadlocks.
        # PrintWindow sends WM_PRINT to the target window and waits for
        # a response — if that window's message pump is blocked, we deadlock.
        # BitBlt copies directly from the screen DC (no message sending).
        hwnd_dc = user32.GetDC(None)
        mem_dc = gdi32.CreateCompatibleDC(hwnd_dc)
        bitmap = gdi32.CreateCompatibleBitmap(hwnd_dc, w, h)
        old_bmp = gdi32.SelectObject(mem_dc, bitmap)

        src_dc = user32.GetDC(None)
        gdi32.BitBlt(mem_dc, 0, 0, w, h, src_dc,
                     rect.left, rect.top, SRCCOPY)
        user32.ReleaseDC(None, src_dc)

        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = w
        bmi.bmiHeader.biHeight = -h
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = BI_RGB
        buf = ctypes.create_string_buffer(w * h * 4)
        gdi32.GetDIBits(mem_dc, bitmap, 0, h, buf, ctypes.byref(bmi), DIB_RGB_COLORS)

        gdi32.SelectObject(mem_dc, old_bmp)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(None, hwnd_dc)

        data = np.frombuffer(buf.raw, dtype=np.uint8).reshape(h, w, 4).copy()
        return w, h, data
    except Exception:
        return None


class Panel:
    """A single panel in the virtual workspace."""

    def __init__(self, title, hwnd=None, is_main=False):
        self.title = title
        self.hwnd = hwnd
        self.is_main = is_main  # True = DXGI capture (managed externally)
        self.width = 0
        self.height = 0
        self.pixel_data = None
        self.texture_dirty = True
        self.gl_texture_id = None

    def update_capture(self):
        """Re-capture this panel's window. Only for non-main panels."""
        if self.is_main:
            return  # main panel updated by WindowManager
        if self.hwnd is None:
            return
        result = capture_window_bgra(self.hwnd)
        if result is None:
            return
        self.width, self.height, self.pixel_data = result
        self.texture_dirty = True


class PanelManager:
    """
    Manages multiple panels arranged horizontally.
    Panel 0 = main screen (center). Negative indices = left, positive = right.
    Also tracks a virtual cursor that can move across panels.
    """

    def __init__(self, screen_width, screen_height=0):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.panels = []
        self.main_index = 0
        self._capture_thread = None
        self._running = False
        self._lock = threading.Lock()

        # Virtual cursor: tracks position across all panels
        # Real mouse stays within screen bounds; virtual cursor extends beyond
        self._vcursor_x = screen_width / 2.0
        self._vcursor_y = screen_height / 2.0 if screen_height > 0 else 400.0
        self._last_real_x = -1
        self._last_real_y = -1

    def add_main_panel(self):
        """Add the main DXGI panel at center."""
        p = Panel("Main Screen", is_main=True)
        self.panels.append(p)
        self.main_index = len(self.panels) - 1
        return p

    def add_panel_left(self, hwnd, title):
        """Add a window panel to the left of all existing panels."""
        p = Panel(title, hwnd=hwnd)
        with self._lock:
            self.panels.insert(0, p)
            self.main_index += 1  # main shifted right
        p.update_capture()  # grab first frame
        print(f"  Panel added LEFT: {title}")
        return p

    def add_panel_right(self, hwnd, title):
        """Add a window panel to the right of all existing panels."""
        p = Panel(title, hwnd=hwnd)
        with self._lock:
            self.panels.append(p)
        p.update_capture()
        print(f"  Panel added RIGHT: {title}")
        return p

    def get_panels(self):
        """Get all panels, ordered left to right."""
        with self._lock:
            return list(self.panels)

    def get_panel_offset_px(self, panel_index):
        """Get the x pixel offset for a panel relative to the main panel."""
        import config
        gap = getattr(config, 'PANEL_GAP', 50)
        return (panel_index - self.main_index) * (self.screen_width + gap)

    def get_total_width(self):
        """Total width of all panels combined."""
        return len(self.panels) * self.screen_width

    def start_capture(self, fps=30):
        """Start background thread to update side panels."""
        self._running = True
        self._capture_thread = threading.Thread(target=self._capture_loop,
                                                 daemon=True, args=(fps,))
        self._capture_thread.start()

    def _capture_loop(self, fps):
        interval = 1.0 / fps
        while self._running:
            with self._lock:
                panels = list(self.panels)
            for p in panels:
                if not p.is_main:
                    p.update_capture()
            time.sleep(interval)

    def update_virtual_cursor(self, real_x, real_y):
        """
        Update virtual cursor from real mouse position.
        When the real cursor hits the screen edge and there's a panel beyond,
        warps the real cursor to the opposite edge (Synergy-style).
        """
        if self._last_real_x < 0:
            self._last_real_x = real_x
            self._last_real_y = real_y
            return

        dx = real_x - self._last_real_x
        dy = real_y - self._last_real_y
        self._last_real_x = real_x
        self._last_real_y = real_y

        self._vcursor_x += dx
        self._vcursor_y += dy

        import config
        gap = getattr(config, 'PANEL_GAP', 50)
        edge_margin = 5
        nudge_speed = 8.0  # pixels per frame when at edge

        # At screen edge + more panels exist → push virtual cursor beyond screen
        # No SetCursorPos (causes deadlocks with WS_EX_TRANSPARENT)
        left_edge = self.get_panel_offset_px(0)
        right_limit = self.get_panel_offset_px(len(self.panels) - 1) + self.screen_width

        if real_x <= edge_margin and self._vcursor_x > left_edge:
            self._vcursor_x -= nudge_speed
        elif real_x >= self.screen_width - edge_margin and self._vcursor_x < right_limit:
            self._vcursor_x += nudge_speed

        # Clamp to total panel range
        total_w = len(self.panels) * (self.screen_width + gap) - gap
        left_edge = self.get_panel_offset_px(0)
        right_edge = left_edge + total_w
        self._vcursor_x = max(left_edge, min(right_edge, self._vcursor_x))
        self._vcursor_y = max(0, min(self.screen_height, self._vcursor_y))

    def get_virtual_cursor(self):
        """Get virtual cursor position (may be outside physical screen)."""
        return self._vcursor_x, self._vcursor_y

    def get_active_panel_index(self):
        """Which panel is the virtual cursor on?"""
        import config
        gap = getattr(config, 'PANEL_GAP', 50)
        for i in range(len(self.panels)):
            px = self.get_panel_offset_px(i)
            if px <= self._vcursor_x < px + self.screen_width:
                return i
        return self.main_index

    def get_cursor_on_panel(self):
        """Get cursor position relative to its active panel (0..screen_width)."""
        import config
        gap = getattr(config, 'PANEL_GAP', 50)
        idx = self.get_active_panel_index()
        px = self.get_panel_offset_px(idx)
        return self._vcursor_x - px, self._vcursor_y

    def stop(self):
        self._running = False
        if self._capture_thread:
            self._capture_thread.join(timeout=2.0)
