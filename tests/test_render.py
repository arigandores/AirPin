"""Automated render test — checks panel sizes, positions, quality."""
import ctypes
ctypes.windll.shcore.SetProcessDpiAwareness(2)
import time, math
from virtual_display import VirtualDisplayManager
from window_capture import capture_screen, WindowSlot
import numpy as np

user32 = ctypes.windll.user32
primary_w = user32.GetSystemMetrics(0)
primary_h = user32.GetSystemMetrics(1)
print(f"Primary: {primary_w}x{primary_h}")

errors = []

# Test 1: Main capture size
print("\n[1] Main capture size")
result = capture_screen(0, 0, primary_w, primary_h)
if result:
    w, h, data = result
    print(f"  Captured: {w}x{h}")
    if w != primary_w or h != primary_h:
        errors.append(f"Main capture size {w}x{h} != primary {primary_w}x{primary_h}")
    if data.mean() < 5:
        errors.append("Main capture is BLACK")
    else:
        print(f"  Content OK (brightness={data.mean():.0f})")
else:
    errors.append("Main capture returned None")

# Test 2: Add VDD, check its size matches primary
print("\n[2] VDD display size")
vdd = VirtualDisplayManager()
vdd.start()
info = vdd.add_display(primary_w, primary_h, 60, position='right')
time.sleep(1.5)
print(f"  VDD: x={info['x']} size={info['width']}x{info['height']}")
if info['width'] != primary_w or info['height'] != primary_h:
    errors.append(f"VDD size {info['width']}x{info['height']} != primary {primary_w}x{primary_h}")

# Test 3: VDD capture has content
print("\n[3] VDD capture content")
result2 = capture_screen(info['x'], 0, info['width'], info['height'])
if result2:
    w2, h2, data2 = result2
    print(f"  Captured: {w2}x{h2}, brightness={data2.mean():.0f}")
    if data2.mean() < 1:
        errors.append(f"VDD capture is BLACK at x={info['x']}")
else:
    errors.append("VDD capture returned None")

# Test 4: Virtual desktop size
print("\n[4] Virtual desktop")
vw = user32.GetSystemMetrics(78)
vh = user32.GetSystemMetrics(79)
expected_w = primary_w + info['width']
print(f"  Virtual desktop: {vw}x{vh}")
print(f"  Expected width: {expected_w}")
if vw != expected_w:
    errors.append(f"Virtual desktop width {vw} != expected {expected_w}")

# Test 5: Render math simulation
print("\n[5] Render math check")
# Simulate what render_panels does
zoom = 1.0
head_yaw = 0.0
ppd_rad = primary_w / math.radians(46.0)
head_offset_x = head_yaw * ppd_rad

# Main panel
main_slot = WindowSlot("Main")
main_slot.width = primary_w
main_slot.height = primary_h
main_slot.pixel_data = np.zeros((primary_h, primary_w, 4), dtype=np.uint8)

# Simulate render for main panel (offset=0)
tex_w, tex_h = primary_w, primary_h
sw = float(tex_w) * zoom
sh = float(tex_h) * zoom
primary_cx = float(primary_w) * 0.5
primary_cy = float(primary_h) * 0.5
x_main = 0 * zoom + head_offset_x + primary_cx * (1 - zoom)
y_main = head_offset_y if 'head_offset_y' in dir() else primary_cy - sh * 0.5

print(f"  Main panel: x={x_main:.0f} y={y_main:.0f} sw={sw:.0f} sh={sh:.0f}")
if sw != primary_w:
    errors.append(f"Main panel width {sw:.0f} != {primary_w}")
if x_main != 0:
    errors.append(f"Main panel x={x_main:.0f} should be 0 at yaw=0")

# VDD panel (offset=2560)
x_vdd = info['x'] * zoom + head_offset_x + primary_cx * (1 - zoom)
print(f"  VDD panel: x={x_vdd:.0f} sw={sw:.0f}")
if x_vdd != info['x']:
    errors.append(f"VDD panel x={x_vdd:.0f} should be {info['x']} at yaw=0")
if abs(x_vdd - primary_w) > 1:
    errors.append(f"VDD panel starts at {x_vdd:.0f}, should be right after primary at {primary_w}")

# Overlap check
main_right = x_main + sw
vdd_left = x_vdd
print(f"  Main right edge: {main_right:.0f}")
print(f"  VDD left edge: {vdd_left:.0f}")
if main_right > vdd_left:
    errors.append(f"OVERLAP! Main extends to {main_right:.0f} but VDD starts at {vdd_left:.0f}")
else:
    print(f"  Gap: {vdd_left - main_right:.0f}px — OK")

# Cleanup
vdd.stop()

# Summary
print("\n" + "=" * 50)
if errors:
    print(f"FAILED: {len(errors)} error(s)")
    for e in errors:
        print(f"  - {e}")
else:
    print("ALL TESTS PASSED")
