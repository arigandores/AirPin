import ctypes
ctypes.windll.shcore.SetProcessDpiAwareness(2)
from virtual_display import VirtualDisplayManager
import time

user32 = ctypes.windll.user32

vdd = VirtualDisplayManager()
vdd.start()
info = vdd.add_display(1920, 1080, 60, position='right')
time.sleep(2)

print(f"VDD display: x={info['x']} w={info['width']} h={info['height']}")
print(f"Primary: {user32.GetSystemMetrics(0)}x{user32.GetSystemMetrics(1)}")
print(f"Virtual desktop: origin=({user32.GetSystemMetrics(76)},{user32.GetSystemMetrics(77)}) "
      f"size={user32.GetSystemMetrics(78)}x{user32.GetSystemMetrics(79)}")

# Check: can mouse reach the virtual display?
# Move cursor to the virtual display area
print(f"\nMoving cursor to virtual display at ({info['x'] + 100}, 500)...")
user32.SetCursorPos(info['x'] + 100, 500)
time.sleep(0.5)

pt = ctypes.wintypes.POINT()
user32.GetCursorPos(ctypes.byref(pt))
print(f"Cursor actual position: ({pt.x}, {pt.y})")
if pt.x >= info['x']:
    print("Cursor reached virtual display OK!")
else:
    print(f"Cursor stuck at x={pt.x} - can't reach virtual display")
    print("Windows may not have extended the desktop properly")

# Check if display is in Extend mode
class DEVMODEW(ctypes.Structure):
    _fields_ = [
        ("dmDeviceName", ctypes.c_wchar * 32),
        ("dmSpecVersion", ctypes.wintypes.WORD),
        ("dmDriverVersion", ctypes.wintypes.WORD),
        ("dmSize", ctypes.wintypes.WORD),
        ("dmDriverExtra", ctypes.wintypes.WORD),
        ("dmFields", ctypes.wintypes.DWORD),
        ("dmPositionX", ctypes.c_long),
        ("dmPositionY", ctypes.c_long),
        ("_pad", ctypes.c_byte * 300),
    ]

dm = DEVMODEW()
dm.dmSize = ctypes.sizeof(dm)
if user32.EnumDisplaySettingsW(info['device'], -1, ctypes.byref(dm)):
    print(f"\nDisplay settings for {info['device']}:")
    print(f"  Position: ({dm.dmPositionX}, {dm.dmPositionY})")
else:
    print(f"\nCould not query settings for {info['device']}")

vdd.stop()
