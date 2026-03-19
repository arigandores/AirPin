"""Quick test: add 2 displays right, check no overlap, fast shutdown."""
import ctypes
ctypes.windll.shcore.SetProcessDpiAwareness(2)
import time
from virtual_display import VirtualDisplayManager
from window_capture import capture_screen

user32 = ctypes.windll.user32
PW = user32.GetSystemMetrics(0)

vdd = VirtualDisplayManager()
vdd.start()

d1 = vdd.add_display(PW, 1600, 120, position='right')
time.sleep(1.5)
d2 = vdd.add_display(PW, 1600, 120, position='right')
time.sleep(1.5)

displays = vdd.get_displays()
print("Displays: " + str(len(displays)))
for idx, dev, pos, x, w, h in displays:
    cap = capture_screen(x, 0, w, h)
    bright = cap[2].mean() if cap else 0
    print("  " + dev + " pos=" + pos + " x=" + str(x) + " " + str(w) + "x" + str(h) + " brightness=" + str(int(bright)))

# Check no overlap
if len(displays) == 2:
    x1 = displays[0][3]
    x2 = displays[1][3]
    w1 = displays[0][4]
    if x1 + w1 <= x2:
        print("No overlap: OK")
    else:
        print("OVERLAP!")

# Test fast shutdown
t0 = time.time()
vdd.stop()
t1 = time.time()
print("Shutdown time: " + str(round(t1-t0, 2)) + "s")
if t1-t0 < 2:
    print("Fast shutdown: OK")
else:
    print("Shutdown too slow!")
