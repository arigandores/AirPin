"""
Global hotkey manager using GetAsyncKeyState.
Polls keyboard state directly — works regardless of focus or message queue.
"""

import ctypes
import ctypes.wintypes
import time

user32 = ctypes.windll.user32
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.wintypes.SHORT

# Virtual key codes for modifiers
VK_CONTROL = 0x11
VK_MENU = 0x12     # Alt
VK_SHIFT = 0x10

# Modifier flags (matching config.py)
MOD_CTRL = 0x0002
MOD_ALT = 0x0001
MOD_SHIFT = 0x0004


def _is_key_down(vk):
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


class HotkeyManager:
    """Poll-based global hotkeys using GetAsyncKeyState."""

    def __init__(self):
        self._hotkeys = {}  # name -> (modifier_flags, vk_code)
        self._cooldowns = {}  # name -> last_trigger_time
        self._cooldown_sec = 0.3  # prevent rapid re-triggering

    def register(self, name, modifiers, vk_code):
        """Register a hotkey. Always succeeds (no OS registration needed)."""
        self._hotkeys[name] = (modifiers, vk_code)
        self._cooldowns[name] = 0.0
        return True

    def poll(self):
        """
        Check which hotkeys are currently pressed.
        Returns set of triggered hotkey names.
        """
        triggered = set()
        now = time.monotonic()

        for name, (mods, vk) in self._hotkeys.items():
            # Check cooldown
            if now - self._cooldowns[name] < self._cooldown_sec:
                continue

            # Check modifiers
            mods_ok = True
            if mods & MOD_CTRL and not _is_key_down(VK_CONTROL):
                mods_ok = False
            if mods & MOD_ALT and not _is_key_down(VK_MENU):
                mods_ok = False
            if mods & MOD_SHIFT and not _is_key_down(VK_SHIFT):
                mods_ok = False

            if not mods_ok:
                continue

            # Check the key itself
            if _is_key_down(vk):
                triggered.add(name)
                self._cooldowns[name] = now

        return triggered

    def unregister_all(self):
        """No-op (GetAsyncKeyState doesn't need registration)."""
        self._hotkeys.clear()
