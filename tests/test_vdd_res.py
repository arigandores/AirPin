import ctypes
ctypes.windll.shcore.SetProcessDpiAwareness(2)
from virtual_display import VirtualDisplayManager
import time

vdd = VirtualDisplayManager()
vdd.start()
info = vdd.add_display(2560, 1600, 60, position="right")
time.sleep(1)
w, h, x = info["width"], info["height"], info["x"]
print("Result: " + str(w) + "x" + str(h) + " at x=" + str(x))
vdd.stop()
