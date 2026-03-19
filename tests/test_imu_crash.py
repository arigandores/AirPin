"""Find what kills IMU: clean stop vs simulated crash."""
import ctypes
ctypes.windll.shcore.SetProcessDpiAwareness(2)
from imu_tracker import ImuTracker
import time

print("=== Test 1: Clean stop/restart ===")
t = ImuTracker()
t.start()
time.sleep(1)
print(f"  Before stop: {t.imu_count}")
t.stop()
time.sleep(1)
t2 = ImuTracker()
t2.start()
time.sleep(1)
print(f"  After clean restart: {t2.imu_count}")
t2.stop()

print()
print("=== Test 2: Crash (no stop), then restart ===")
t3 = ImuTracker()
t3.start()
time.sleep(1)
print(f"  Before crash: {t3.imu_count}")
# DON'T call stop — simulate crash
del t3
time.sleep(2)
t4 = ImuTracker()
t4.start()
time.sleep(1)
print(f"  After crash restart: {t4.imu_count}")
if t4.imu_count == 0:
    print("  >>> Crash without stop() kills IMU!")
else:
    print("  IMU survived one crash")
t4.stop()

print()
print("=== Test 3: Second crash, then restart ===")
t5 = ImuTracker()
t5.start()
time.sleep(1)
print(f"  Before crash 2: {t5.imu_count}")
del t5
time.sleep(2)
t6 = ImuTracker()
t6.start()
time.sleep(1)
print(f"  After crash 2 restart: {t6.imu_count}")
if t6.imu_count == 0:
    print("  >>> Multiple crashes kill IMU!")
else:
    print("  IMU survived two crashes")
t6.stop()

print()
print("=== Test 4: Ctrl+C simulation (KeyboardInterrupt) ===")
t7 = ImuTracker()
t7.start()
time.sleep(1)
print(f"  Before interrupt: {t7.imu_count}")
# Don't stop, just abandon
t7._running = False
# Don't call stop() or destroy SDK
time.sleep(2)
t8 = ImuTracker()
t8.start()
time.sleep(1)
print(f"  After interrupt restart: {t8.imu_count}")
if t8.imu_count == 0:
    print("  >>> Abandoning SDK without Destroy() kills IMU!")
else:
    print("  IMU survived")
t8.stop()
print()
print("Done.")
