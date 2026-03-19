"""Check which resolutions Parsec VDD supports."""
import ctypes
ctypes.windll.shcore.SetProcessDpiAwareness(2)
from virtual_display import VirtualDisplayManager, DEVMODEW
import time

user32 = ctypes.windll.user32

vdd = VirtualDisplayManager()
vdd.start()
info = vdd.add_display(1920, 1080, 60, position='right')
time.sleep(1)

device = info['device']
print(f"VDD device: {device}")
print(f"Supported resolutions:")

dm = DEVMODEW()
dm.dmSize = ctypes.sizeof(dm)
i = 0
modes = set()
while user32.EnumDisplaySettingsW(device, i, ctypes.byref(dm)):
    mode = (dm.dmPelsWidth, dm.dmPelsHeight, dm.dmDisplayFrequency)
    if mode not in modes and dm.dmPelsWidth > 0:
        modes.add(mode)
    i += 1

for w, h, hz in sorted(modes):
    marker = " <-- primary" if w == 2560 and h == 1600 else ""
    print(f"  {w}x{h} @ {hz}Hz{marker}")

vdd.stop()
