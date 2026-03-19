import ctypes
ctypes.windll.shcore.SetProcessDpiAwareness(2)
from imu_tracker import ImuTracker
from smooth_follow import SmoothFollow
import time, math

tracker = ImuTracker()
tracker.start()
time.sleep(1.5)
tracker.recenter()

follow = SmoothFollow()
follow.reset()
last_t = time.time()
prev_output = 0.0
jumps = 0

print("10 seconds still:")
for i in range(200):
    now = time.time()
    dt_ms = (now - last_t) * 1000
    last_t = now
    raw_yaw = tracker.get_orientation()[0]
    gyro_mag = getattr(tracker, '_last_gyro_mag', 0.0)
    offset = follow.update(raw_yaw, dt_ms, gyro_mag)
    out_change = abs(math.degrees(offset) - math.degrees(prev_output))
    if out_change > 0.1:
        jumps += 1
        print("  JUMP at t=" + str(round(i*0.05,1)) + "s: " + str(round(out_change,1)) + " deg")
    prev_output = offset
    time.sleep(0.05)

print("Jumps: " + str(jumps) + " (want 0)")
if jumps == 0:
    print("STABLE")
tracker.stop()
