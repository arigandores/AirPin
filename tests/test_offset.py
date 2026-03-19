"""Check: does the renderer actually shift the image?"""
import ctypes
ctypes.windll.shcore.SetProcessDpiAwareness(2)
import math, config

pw = ctypes.windll.user32.GetSystemMetrics(0)
ppd_rad = pw / math.radians(config.FOV_HORIZONTAL_DEG)
yaw_sign = -1.0 if config.INVERT_YAW else 1.0

print("INVERT_YAW = " + str(config.INVERT_YAW))
print("yaw_sign = " + str(yaw_sign))
print("PPD = " + str(round(ppd_rad)) + " px/rad")
print("")

# Simulate: head turned LEFT, yaw = +0.1 rad (~5.7 deg)
yaw = 0.1
offset_x = yaw_sign * yaw * ppd_rad
print("Head LEFT 5.7 deg:")
print("  yaw = +" + str(yaw))
print("  offset_x = " + str(round(offset_x)) + " px")
if offset_x > 0:
    print("  Image shifts RIGHT = SPATIAL PINNING (correct)")
elif offset_x < 0:
    print("  Image shifts LEFT = FOLLOWS HEAD (wrong!)")
else:
    print("  No shift??")

print("")
# Simulate: head turned RIGHT, yaw = -0.1 rad
yaw = -0.1
offset_x = yaw_sign * yaw * ppd_rad
print("Head RIGHT 5.7 deg:")
print("  yaw = " + str(yaw))
print("  offset_x = " + str(round(offset_x)) + " px")
if offset_x < 0:
    print("  Image shifts LEFT = SPATIAL PINNING (correct)")
elif offset_x > 0:
    print("  Image shifts RIGHT = FOLLOWS HEAD (wrong!)")
