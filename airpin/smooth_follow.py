"""
Smooth Follow for AR head tracking.

Simple approach:
- Track head 1:1 (no lag, no delay)
- When head is STILL for 2+ seconds, slowly correct accumulated drift
- Output is frozen when head is still (no jitter from micro-movements)

This gives instant response to intentional head turns while masking
gyroscope drift during stationary periods.
"""

import math
import time


# Hysteresis thresholds for movement detection (rad/s)
# Start tracking: gyro must exceed this (filters pulse/sway ~1-2 deg/s)
MOVE_START_RAD = 0.052  # ~3.0 deg/s
# Stop tracking: gyro must drop below this (lower = smoother stop)
MOVE_STOP_RAD = 0.015   # ~0.9 deg/s

# How long head must be still before drift correction starts
STILL_TIME_SEC = 2.0

# Drift correction speed (radians per second toward zero offset)
DRIFT_CORRECTION_SPEED = 0.5  # deg/sec


# Consecutive frames to confirm state change
MOVE_START_CONFIRM = 2   # frames above START threshold to begin tracking
MOVE_STOP_CONFIRM = 15   # frames below STOP threshold to freeze

class SmoothFollow:
    def __init__(self):
        self._ref_yaw = 0.0
        self._output = 0.0
        self._is_moving = False
        self._still_start = 0.0
        self._last_raw = 0.0
        self._move_count = 0       # consecutive frames above threshold

    def reset(self, current_yaw=0.0):
        self._ref_yaw = current_yaw
        self._output = 0.0
        self._is_moving = False
        self._still_start = time.monotonic()
        self._last_raw = current_yaw
        self._move_count = 0

    def update(self, raw_yaw, dt_ms, gyro_magnitude=0.0):
        """
        raw_yaw: current head yaw from IMU (radians, relative to reference)
        dt_ms: milliseconds since last update
        gyro_magnitude: current gyro speed (rad/s) — used to detect movement

        Returns: yaw offset to apply to display (radians)
        """
        now = time.monotonic()

        # Hysteresis movement detection:
        # Enter MOVE at high threshold (filters noise)
        # Stay in MOVE until low threshold (allows slow fine adjustments)
        if not self._is_moving:
            if gyro_magnitude > MOVE_START_RAD:
                self._move_count += 1
                if self._move_count >= MOVE_START_CONFIRM:
                    self._is_moving = True
                    self._move_count = 0
            else:
                self._move_count = 0
        else:
            if gyro_magnitude < MOVE_STOP_RAD:
                self._move_count += 1
                if self._move_count >= MOVE_STOP_CONFIRM:
                    self._output = self._wrap(raw_yaw - self._ref_yaw)
                    self._is_moving = False
                    self._still_start = now
                    self._move_count = 0
            else:
                self._move_count = 0
                self._still_start = now

        if self._is_moving:
            # MOVING: track 1:1, no lag
            self._output = self._wrap(raw_yaw - self._ref_yaw)
        else:
            # STILL: output is frozen (no jitter)
            still_duration = now - self._still_start

            if still_duration > STILL_TIME_SEC:
                # Drift correction: slowly move ref toward current raw_yaw
                # This makes the output gradually return to 0 (correcting drift)
                drift = self._wrap(raw_yaw - self._ref_yaw) - self._output
                if abs(drift) > math.radians(0.1):  # only correct if drift > 0.1 deg
                    correction = math.copysign(
                        min(abs(drift), math.radians(DRIFT_CORRECTION_SPEED) * dt_ms / 1000),
                        drift
                    )
                    self._ref_yaw += correction
                    # Output stays frozen — correction is invisible

        self._last_raw = raw_yaw
        return self._output

    @staticmethod
    def _wrap(angle):
        return (angle + math.pi) % (2 * math.pi) - math.pi
