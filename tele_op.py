#!/usr/bin/env python3
"""
Tele-op controller for Waveshare RasRover + Jetson Orin Nano
- Reads gamepad input via a wireless USB dongle (using inputs or pygame)
- Translates joystick axes to differential drive wheel speeds
- Sends JSON commands over USB serial to the RasRover ESP32 base
"""

import json
import time
import threading
import serial
import sys

# ─── Try to import 'inputs' (pip install inputs), fallback to pygame ───────────
try:
    from inputs import get_gamepad, UnpluggedError
    USE_INPUTS = True
except ImportError:
    USE_INPUTS = False

try:
    import pygame
    USE_PYGAME = True
except ImportError:
    USE_PYGAME = False

# ─── Configuration ─────────────────────────────────────────────────────────────

SERIAL_PORT   = "/dev/ttyACM0"   # Change if needed (check: ls /dev/ttyUSB*)
BAUD_RATE     = 115200
SEND_RATE_HZ  = 20               # Command send rate


# Axis deadzone — ignore joystick noise below this threshold
DEADZONE      = 0.08

# Gamepad axis indices (standard for most USB gamepads / Xbox-style)
# inputs library: ABS_Y = left stick vertical, ABS_RX = right stick horizontal
# pygame: axis 1 = left Y, axis 2 or 3 = right X (varies by controller)
LEFT_Y_AXIS  = "ABS_Y"         # Forward / backward
LEFT_X_AXIS  = "ABS_X"        # Angular clockwise / counterclockwise 

MAX_LINEAR  = 0.2   # m/s, forward/backward
MAX_ANGULAR = 2.0   # rad/s, left/right turn

SCURVE_ALPHA = 0.7   # 0.0 = linear, 1.0 = full cubic S-curve

# ─── Shared state ──────────────────────────────────────────────────────────────

class RobotState:
    def __init__(self):
        self.linear  = 0.0
        self.angular = 0.0
        self.running = True
        self.lock    = threading.Lock()

state = RobotState()


# ─── Serial communication ──────────────────────────────────────────────────────

class RasRoverSerial:
    """Handles serial communication with the RasRover ESP32 base."""

    def __init__(self, port: str, baud: int):
        self.ser = serial.Serial(
            port,
            baudrate=baud,
            timeout=1,
            dsrdtr=None
        )
        self.ser.setRTS(False)
        self.ser.setDTR(False)
        print(f"[Serial] Connected to {port} @ {baud} baud")

        # Background thread to read and print feedback from the base
        # self._reader = threading.Thread(target=self._read_loop, daemon=True)
        # self._reader.start()

    def send_command(self, cmd: dict):
        """Serialize a dict to JSON and write it over serial."""
        payload = json.dumps(cmd, separators=(',', ':')) + '\n'
        self.ser.write(payload.encode('utf-8'))

    def send_motion(self, linear: float, angular: float):
        """Send a velocity command using T=13 (X=linear, Z=angular)."""
        self.send_command({"T": 13, "X": linear, "Z": angular})

    def stop(self):
        self.send_motion(0.0, 0.0)

    def close(self):
        self.stop()
        time.sleep(0.1)
        self.ser.close()

    def _read_loop(self):
        """Read feedback lines from the ESP32 base."""
        while True:
            try:
                line = self.ser.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    print(f"[Base feedback] {line}")
            except Exception:
                break


# ─── Joystick / gamepad input ──────────────────────────────────────────────────

def apply_deadzone(value: float, deadzone: float) -> float:
    if abs(value) < deadzone:
        return 0.0
    # Re-scale so output is still 0..1 at extremes
    sign = 1.0 if value > 0 else -1.0
    return sign * (abs(value) - deadzone) / (1.0 - deadzone)

def s_curve(x: float) -> float:
    """
    Maps x in [-1, 1] to [-1, 1] with an S-curve response.
    Uses a weighted blend of linear and cubic:
      - Pure linear (alpha=0.0): no shaping, original behavior
      - Pure cubic  (alpha=1.0): strong S-curve, very gentle near center
    Tune SCURVE_ALPHA between 0.0 and 1.0 to taste.
    """
    return (1.0 - SCURVE_ALPHA) * x + SCURVE_ALPHA * (x ** 3)

def joystick_to_cmd_vel(raw_y: float, raw_x: float):
    """
    Convert raw 0-255 axis values to (linear, angular) velocities.
    raw_y: 0 = full up, 127 = center, 255 = full down
    raw_x: 0 = full left, 127 = center, 255 = full right
    """
    # Re-center and normalize to -1.0 .. +1.0
    norm_y = (raw_y - 127.5) / 127.5   # positive = down
    norm_x = (raw_x - 127.5) / 127.5   # positive = right

    # Apply deadzone
    norm_y = apply_deadzone(norm_y, DEADZONE)
    norm_x = apply_deadzone(norm_x, DEADZONE)

    # Apply S-curve shaping before scaling to physical units
    norm_y = s_curve(norm_y)
    norm_x = s_curve(norm_x)

    # Map to physical units and invert axes to match desired directions:
    # Up (norm_y negative) → positive linear; Left (norm_x negative) → positive angular
    linear  = -norm_y * MAX_LINEAR
    angular = -norm_x * MAX_ANGULAR

    return round(linear, 3), round(angular, 3)


# ── Option A: 'inputs' library (recommended for headless Jetson) ───────────────

def gamepad_loop_inputs():
    """Read left joystick only; update shared linear/angular state."""
    raw = {"ABS_Y": 127.0, "ABS_X": 127.0}  # start at center

    print("[Gamepad] Waiting for controller events (inputs library) ...")
    while state.running:
        try:
            events = get_gamepad()
            for event in events:
                if event.ev_type == 'Absolute' and event.code in raw:
                    raw[event.code] = float(event.state)

            linear, angular = joystick_to_cmd_vel(raw["ABS_Y"], raw["ABS_X"])

            with state.lock:
                state.linear  = linear
                state.angular = angular

        except UnpluggedError:
            print("[Gamepad] Controller unplugged! Stopping robot.")
            with state.lock:
                state.linear  = 0.0
                state.angular = 0.0
            time.sleep(1.0)

        except Exception as e:
            print(f"[Gamepad] Error: {e}")
            time.sleep(0.1)


# ── Option B: pygame (if you have a display / virtual framebuffer) ─────────────

def gamepad_loop_pygame():
    """Read gamepad events using pygame."""
    pygame.init()
    pygame.joystick.init()

    if pygame.joystick.get_count() == 0:
        print("[Gamepad] No joystick found!")
        state.running = False
        return

    joy = pygame.joystick.Joystick(0)
    joy.init()
    print(f"[Gamepad] Using: {joy.get_name()}")

    PYGAME_LEFT_Y  = 1   # Left stick vertical   (adjust for your controller)
    PYGAME_RIGHT_X = 3   # Right stick horizontal (adjust for your controller)

    while state.running:
        pygame.event.pump()

        fwd  = -joy.get_axis(PYGAME_LEFT_Y)   # Invert Y axis
        turn =  joy.get_axis(PYGAME_RIGHT_X)

        left_spd, right_spd = joystick_to_tank(fwd, turn)

        with state.lock:
            state.left_speed  = left_spd
            state.right_speed = right_spd

        time.sleep(1.0 / 60.0)


# ─── Serial sender loop ────────────────────────────────────────────────────────

def serial_sender_loop(rover: RasRoverSerial):
    period = 1.0 / SEND_RATE_HZ
    print(f"[Sender] Sending commands at {SEND_RATE_HZ} Hz ...")
    while state.running:
        with state.lock:
            L = state.linear
            A = state.angular
        rover.send_motion(L, A)
        time.sleep(period)


# ─── Entry point ───────────────────────────────────────────────────────────────

def main():
    print("=== RasRover Tele-op ===")
    print(f"  Serial port : {SERIAL_PORT}")
    print(f"  Max Linear   : {MAX_LINEAR} m/s")
    print(f"  Max Angular  : {MAX_ANGULAR} rad/s")
    print("  Press Ctrl+C to stop.\n")

    # Open serial connection to the RasRover base
    try:
        rover = RasRoverSerial(SERIAL_PORT, BAUD_RATE)
    except serial.SerialException as e:
        print(f"[Error] Cannot open serial port: {e}")
        print("  Tip: Check 'ls /dev/ttyACM0' and update SERIAL_PORT.")
        sys.exit(1)

    # Choose input backend
    if USE_INPUTS:
        input_thread = threading.Thread(target=gamepad_loop_inputs, daemon=True)
    elif USE_PYGAME:
        input_thread = threading.Thread(target=gamepad_loop_pygame, daemon=True)
    else:
        print("[Error] Install either 'inputs' or 'pygame':")
        print("  pip install inputs      # recommended for headless Jetson")
        print("  pip install pygame")
        rover.close()
        sys.exit(1)

    input_thread.start()

    # Run the serial sender on the main thread
    try:
        serial_sender_loop(rover)
    except KeyboardInterrupt:
        print("\n[Main] Ctrl+C received — stopping robot.")
    finally:
        state.running = False
        rover.close()
        print("[Main] Shutdown complete.")


if __name__ == "__main__":
    main()