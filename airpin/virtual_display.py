"""
Virtual Display Manager using Parsec VDD (already installed).
Creates/removes virtual monitors at runtime via DeviceIoControl.
Displays are auto-removed on cleanup or crash.
"""

import ctypes
import ctypes.wintypes
import threading
import time
import atexit
import signal

kernel32 = ctypes.windll.kernel32
setupapi = ctypes.windll.setupapi
user32 = ctypes.windll.user32

# Parsec VDD IOCTL codes
VDD_IOCTL_ADD = 0x0022e004
VDD_IOCTL_REMOVE = 0x0022a008
VDD_IOCTL_UPDATE = 0x0022a00c
VDD_IOCTL_VERSION = 0x0022e010

# Parsec VDD GUIDs
# Adapter: {00b41627-04c4-429e-a26e-0265cf50c8fa}
class GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort),
                ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8)]

VDD_ADAPTER_GUID = GUID(0x00b41627, 0x04c4, 0x429e,
                         (ctypes.c_ubyte * 8)(0xa2, 0x6e, 0x02, 0x65, 0xcf, 0x50, 0xc8, 0xfa))

VDD_CLASS_GUID = GUID(0x4d36e968, 0xe325, 0x11ce,
                       (ctypes.c_ubyte * 8)(0xbf, 0xc1, 0x08, 0x00, 0x2b, 0xe1, 0x03, 0x18))

VDD_HARDWARE_ID = "Root\\Parsec\\VDA"
VDD_MAX_DISPLAYS = 8

# SetupAPI constants
DIGCF_PRESENT = 0x02
DIGCF_DEVICEINTERFACE = 0x10
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x01
FILE_SHARE_WRITE = 0x02
OPEN_EXISTING = 3
FILE_ATTRIBUTE_NORMAL = 0x80
FILE_FLAG_NO_BUFFERING = 0x20000000
FILE_FLAG_OVERLAPPED = 0x40000000
FILE_FLAG_WRITE_THROUGH = 0x80000000
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

# ChangeDisplaySettingsEx
CDS_UPDATEREGISTRY = 0x01
CDS_NORESET = 0x10000000
DM_PELSWIDTH = 0x80000
DM_PELSHEIGHT = 0x100000
DM_DISPLAYFREQUENCY = 0x400000
DM_POSITION = 0x20

class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.wintypes.DWORD),
                ("InterfaceClassGuid", GUID),
                ("Flags", ctypes.wintypes.DWORD),
                ("Reserved", ctypes.POINTER(ctypes.c_ulong))]

class OVERLAPPED(ctypes.Structure):
    _fields_ = [("Internal", ctypes.POINTER(ctypes.c_ulong)),
                ("InternalHigh", ctypes.POINTER(ctypes.c_ulong)),
                ("Offset", ctypes.wintypes.DWORD),
                ("OffsetHigh", ctypes.wintypes.DWORD),
                ("hEvent", ctypes.wintypes.HANDLE)]

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
        ("dmDisplayOrientation", ctypes.wintypes.DWORD),
        ("dmDisplayFixedOutput", ctypes.wintypes.DWORD),
        ("dmColor", ctypes.c_short),
        ("dmDuplex", ctypes.c_short),
        ("dmYResolution", ctypes.c_short),
        ("dmTTOption", ctypes.c_short),
        ("dmCollate", ctypes.c_short),
        ("dmFormName", ctypes.c_wchar * 32),
        ("dmLogPixels", ctypes.wintypes.WORD),
        ("dmBitsPerPel", ctypes.wintypes.DWORD),
        ("dmPelsWidth", ctypes.wintypes.DWORD),
        ("dmPelsHeight", ctypes.wintypes.DWORD),
        ("dmDisplayFlags", ctypes.wintypes.DWORD),
        ("dmDisplayFrequency", ctypes.wintypes.DWORD),
        # ... more fields exist but we don't need them
        ("_pad", ctypes.c_byte * 128),
    ]


def _open_device():
    """Open Parsec VDD device handle via SetupAPI."""
    dev_info = setupapi.SetupDiGetClassDevsW(
        ctypes.byref(VDD_ADAPTER_GUID), None, None,
        DIGCF_PRESENT | DIGCF_DEVICEINTERFACE
    )
    if dev_info == INVALID_HANDLE_VALUE:
        return None

    iface_data = SP_DEVICE_INTERFACE_DATA()
    iface_data.cbSize = ctypes.sizeof(SP_DEVICE_INTERFACE_DATA)

    for i in range(16):
        if not setupapi.SetupDiEnumDeviceInterfaces(
            dev_info, None, ctypes.byref(VDD_ADAPTER_GUID), i, ctypes.byref(iface_data)
        ):
            break

        # Get required size
        detail_size = ctypes.wintypes.DWORD(0)
        setupapi.SetupDiGetDeviceInterfaceDetailW(
            dev_info, ctypes.byref(iface_data), None, 0, ctypes.byref(detail_size), None
        )
        if detail_size.value == 0:
            continue

        # Allocate and fill detail
        buf = ctypes.create_string_buffer(detail_size.value)
        # cbSize = 8 on 64-bit (sizeof pointer + DWORD)
        ctypes.memmove(buf, ctypes.byref(ctypes.wintypes.DWORD(8)), 4)

        if setupapi.SetupDiGetDeviceInterfaceDetailW(
            dev_info, ctypes.byref(iface_data), buf, detail_size, None, None
        ):
            # Device path starts at offset 4 (after cbSize DWORD)
            path = ctypes.wstring_at(ctypes.addressof(buf) + 4)
            handle = kernel32.CreateFileW(
                path, GENERIC_READ | GENERIC_WRITE,
                FILE_SHARE_READ | FILE_SHARE_WRITE,
                None, OPEN_EXISTING,
                FILE_ATTRIBUTE_NORMAL | FILE_FLAG_NO_BUFFERING |
                FILE_FLAG_OVERLAPPED | FILE_FLAG_WRITE_THROUGH,
                None
            )
            if handle and handle != INVALID_HANDLE_VALUE:
                setupapi.SetupDiDestroyDeviceInfoList(dev_info)
                return handle

    setupapi.SetupDiDestroyDeviceInfoList(dev_info)
    return None


def _ioctl(handle, code, in_data=None, timeout_ms=5000):
    """Send DeviceIoControl to Parsec VDD."""
    in_buf = (ctypes.c_byte * 32)()
    if in_data:
        ctypes.memmove(in_buf, in_data, min(len(in_data), 32))

    out_buf = ctypes.wintypes.DWORD(0)
    overlapped = OVERLAPPED()
    overlapped.hEvent = kernel32.CreateEventW(None, False, False, None)

    kernel32.DeviceIoControl(
        handle, code,
        in_buf, 32,
        ctypes.byref(out_buf), 4,
        None, ctypes.byref(overlapped)
    )

    transferred = ctypes.wintypes.DWORD(0)
    kernel32.GetOverlappedResultEx(
        handle, ctypes.byref(overlapped),
        ctypes.byref(transferred), timeout_ms, False
    )

    if overlapped.hEvent:
        kernel32.CloseHandle(overlapped.hEvent)

    return out_buf.value


class VirtualDisplayManager:
    """Manages Parsec VDD virtual displays."""

    def __init__(self):
        self._handle = None
        self._displays = []  # list of (index, device_name, position)
        self._keepalive_thread = None
        self._running = False
        self._lock = threading.Lock()

        # Register cleanup on exit/crash
        atexit.register(self.remove_all)
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, sig, frame):
        self.remove_all()
        raise SystemExit(0)

    def start(self):
        """Open device and start keepalive."""
        self._handle = _open_device()
        if not self._handle:
            print("  VDD: Parsec Virtual Display Adapter not found!")
            print("  Install from: https://github.com/nomi-san/parsec-vdd")
            return False

        version = _ioctl(self._handle, VDD_IOCTL_VERSION)
        print(f"  VDD: Parsec VDD v0.{version}, max {VDD_MAX_DISPLAYS} displays")

        self._running = True
        self._keepalive_thread = threading.Thread(target=self._keepalive_loop, daemon=True)
        self._keepalive_thread.start()
        return True

    def _keepalive_loop(self):
        """Ping VDD every 100ms to keep virtual displays alive."""
        while self._running:
            if self._handle:
                try:
                    _ioctl(self._handle, VDD_IOCTL_UPDATE)
                except Exception:
                    pass
            time.sleep(0.1)

    def add_display(self, width=1920, height=1080, hz=60, position='right'):
        """
        Add a virtual display and position it relative to the primary monitor.
        position: 'left' or 'right'
        Returns display info dict or None.
        """
        if not self._handle:
            return None
        if len(self._displays) >= VDD_MAX_DISPLAYS:
            print(f"  VDD: Maximum {VDD_MAX_DISPLAYS} displays reached")
            return None

        # Add display via IOCTL
        idx = _ioctl(self._handle, VDD_IOCTL_ADD)
        time.sleep(0.5)  # wait for Windows to detect the new display

        # Find the new display's device name
        device_name = self._find_new_display()
        if not device_name:
            print(f"  VDD: Display added (idx={idx}) but not found by Windows")
            # Try to remove it
            self._remove_by_index(idx)
            return None

        # Calculate position
        primary_w = user32.GetSystemMetrics(0)
        if position == 'left':
            n_left = sum(1 for d in self._displays if d[2] == 'left')
            pos_x = -width * (1 + n_left)
        else:
            n_right = sum(1 for d in self._displays if d[2] == 'right')
            pos_x = primary_w + width * n_right
        pos_y = 0

        # Add to list FIRST so reconfigure_all_positions knows about it
        with self._lock:
            self._displays.append((idx, device_name, position, pos_x, width, height))

        # Wait for Windows to initialize the display
        import time as _time
        _time.sleep(1.0)

        # Reconfigure ALL displays at once (staged then apply)
        self._reconfigure_all_positions()

        # Query actual positions
        with self._lock:
            updated = []
            for d_idx, d_name, d_pos, d_x, d_w, d_h in self._displays:
                ax, aw, ah = self._get_actual_position(d_name, d_x, d_w, d_h)
                updated.append((d_idx, d_name, d_pos, ax, aw, ah))
            self._displays = updated

        # Get this display's actual info
        actual_x, actual_w, actual_h = pos_x, width, height
        with self._lock:
            for d in self._displays:
                if d[0] == idx:
                    actual_x, actual_w, actual_h = d[3], d[4], d[5]
                    break

        print(f"  VDD: Added {device_name} ({actual_w}x{actual_h}@{hz}Hz) at x={actual_x} [{position}]")
        return {'index': idx, 'device': device_name, 'position': position,
                'x': actual_x, 'width': actual_w, 'height': actual_h}

    def _find_new_display(self):
        """Find the device name of a newly added Parsec display."""
        class DISPLAY_DEVICE(ctypes.Structure):
            _fields_ = [
                ('cb', ctypes.wintypes.DWORD),
                ('DeviceName', ctypes.c_wchar * 32),
                ('DeviceString', ctypes.c_wchar * 128),
                ('StateFlags', ctypes.wintypes.DWORD),
                ('DeviceID', ctypes.c_wchar * 128),
                ('DeviceKey', ctypes.c_wchar * 128),
            ]

        known_names = {d[1] for d in self._displays}

        for i in range(32):
            dd = DISPLAY_DEVICE()
            dd.cb = ctypes.sizeof(dd)
            if not user32.EnumDisplayDevicesW(None, i, ctypes.byref(dd), 0):
                break
            if dd.StateFlags & 1:  # DISPLAY_DEVICE_ATTACHED_TO_DESKTOP or active
                name = dd.DeviceName.strip()
                if 'Parsec' in dd.DeviceString or name not in known_names:
                    if name not in known_names and 'DISPLAY' in name:
                        # Check if it's actually a Parsec display
                        dd2 = DISPLAY_DEVICE()
                        dd2.cb = ctypes.sizeof(dd2)
                        if user32.EnumDisplayDevicesW(name, 0, ctypes.byref(dd2), 0):
                            if 'Parsec' in dd2.DeviceString or 'PSCCDD' in dd2.DeviceID:
                                return name
        return None

    def _reconfigure_all_positions(self):
        """Reconfigure ALL virtual displays + primary in one staged batch."""
        primary_w = user32.GetSystemMetrics(0)
        primary = self._get_primary_device()

        # Stage primary at (0,0)
        if primary:
            dm_p = DEVMODEW()
            dm_p.dmSize = ctypes.sizeof(DEVMODEW)
            user32.EnumDisplaySettingsW(primary, -1, ctypes.byref(dm_p))
            dm_p.dmPositionX = 0
            dm_p.dmPositionY = 0
            dm_p.dmFields = DM_POSITION
            user32.ChangeDisplaySettingsExW(
                primary, ctypes.byref(dm_p), None,
                CDS_UPDATEREGISTRY | CDS_NORESET, None
            )

        # Stage each VDD display
        with self._lock:
            displays_copy = list(self._displays)

        for d_idx, d_name, d_pos, d_x, d_w, d_h in displays_copy:
            dm = DEVMODEW()
            dm.dmSize = ctypes.sizeof(DEVMODEW)
            user32.EnumDisplaySettingsW(d_name, -1, ctypes.byref(dm))
            dm.dmPelsWidth = d_w
            dm.dmPelsHeight = d_h
            dm.dmPositionX = d_x
            dm.dmPositionY = 0
            dm.dmFields = DM_PELSWIDTH | DM_PELSHEIGHT | DM_POSITION
            rc = user32.ChangeDisplaySettingsExW(
                d_name, ctypes.byref(dm), None,
                CDS_UPDATEREGISTRY | CDS_NORESET, None
            )
            if rc != 0:
                print(f"  VDD: Stage {d_name} at x={d_x} rc={rc}")

        # Apply all at once
        user32.ChangeDisplaySettingsExW(None, None, None, 0, None)

    def _configure_display(self, device_name, width, height, hz, pos_x, pos_y):
        """Set resolution and position of a display in Extend mode."""
        # Get current settings as base (required for NOTUPDATED fix)
        dm = DEVMODEW()
        dm.dmSize = ctypes.sizeof(DEVMODEW)
        user32.EnumDisplaySettingsW(device_name, -1, ctypes.byref(dm))  # ENUM_CURRENT_SETTINGS

        # Modify what we need
        dm.dmPelsWidth = width
        dm.dmPelsHeight = height
        dm.dmDisplayFrequency = hz
        dm.dmPositionX = pos_x
        dm.dmPositionY = pos_y
        dm.dmFields = DM_PELSWIDTH | DM_PELSHEIGHT | DM_DISPLAYFREQUENCY | DM_POSITION

        result = user32.ChangeDisplaySettingsExW(
            device_name, ctypes.byref(dm), None,
            CDS_UPDATEREGISTRY | CDS_NORESET, None
        )
        if result != 0:
            print(f"  VDD: ChangeDisplaySettings({width}x{height} at x={pos_x}) rc={result}")

        # Ensure primary keeps position (0,0)
        primary = self._get_primary_device()
        if primary:
            dm_p = DEVMODEW()
            dm_p.dmSize = ctypes.sizeof(DEVMODEW)
            user32.EnumDisplaySettingsW(primary, -1, ctypes.byref(dm_p))
            dm_p.dmPositionX = 0
            dm_p.dmPositionY = 0
            dm_p.dmFields = DM_POSITION
            user32.ChangeDisplaySettingsExW(
                primary, ctypes.byref(dm_p), None,
                CDS_UPDATEREGISTRY | CDS_NORESET, None
            )

        # Apply all
        user32.ChangeDisplaySettingsExW(None, None, None, 0, None)
        return result == 0

    def _get_actual_position(self, device_name, fallback_x, fallback_w, fallback_h):
        """Query Windows for the actual position/size of a display."""
        try:
            dm = DEVMODEW()
            dm.dmSize = ctypes.sizeof(DEVMODEW)
            if user32.EnumDisplaySettingsW(device_name, -1, ctypes.byref(dm)):  # ENUM_CURRENT_SETTINGS
                return dm.dmPositionX, dm.dmPelsWidth or fallback_w, dm.dmPelsHeight or fallback_h
        except Exception:
            pass
        return fallback_x, fallback_w, fallback_h

    def _get_primary_device(self):
        """Get the device name of the primary monitor."""
        class DISPLAY_DEVICE(ctypes.Structure):
            _fields_ = [
                ('cb', ctypes.wintypes.DWORD),
                ('DeviceName', ctypes.c_wchar * 32),
                ('DeviceString', ctypes.c_wchar * 128),
                ('StateFlags', ctypes.wintypes.DWORD),
                ('DeviceID', ctypes.c_wchar * 128),
                ('DeviceKey', ctypes.c_wchar * 128),
            ]
        for i in range(32):
            dd = DISPLAY_DEVICE()
            dd.cb = ctypes.sizeof(dd)
            if not user32.EnumDisplayDevicesW(None, i, ctypes.byref(dd), 0):
                break
            if dd.StateFlags & 4:  # DISPLAY_DEVICE_PRIMARY_DEVICE
                return dd.DeviceName.strip()
        return None


    def _remove_by_index(self, idx):
        """Remove a display by VDD index."""
        # 16-bit big-endian index
        idx_data = bytes([(idx >> 8) & 0xFF, idx & 0xFF])
        _ioctl(self._handle, VDD_IOCTL_REMOVE, idx_data)

    def remove_display(self, position_index):
        """Remove a display by its position in our list."""
        with self._lock:
            if position_index >= len(self._displays):
                return
            idx, device_name, pos, *_ = self._displays.pop(position_index)
        self._remove_by_index(idx)
        print(f"  VDD: Removed {device_name}")

    def remove_all(self):
        """Remove all virtual displays instantly via IOCTL."""
        with self._lock:
            displays = list(self._displays)
            self._displays.clear()
        if not displays:
            return
        # Fire-and-forget: send all remove IOCTLs, don't wait for each
        for idx, device_name, pos, *_ in displays:
            try:
                idx_data = bytes([(idx >> 8) & 0xFF, idx & 0xFF])
                # Non-blocking: just send, 100ms timeout
                _ioctl(self._handle, VDD_IOCTL_REMOVE, idx_data, timeout_ms=100)
            except Exception:
                pass
        print(f"  VDD: Removed {len(displays)} display{'s' if len(displays) > 1 else ''}")

    def get_displays(self):
        """Get list of active virtual displays."""
        with self._lock:
            return list(self._displays)

    def stop(self):
        """Clean shutdown."""
        self.remove_all()
        self._running = False
        if self._keepalive_thread:
            self._keepalive_thread.join(timeout=2.0)
        if self._handle:
            kernel32.CloseHandle(self._handle)
            self._handle = None
