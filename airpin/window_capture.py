"""
Screen capture using BitBlt from screen DC.
Simple, reliable, works with any display configuration.
No DXGI dependency — no crashes from display topology changes.
"""

import ctypes
import ctypes.wintypes
import threading
import time
import numpy as np

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
SRCCOPY = 0x00CC0020
BI_RGB = 0
DIB_RGB_COLORS = 0


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

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


def list_windows():
    """List all visible, capturable windows."""
    results = []
    def enum_callback(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        if ex_style & WS_EX_TOOLWINDOW:
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value
        if not title or title in ("Program Manager", "Windows Input Experience"):
            return True
        rect = RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        w = rect.right - rect.left
        h = rect.bottom - rect.top
        if w > 0 and h > 0:
            results.append((hwnd, title, (rect.left, rect.top, w, h)))
        return True
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(enum_callback), 0)
    return results


def capture_screen(x=0, y=0, w=None, h=None):
    """
    Capture a screen region as BGRA numpy array.
    Returns (w, h, data) or None.
    """
    try:
        if w is None:
            w = user32.GetSystemMetrics(0)
        if h is None:
            h = user32.GetSystemMetrics(1)
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


class ScreenCapture:
    """Captures a screen region via BitBlt. Simple and always works."""

    def __init__(self, x=0, y=0, width=None, height=None):
        self.x = x
        self.y = y
        self.width = width or user32.GetSystemMetrics(0)
        self.height = height or user32.GetSystemMetrics(1)

    def start(self):
        # Test grab
        result = self.grab()
        return result is not None

    def grab(self):
        return capture_screen(self.x, self.y, self.width, self.height)

    def reinit(self):
        pass  # BitBlt doesn't need reinit

    def stop(self):
        pass


class WindowSlot:
    """A captured screen region with its texture data."""
    def __init__(self, title="Screen"):
        self.title = title
        self.width = 0
        self.height = 0
        self.pixel_data = None
        self.texture_dirty = True
        self.gl_texture_id = None
        self.pos_x = 0.0
        self.pos_y = 0.0
        self.pos_z = -3.0
        self.scale = 1.0


class WindowManager:
    """Manages screen capture and periodic updates."""

    def __init__(self, capture_fps=30, monitor_index=0):
        self.capture = ScreenCapture()
        self.slot = WindowSlot("Primary Monitor")
        self.capture_interval = 1.0 / capture_fps
        self._thread = None
        self._running = False

    def get_slots(self):
        return [self.slot]

    def start(self):
        if not self.capture.start():
            return False
        print(f"  Screen capture: {self.capture.width}x{self.capture.height} BitBlt")
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        return True

    def _capture_loop(self):
        while self._running:
            result = self.capture.grab()
            if result is not None:
                w, h, data = result
                self.slot.width = w
                self.slot.height = h
                self.slot.pixel_data = data
                self.slot.texture_dirty = True
            time.sleep(self.capture_interval)

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        self.capture.stop()
