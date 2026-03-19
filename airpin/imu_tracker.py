"""
IMU tracker for RayNeo Air 4 Pro.
Reads gyro/accel via RayNeoSDK.dll, fuses into yaw/pitch/roll.
"""

import os
import ctypes
import threading
import numpy as np
from ctypes import (
    c_uint8, c_uint16, c_uint32, c_uint64, c_int, c_float,
    c_void_p, c_char, POINTER, Structure, Union, byref
)

import config

# ── SDK C types ──────────────────────────────────────────────────────────────

class RAYNEO_ImuSample(Structure):
    _fields_ = [
        ("acc", c_float * 3), ("gyroDps", c_float * 3), ("gyroRad", c_float * 3),
        ("magnet", c_float * 3), ("temperature", c_float), ("psensor", c_float),
        ("lsensor", c_float), ("tick", c_uint32), ("count", c_uint32),
        ("flag", c_uint8), ("checksum", c_uint8), ("valid", c_uint8), ("reserved", c_uint8),
    ]

class RAYNEO_DeviceInfoMini(Structure):
    _fields_ = [
        ("raw", c_uint8 * 60), ("valid", c_uint8), ("reserved", c_uint8 * 3),
        ("tick", c_uint32), ("value", c_uint8), ("cpuid", c_uint8 * 12),
        ("board_id", c_uint8), ("sensor_on", c_uint8), ("support_fov", c_uint8),
        ("date", c_char * 13), ("year", c_uint16), ("month", c_uint8), ("day", c_uint8),
        ("glasses_fps", c_uint8), ("luminance", c_uint8), ("volume", c_uint8),
        ("side_by_side", c_uint8), ("psensor_enable", c_uint8), ("audio_mode", c_uint8),
        ("dp_status", c_uint8), ("status3", c_uint8), ("psensor_valid", c_uint8),
        ("lsensor_valid", c_uint8), ("gyro_valid", c_uint8), ("magnet_valid", c_uint8),
        ("reserve1", c_float), ("reserve2", c_float), ("max_luminance", c_uint8),
        ("max_volume", c_uint8), ("support_panel_color_adjust", c_uint8), ("flag", c_uint8),
    ]

class _NotifyData(Structure):
    _fields_ = [("code", c_int), ("message", c_char * 96)]
class _LogData(Structure):
    _fields_ = [("level", c_int), ("message", c_char * 96)]
class _ErrorData(Structure):
    _fields_ = [("code", c_int)]
class _EventUnion(Union):
    _fields_ = [
        ("imu", RAYNEO_ImuSample), ("info", RAYNEO_DeviceInfoMini),
        ("error", _ErrorData), ("log", _LogData), ("notify", _NotifyData),
    ]
class RAYNEO_Event(Structure):
    _fields_ = [("type", c_int), ("seq", c_uint64), ("data", _EventUnion)]

EVT_IMU = 2
EVT_DETACHED = 1

# ── Config ───────────────────────────────────────────────────────────────────

# Gyro deadzone in rad/s. Filters noise when head is still.
# No deadzone on gyro INTEGRATION (prevents asymmetric drift).
GYRO_DEADZONE = 0.0

# Output deadzone on displayed yaw.
OUTPUT_DEADZONE_DEG = 0.5

# Auto-bias: update bias ONLY when head is VERY still for a LONG time.
# Much stricter than before: 0.01 rad/s threshold, 2 seconds of stillness,
# tiny learn rate. This prevents corrupting bias with movement data.
STILL_THRESHOLD = 0.01   # rad/s — very strict stillness detection
STILL_SAMPLES = 1000     # 2 seconds at 500Hz before updating
BIAS_LEARN_RATE = 0.0002 # very slow adaptation

# EMA smoothing alpha at 500Hz. Equivalent to ~0.25 at 60Hz.
EMA_ALPHA = 0.035

YAW_DECAY = 1.0  # No decay

# Fixed bias calibration at startup (first 500 samples = ~1 second).
# No auto-bias during use — it corrupts the bias with movement data.
# User can recenter with Ctrl+Alt+R.
BIAS_SAMPLES = 500

# ── IMU Tracker ──────────────────────────────────────────────────────────────

class ImuTracker:
    def __init__(self):
        self.sdk = None
        self.ctx = None
        self.connected = False
        self._lock = threading.Lock()
        self._thread = None
        self._running = False
        self._imu_count = 0

        # Raw integrated angles from complementary filter
        self._raw_yaw = 0.0
        self._raw_pitch = 0.0
        self._raw_roll = 0.0

        # EMA-smoothed output
        self._yaw = 0.0
        self._pitch = 0.0
        self._roll = 0.0

        # Reference (set on recenter)
        self._ref_yaw = 0.0
        self._ref_pitch = 0.0
        self._ref_roll = 0.0

        # Bias calibration
        self._gyro_bias = np.zeros(3)
        self._bias_count = 0
        self._bias_done = False
        self._last_tick = 0
        self._cf_initialized = False

        # Output deadzone state
        self._output_yaw = 0.0
        self._still_counter = 0

    def _find_dll(self):
        root = os.path.dirname(os.path.dirname(__file__))  # project root
        candidates = [
            os.path.join(root, "lib", "RayNeoSDK.dll"),
            os.path.join(os.path.dirname(__file__), "RayNeoSDK.dll"),
            os.path.join(root, "RayNeoSDK.dll"),
        ]
        if config.SDK_DLL_PATH and os.path.exists(config.SDK_DLL_PATH):
            return config.SDK_DLL_PATH
        for p in candidates:
            if os.path.exists(p):
                return p
        return None

    def start(self):
        dll_path = self._find_dll()
        if not dll_path:
            raise FileNotFoundError("RayNeoSDK.dll not found")
        dll_dir = os.path.dirname(dll_path)
        os.add_dll_directory(dll_dir)
        os.environ["PATH"] = dll_dir + ";" + os.environ.get("PATH", "")
        # Also add lib/ directory for libusb
        lib_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "lib")
        if os.path.isdir(lib_dir):
            os.add_dll_directory(lib_dir)
            os.environ["PATH"] = lib_dir + ";" + os.environ.get("PATH", "")

        self.sdk = ctypes.CDLL(dll_path)
        s = self.sdk
        s.Rayneo_Create.restype = c_int
        s.Rayneo_Create.argtypes = [POINTER(c_void_p)]
        s.Rayneo_Destroy.argtypes = [c_void_p]
        s.Rayneo_SetTargetVidPid.restype = c_int
        s.Rayneo_SetTargetVidPid.argtypes = [c_void_p, c_uint16, c_uint16]
        s.Rayneo_Start.restype = c_int
        s.Rayneo_Start.argtypes = [c_void_p, c_uint32]
        s.Rayneo_Stop.restype = c_int
        s.Rayneo_Stop.argtypes = [c_void_p]
        s.Rayneo_PollEvent.restype = c_int
        s.Rayneo_PollEvent.argtypes = [c_void_p, POINTER(RAYNEO_Event), c_uint32]
        s.Rayneo_EnableImu.restype = c_int
        s.Rayneo_EnableImu.argtypes = [c_void_p]
        s.Rayneo_DisableImu.restype = c_int
        s.Rayneo_DisableImu.argtypes = [c_void_p]

        self.ctx = c_void_p()
        if s.Rayneo_Create(byref(self.ctx)) != 0:
            raise RuntimeError("Rayneo_Create failed")
        s.Rayneo_SetTargetVidPid(self.ctx, config.RAYNEO_VID, config.RAYNEO_PID)
        if s.Rayneo_Start(self.ctx, 0) != 0:
            s.Rayneo_Destroy(self.ctx)
            raise RuntimeError("Rayneo_Start failed (glasses not connected?)")
        s.Rayneo_EnableImu(self.ctx)
        self.connected = True
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

        # Ensure SDK cleanup on any exit (crash, Ctrl+C, sys.exit)
        import atexit
        atexit.register(self._cleanup_sdk)

    def _poll_loop(self):
        evt = RAYNEO_Event()

        while self._running:
            rc = self.sdk.Rayneo_PollEvent(self.ctx, byref(evt), 5)
            if rc != 0:
                continue
            if evt.type == EVT_DETACHED:
                self.connected = False
                continue
            if evt.type != EVT_IMU or not evt.data.imu.valid:
                continue

            s = evt.data.imu
            self._imu_count += 1
            gyro = np.array([s.gyroRad[0], s.gyroRad[1], s.gyroRad[2]])
            accel = np.array([s.acc[0], s.acc[1], s.acc[2]])

            # ── Initialize orientation from accel on first sample ──
            if not self._cf_initialized:
                ax, ay, az = accel
                self._raw_pitch = np.arctan2(-ax, np.sqrt(ay*ay + az*az))
                self._raw_roll = np.arctan2(ay, az)
                self._raw_yaw = 0.0
                with self._lock:
                    self._yaw = 0.0
                    self._pitch = self._raw_pitch
                    self._roll = self._raw_roll
                    self._ref_yaw = 0.0
                    self._ref_pitch = self._raw_pitch
                    self._ref_roll = self._raw_roll
                self._cf_initialized = True
                continue

            # ── Subtract bias ──
            gc = gyro - self._gyro_bias
            gc = np.where(np.abs(gc) > GYRO_DEADZONE, gc, 0.0)
            # Save gyro magnitude for movement detection
            self._last_gyro_mag = float(np.sqrt(np.sum(gc * gc)))

            # ── Compute dt ──
            dt = 0.002
            if self._last_tick > 0 and s.tick > self._last_tick:
                dt_t = (s.tick - self._last_tick) / 1000.0
                if 0.0001 < dt_t < 0.1:
                    dt = dt_t
            self._last_tick = s.tick

            gx, gy, gz = gc

            # ── Complementary filter ──
            pitch_gyro = self._raw_pitch + gx * dt
            roll_gyro = self._raw_roll + gz * dt
            yaw_gyro = self._raw_yaw + gy * dt

            ax, ay, az = accel
            g_norm = np.sqrt(ax*ax + ay*ay + az*az)
            if g_norm > 0.5:
                pitch_accel = np.arctan2(-ax, np.sqrt(ay*ay + az*az))
                roll_accel = np.arctan2(ay, az)
            else:
                pitch_accel = self._raw_pitch
                roll_accel = self._raw_roll

            CF_ALPHA = 0.999
            self._raw_pitch = CF_ALPHA * pitch_gyro + (1 - CF_ALPHA) * pitch_accel
            self._raw_roll = CF_ALPHA * roll_gyro + (1 - CF_ALPHA) * roll_accel
            self._raw_yaw = yaw_gyro * YAW_DECAY

            # ── Output update ──
            a = EMA_ALPHA
            with self._lock:
                self._yaw = self._raw_yaw
                self._pitch = a * self._raw_pitch + (1 - a) * self._pitch
                rd = (self._raw_roll - self._roll + np.pi) % (2*np.pi) - np.pi
                self._roll += rd * a

    def get_orientation(self):
        """Get raw (yaw, pitch, roll) in radians, relative to reference."""
        with self._lock:
            dy = (self._yaw - self._ref_yaw + np.pi) % (2*np.pi) - np.pi
            dp = self._pitch - self._ref_pitch
            dr = (self._roll - self._ref_roll + np.pi) % (2*np.pi) - np.pi
            return (dy, dp, dr)

    def recenter(self):
        with self._lock:
            self._ref_yaw = self._yaw
            self._ref_pitch = self._pitch
            self._ref_roll = self._roll

    @property
    def imu_count(self):
        return self._imu_count

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        self._cleanup_sdk()
        self.connected = False

    def _cleanup_sdk(self):
        """Release SDK resources. Safe to call multiple times."""
        if self.sdk and self.ctx:
            try:
                self.sdk.Rayneo_DisableImu(self.ctx)
            except Exception:
                pass
            try:
                self.sdk.Rayneo_Stop(self.ctx)
            except Exception:
                pass
            try:
                self.sdk.Rayneo_Destroy(self.ctx)
            except Exception:
                pass
            self.ctx = None

    def __del__(self):
        """Destructor: ensure SDK is released even on crash/GC."""
        self._running = False
        self._cleanup_sdk()
