"""Turn head LEFT slowly when prompted. This determines the correct INVERT_YAW."""
import ctypes
ctypes.windll.shcore.SetProcessDpiAwareness(2)
from imu_tracker import ImuTracker
import time, math

tracker = ImuTracker()
tracker.start()
time.sleep(1)
tracker.recenter()
time.sleep(0.5)

print("Keep head STILL for 2 seconds...")
time.sleep(2)
y0, _, _ = tracker.get_orientation()

print("Now SLOWLY turn head LEFT... (3 seconds)")
time.sleep(3)
y1, _, _ = tracker.get_orientation()

delta = math.degrees(y1 - y0)
print("")
print("Yaw delta: " + str(round(delta, 1)) + " degrees")

if abs(delta) < 1:
    print("ERROR: No movement detected. Turn head more.")
elif delta > 0:
    print("Gyro convention: LEFT turn = POSITIVE yaw")
    print("INVERT_YAW should be: False")
else:
    print("Gyro convention: LEFT turn = NEGATIVE yaw")
    print("INVERT_YAW should be: True")

tracker.stop()
