import ctypes
ctypes.windll.shcore.SetProcessDpiAwareness(2)
u = ctypes.windll.user32
print(f"Primary: {u.GetSystemMetrics(0)}x{u.GetSystemMetrics(1)}")
print(f"Virtual: origin=({u.GetSystemMetrics(76)},{u.GetSystemMetrics(77)}) size={u.GetSystemMetrics(78)}x{u.GetSystemMetrics(79)}")

# The core issue: overlay is created at startup with primary size,
# then reinit_size expands it. But pygame window can't be resized
# after creation with OpenGL context.
# Let's check what we're actually creating:
from virtual_display import VirtualDisplayManager
import time

vdd = VirtualDisplayManager()
vdd.start()
info = vdd.add_display(1920, 1080, 60, position='right')
time.sleep(1)

print(f"\nAfter VDD add:")
print(f"  VDD at x={info['x']}, {info['width']}x{info['height']}")
print(f"  Virtual: origin=({u.GetSystemMetrics(76)},{u.GetSystemMetrics(77)}) size={u.GetSystemMetrics(78)}x{u.GetSystemMetrics(79)}")
print(f"  VDD creates {info['width']}x{info['height']} but primary is {u.GetSystemMetrics(0)}x{u.GetSystemMetrics(1)}")
print(f"  Total virtual width: {u.GetSystemMetrics(78)}")
print(f"  Primary contributes: {u.GetSystemMetrics(0)} pixels")
print(f"  VDD contributes: {info['width']} pixels")

vdd.stop()
