"""
Test: does adding a Parsec VDD virtual display kill the RayNeo IMU?
Run after reconnecting USB-C.
"""
import ctypes
ctypes.windll.shcore.SetProcessDpiAwareness(2)

import time, math
from imu_tracker import ImuTracker
from virtual_display import VirtualDisplayManager

print("=" * 50)
print("TEST: Does VDD kill IMU?")
print("=" * 50)

# Step 1: Check IMU works
print("\n[1] Starting IMU...")
tracker = ImuTracker()
tracker.start()
time.sleep(1)
c = tracker.imu_count
print(f"    IMU count: {c}")
if c == 0:
    print("    FAIL: IMU not working. Reconnect USB-C and try again.")
    tracker.stop()
    exit(1)

c1 = tracker.imu_count; time.sleep(0.5); c2 = tracker.imu_count
rate = (c2 - c1) / 0.5
print(f"    IMU rate: {rate:.0f} samples/sec - OK")

# Step 2: Add VDD display
print("\n[2] Adding virtual display...")
vdd = VirtualDisplayManager()
vdd.start()
info = vdd.add_display(1920, 1080, 60, position='right')
print(f"    Added at x={info['x']}")

# Step 3: Wait for topology to settle
print("\n[3] Waiting 3 seconds for Windows to settle...")
time.sleep(3)

# Step 4: Check IMU again
c3 = tracker.imu_count; time.sleep(0.5); c4 = tracker.imu_count
rate2 = (c4 - c3) / 0.5
print(f"\n[4] IMU rate AFTER VDD: {rate2:.0f} samples/sec")

if rate2 > 100:
    print("    RESULT: IMU SURVIVES VDD!")
    print("    The previous IMU deaths were from crashes, not from VDD.")
elif rate2 > 0:
    print("    RESULT: IMU DEGRADED but alive")
else:
    print("    RESULT: VDD KILLS IMU")
    print("    Need to restart IMU after adding VDD displays.")

    # Step 5: Try restarting IMU
    print("\n[5] Restarting IMU SDK...")
    tracker.stop()
    time.sleep(1)
    tracker = ImuTracker()
    tracker.start()
    time.sleep(1)
    c5 = tracker.imu_count; time.sleep(0.5); c6 = tracker.imu_count
    rate3 = (c6 - c5) / 0.5
    print(f"    IMU rate after restart: {rate3:.0f} samples/sec")
    if rate3 > 0:
        print("    FIX: Restarting SDK works!")
    else:
        print("    SDK restart doesn't help. Need USB reconnect.")

# Cleanup
print("\n[6] Cleaning up...")
vdd.stop()
tracker.stop()
print("    Done.")
