"""
Comprehensive multi-display tests.
Tests all combinations of adding displays left/right.
"""
import ctypes
ctypes.windll.shcore.SetProcessDpiAwareness(2)
import time
from virtual_display import VirtualDisplayManager
from window_capture import capture_screen

user32 = ctypes.windll.user32
PW = user32.GetSystemMetrics(0)
PH = user32.GetSystemMetrics(1)

def check_layout(vdd, test_name, expected_displays):
    """Verify all displays are correctly positioned and non-overlapping."""
    errors = []
    displays = vdd.get_displays()

    if len(displays) != expected_displays:
        errors.append(f"Expected {expected_displays} displays, got {len(displays)}")
        return errors

    # Collect all screen regions: primary + VDD displays
    regions = [("Primary", 0, PW, PH)]
    for idx, dev, pos, actual_x, w, h in displays:
        regions.append((f"VDD-{pos}-{idx}", actual_x, w, h))

    # Check no overlaps
    rects = [(name, x, x + w) for name, x, w, h in regions]
    rects.sort(key=lambda r: r[1])
    for i in range(len(rects) - 1):
        name1, _, right1 = rects[i]
        name2, left2, _ = rects[i + 1]
        if right1 > left2:
            errors.append(f"OVERLAP: {name1} ends at {right1}, {name2} starts at {left2}")

    # Check captures work
    for idx, dev, pos, actual_x, w, h in displays:
        result = capture_screen(actual_x, 0, w, h)
        if result is None:
            errors.append(f"VDD-{pos} at x={actual_x}: capture returned None")
        elif result[2].mean() < 1:
            errors.append(f"VDD-{pos} at x={actual_x}: capture is BLACK")

    # Check virtual desktop covers everything
    vw = user32.GetSystemMetrics(78)
    leftmost = min(r[1] for r in rects)
    rightmost = max(r[2] for r in rects)
    total = rightmost - leftmost
    if vw < total:
        errors.append(f"Virtual desktop {vw} < total {total}")

    if not errors:
        layout = " | ".join(f"{r[0]}({r[1]}-{r[2]})" for r in rects)
        print(f"  [{test_name}] OK: {layout}")
    else:
        for e in errors:
            print(f"  [{test_name}] FAIL: {e}")

    return errors


all_errors = []

# ══════════════════════════════════════════════════════════════════════
print("=" * 60)
print("TEST 1: One display RIGHT")
print("=" * 60)
vdd = VirtualDisplayManager()
vdd.start()
vdd.add_display(PW, PH, 60, position='right')
time.sleep(1.5)
errs = check_layout(vdd, "1R", 1)
all_errors.extend(errs)
vdd.stop()
time.sleep(3)

# ══════════════════════════════════════════════════════════════════════
print("\nTEST 2: One display LEFT")
print("=" * 60)
vdd = VirtualDisplayManager()
vdd.start()
vdd.add_display(PW, PH, 60, position='left')
time.sleep(1.5)
errs = check_layout(vdd, "1L", 1)
all_errors.extend(errs)
vdd.stop()
time.sleep(1)

# ══════════════════════════════════════════════════════════════════════
print("\nTEST 3: One LEFT + One RIGHT")
print("=" * 60)
vdd = VirtualDisplayManager()
vdd.start()
vdd.add_display(PW, PH, 60, position='left')
time.sleep(1.5)
vdd.add_display(PW, PH, 60, position='right')
time.sleep(1.5)
errs = check_layout(vdd, "1L+1R", 2)
all_errors.extend(errs)
vdd.stop()
time.sleep(1)

# ══════════════════════════════════════════════════════════════════════
print("\nTEST 4: Two LEFT")
print("=" * 60)
vdd = VirtualDisplayManager()
vdd.start()
vdd.add_display(PW, PH, 60, position='left')
time.sleep(1.5)
vdd.add_display(PW, PH, 60, position='left')
time.sleep(1.5)
errs = check_layout(vdd, "2L", 2)
all_errors.extend(errs)
vdd.stop()
time.sleep(1)

# ══════════════════════════════════════════════════════════════════════
print("\nTEST 5: Two RIGHT")
print("=" * 60)
vdd = VirtualDisplayManager()
vdd.start()
vdd.add_display(PW, PH, 60, position='right')
time.sleep(1.5)
vdd.add_display(PW, PH, 60, position='right')
time.sleep(1.5)
errs = check_layout(vdd, "2R", 2)
all_errors.extend(errs)
vdd.stop()
time.sleep(1)

# ══════════════════════════════════════════════════════════════════════
print("\nTEST 6: LEFT + RIGHT + LEFT")
print("=" * 60)
vdd = VirtualDisplayManager()
vdd.start()
vdd.add_display(PW, PH, 60, position='left')
time.sleep(1.5)
vdd.add_display(PW, PH, 60, position='right')
time.sleep(1.5)
vdd.add_display(PW, PH, 60, position='left')
time.sleep(1.5)
errs = check_layout(vdd, "L+R+L", 3)
all_errors.extend(errs)
vdd.stop()
time.sleep(1)

# ══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
if all_errors:
    print(f"TOTAL FAILURES: {len(all_errors)}")
    for e in all_errors:
        print(f"  - {e}")
else:
    print("ALL 6 TESTS PASSED!")
print("=" * 60)
