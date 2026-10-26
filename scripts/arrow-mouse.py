#!/usr/bin/env python3

import glob
import math
import os
import subprocess
import threading
import time

from evdev import InputDevice, UInput, ecodes, list_devices

ARROWS = {
    ecodes.KEY_UP,
    ecodes.KEY_DOWN,
    ecodes.KEY_LEFT,
    ecodes.KEY_RIGHT,
}
RIGHT_SHIFT = ecodes.KEY_RIGHTSHIFT

FPS = 120
MAX_SPEED = 1600.0
ACCELERATION = 4500.0

DOUBLE_TAP_WINDOW = 0.32
SCROLL_TICKS_PER_SECOND = 12.0
LEFT_TAP_WINDOW = 0.30
LEFT_HOLD_THRESHOLD = 0.18

stop_event = threading.Event()
keyboard_failed = threading.Event()
state_lock = threading.RLock()
keyboard_out_lock = threading.Lock()
pointer_lock = threading.Lock()

source = None
keyboard_out = None
pointer_out = None

state = {
    "mouse": True,
    "pressed_arrows": set(),
    "forwarded_arrows": set(),
    "right_shift_down": False,
    "right_shift_forwarded": False,
    "right_shift_chord": False,
    "right_shift_double_candidate": False,
    "right_shift_pressed_at": None,
    "pending_shift_tap": None,
    "caps_click_mode": False,
}


def device_properties(path):
    result = subprocess.run(
        [
            "udevadm", "info",
            "--query=property",
            "--name", path,
        ],
        capture_output=True,
        text=True,
        timeout=1,
    )

    if result.returncode != 0:
        return None

    props = {}
    for line in result.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            props[key] = value.strip().strip('"')

    return props


def detect_external_mouse():
    candidates = []

    for path in glob.glob("/dev/input/event*"):
        node = os.path.basename(path)
        sys_path = os.path.realpath(
            f"/sys/class/input/{node}/device"
        ).lower()

        if "/devices/virtual/input/" in sys_path:
            continue

        if not any(part in sys_path for part in (
            "/usb", "/bluetooth/", "/uhid/"
        )):
            continue

        candidates.append((path, sys_path))

    if not candidates:
        return False

    queried = False

    for path, sys_path in candidates:
        try:
            props = device_properties(path)
        except (OSError, subprocess.TimeoutExpired):
            continue

        if props is None:
            continue

        queried = True

        is_usb = (
            "/usb" in sys_path
            and props.get("ID_BUS", "usb") == "usb"
        )

        is_bluetooth = (
            "/bluetooth/" in sys_path
            or (
                "/uhid/" in sys_path
                and props.get("ID_BUS") == "bluetooth"
            )
        )

        if not (is_usb or is_bluetooth):
            continue

        if props.get("ID_INPUT_MOUSE") != "1":
            continue

        if props.get("ID_INPUT_TOUCHPAD") == "1":
            continue

        if props.get("ID_INPUT_POINTINGSTICK") == "1":
            continue

        return True

    return False if queried else None


def find_keyd_keyboard():
    for path in list_devices():
        try:
            dev = InputDevice(path)
            keys = dev.capabilities(absinfo=False).get(
                ecodes.EV_KEY, []
            )

            if (
                dev.name == "keyd virtual keyboard"
                and ecodes.KEY_UP in keys
            ):
                return dev

            dev.close()
        except OSError:
            continue

    raise RuntimeError("No se encontró el teclado virtual de keyd.")


def emit_key(code, value):
    with keyboard_out_lock:
        keyboard_out.write(ecodes.EV_KEY, code, value)
        keyboard_out.syn()


def emit_scroll(vertical=0, horizontal=0):
    with pointer_lock:
        if vertical:
            pointer_out.write(
                ecodes.EV_REL, ecodes.REL_WHEEL, vertical
            )

        if horizontal:
            pointer_out.write(
                ecodes.EV_REL, ecodes.REL_HWHEEL, horizontal
            )

        if vertical or horizontal:
            pointer_out.syn()


def emit_click(button):
    with pointer_lock:
        pointer_out.write(ecodes.EV_KEY, button, 1)
        pointer_out.syn()
        time.sleep(0.012)
        pointer_out.write(ecodes.EV_KEY, button, 0)
        pointer_out.syn()


def emit_middle_click():
    with pointer_lock:
        pointer_out.write(
            ecodes.EV_KEY, ecodes.BTN_MIDDLE, 1
        )
        pointer_out.syn()

        time.sleep(0.012)

        pointer_out.write(
            ecodes.EV_KEY, ecodes.BTN_MIDDLE, 0
        )
        pointer_out.syn()


def emit_left_button(pressed):
    with pointer_lock:
        pointer_out.write(ecodes.EV_KEY, ecodes.BTN_LEFT, int(pressed))
        pointer_out.syn()


class LeftArrowGesture:
    """Tres toques alternan arrastre; uno/dos conservan sus clicks."""

    def __init__(self, click, button):
        self.click = click
        self.button = button
        self.active = False
        self.down_at = None
        self.consumed = False
        self.tap_count = 0
        self.pending_clicks = 0
        self.deadline = None

    def flush_clicks(self):
        count = self.pending_clicks
        self.pending_clicks = 0
        for _ in range(count):
            self.click()

    def interrupt(self):
        # Resolver clicks antes de otra tecla conserva el orden de acciones.
        self.flush_clicks()
        self.tap_count = 0
        self.deadline = None
        if self.down_at is not None:
            self.consumed = True

    def reset(self):
        if self.active:
            self.button(False)
        self.active = False
        self.down_at = None
        self.consumed = False
        self.tap_count = 0
        self.pending_clicks = 0
        self.deadline = None

    def advance(self, now):
        if (
            self.down_at is not None
            and not self.consumed
            and now - self.down_at >= LEFT_HOLD_THRESHOLD
        ):
            # Mantener una tecla nunca cuenta como varios toques.
            self.flush_clicks()
            self.tap_count = 0
            self.deadline = None
            self.consumed = True

        if self.deadline is not None and now > self.deadline:
            self.flush_clicks()
            self.tap_count = 0
            self.deadline = None

    def handle(self, value, now):
        self.advance(now)

        if value == 1:
            if self.down_at is not None:
                return
            self.down_at = now
            self.consumed = False

            if self.tap_count == 2:
                # Consumir los tres toques sin enviar clicks previos a la app.
                self.pending_clicks = 0
                self.tap_count = 0
                self.deadline = None
                self.button(not self.active)
                self.active = not self.active
                self.consumed = True
                return

            if not self.active:
                self.pending_clicks += 1
            self.deadline = now + LEFT_TAP_WINDOW

        elif value == 0 and self.down_at is not None:
            if not self.consumed:
                self.tap_count += 1
            self.down_at = None
            self.consumed = False

    def moving_left(self, now):
        # Con el botón sostenido, mover al pulsar igual que las otras flechas.
        return self.active and self.down_at is not None


left_gesture = LeftArrowGesture(
    lambda: emit_click(ecodes.BTN_LEFT), emit_left_button
)


def keyboard_listener():
    print(f"Escuchando: {source.name}", flush=True)

    for event in source.read_loop():
        if stop_event.is_set():
            break

        if event.type != ecodes.EV_KEY:
            continue

        code = event.code
        value = event.value
        now = time.monotonic()
        do_middle_click = False

        with state_lock:
            mouse_connected = state["mouse"]
            left_gesture.advance(now)

            if code != ecodes.KEY_LEFT and value == 1:
                left_gesture.interrupt()

            # Caps Lock conserva su función de mayúsculas y activa el modo de clics.
            if code == ecodes.KEY_CAPSLOCK:
                if value == 1:
                    state["caps_click_mode"] = not state["caps_click_mode"]
                    left_gesture.reset()
                    state["pressed_arrows"].discard(ecodes.KEY_LEFT)
                emit_key(code, value)
                continue

            # Flechas: clics con Caps Lock; normales con mouse externo.
            if code in ARROWS:
                if (
                    not mouse_connected
                    and state["caps_click_mode"]
                    and code == ecodes.KEY_LEFT
                ):
                    state["pressed_arrows"].discard(code)
                    state["right_shift_chord"] = True
                    state["right_shift_double_candidate"] = False
                    state["pending_shift_tap"] = None
                    left_gesture.handle(value, now)
                    if value == 1 and state["pressed_arrows"]:
                        left_gesture.interrupt()
                    continue

                if (
                    not mouse_connected
                    and state["caps_click_mode"]
                    and not left_gesture.active
                    and code == ecodes.KEY_RIGHT
                ):
                    state["pressed_arrows"].discard(code)
                    state["right_shift_chord"] = True
                    state["right_shift_double_candidate"] = False
                    state["pending_shift_tap"] = None

                    # Solo un clic por pulsación, sin repetir al mantener.
                    if value == 1:
                        emit_click(ecodes.BTN_RIGHT)

                    continue

                if value in (1, 2):
                    state["pressed_arrows"].add(code)
                elif value == 0:
                    state["pressed_arrows"].discard(code)

                if (
                    not mouse_connected
                    and state["right_shift_down"]
                ):
                    state["right_shift_chord"] = True
                    state["right_shift_double_candidate"] = False
                    state["pending_shift_tap"] = None

                if mouse_connected:
                    if value == 1:
                        if code not in state["forwarded_arrows"]:
                            emit_key(code, 1)
                            state["forwarded_arrows"].add(code)

                    elif value == 2:
                        if code in state["forwarded_arrows"]:
                            emit_key(code, 2)

                    elif value == 0:
                        if code in state["forwarded_arrows"]:
                            emit_key(code, 0)
                            state["forwarded_arrows"].discard(code)

                continue

            # Shift derecho tiene comportamiento especial sin mouse.
            if code == RIGHT_SHIFT:
                if mouse_connected:
                    if value == 1:
                        if not state["right_shift_forwarded"]:
                            emit_key(RIGHT_SHIFT, 1)
                            state["right_shift_forwarded"] = True

                        state["right_shift_down"] = True
                        state["right_shift_pressed_at"] = now

                    elif value == 2:
                        if state["right_shift_forwarded"]:
                            emit_key(RIGHT_SHIFT, 2)

                    elif value == 0:
                        if state["right_shift_forwarded"]:
                            emit_key(RIGHT_SHIFT, 0)

                        state["right_shift_forwarded"] = False
                        state["right_shift_down"] = False
                        state["right_shift_pressed_at"] = None
                        state["right_shift_chord"] = False
                        state["right_shift_double_candidate"] = False
                        state["pending_shift_tap"] = None

                else:
                    if value == 1:
                        state["right_shift_down"] = True
                        state["right_shift_pressed_at"] = now
                        state["right_shift_chord"] = False

                        pending = state["pending_shift_tap"]

                        if (
                            pending is not None
                            and now - pending <= DOUBLE_TAP_WINDOW
                        ):
                            state["right_shift_double_candidate"] = True
                            state["pending_shift_tap"] = None
                        else:
                            state["right_shift_double_candidate"] = False
                            state["pending_shift_tap"] = None

                        if state["pressed_arrows"]:
                            state["right_shift_chord"] = True
                            state["right_shift_double_candidate"] = False

                    elif value == 0:
                        started = state["right_shift_pressed_at"]
                        duration = (
                            now - started if started is not None else 999
                        )

                        if state["right_shift_forwarded"]:
                            emit_key(RIGHT_SHIFT, 0)
                            state["right_shift_forwarded"] = False
                            state["pending_shift_tap"] = None

                        elif (
                            state["right_shift_double_candidate"]
                            and not state["right_shift_chord"]
                            and duration <= DOUBLE_TAP_WINDOW
                        ):
                            do_middle_click = True
                            state["pending_shift_tap"] = None

                        elif (
                            not state["right_shift_chord"]
                            and not state["right_shift_double_candidate"]
                            and duration <= DOUBLE_TAP_WINDOW
                        ):
                            state["pending_shift_tap"] = now

                        else:
                            state["pending_shift_tap"] = None

                        state["right_shift_down"] = False
                        state["right_shift_pressed_at"] = None
                        state["right_shift_chord"] = False
                        state["right_shift_double_candidate"] = False

                if do_middle_click:
                    emit_middle_click()

                continue

            # Si se usa Shift derecho con letras, conservar el
            # comportamiento normal de escritura y atajos.
            if (
                not mouse_connected
                and state["right_shift_down"]
                and not state["right_shift_forwarded"]
            ):
                state["right_shift_chord"] = True
                state["right_shift_double_candidate"] = False
                state["pending_shift_tap"] = None

                emit_key(RIGHT_SHIFT, 1)
                state["right_shift_forwarded"] = True

            # Resto del teclado: siempre se reenvía normalmente.
            emit_key(code, value)


def keyboard_worker():
    try:
        keyboard_listener()
    finally:
        # Si desaparece la entrada, el hilo principal suelta el botón y sale.
        if not stop_event.is_set():
            keyboard_failed.set()
            stop_event.set()


def mouse_watcher():
    while not stop_event.is_set():
        detected = detect_external_mouse()

        # Ante un fallo, no secuestrar las flechas.
        if detected is None:
            detected = True

        changed = False

        with state_lock:
            if detected != state["mouse"]:
                changed = True
                left_gesture.reset()
                state["mouse"] = detected
                state["pending_shift_tap"] = None
                state["right_shift_double_candidate"] = False

                if detected:
                    for code in state["pressed_arrows"]:
                        if code not in state["forwarded_arrows"]:
                            emit_key(code, 1)
                            state["forwarded_arrows"].add(code)

                    if (
                        state["right_shift_down"]
                        and not state["right_shift_forwarded"]
                    ):
                        emit_key(RIGHT_SHIFT, 1)
                        state["right_shift_forwarded"] = True

                else:
                    for code in list(state["forwarded_arrows"]):
                        emit_key(code, 0)

                    state["forwarded_arrows"].clear()

                    if state["right_shift_forwarded"]:
                        emit_key(RIGHT_SHIFT, 0)
                        state["right_shift_forwarded"] = False

                    if state["right_shift_down"]:
                        state["right_shift_chord"] = True

        if changed:
            print(
                "Mouse conectado: controles normales."
                if detected
                else "Sin mouse: flechas controlan el cursor.",
                flush=True,
            )

        stop_event.wait(0.6)


def movement_loop():
    speed = 0.0
    remainder_x = 0.0
    remainder_y = 0.0
    scroll_accumulator = 0.0
    previous = time.perf_counter()
    frame_time = 1.0 / FPS

    while not stop_event.is_set():
        started = time.perf_counter()
        dt = min(started - previous, 0.05)
        previous = started

        with state_lock:
            now = time.monotonic()
            left_gesture.advance(now)
            mouse_connected = state["mouse"]
            keys = state["pressed_arrows"].copy()
            right_shift = state["right_shift_down"]

            if not mouse_connected and state["caps_click_mode"]:
                keys.discard(ecodes.KEY_LEFT)
                if left_gesture.active:
                    if left_gesture.moving_left(now):
                        keys.add(ecodes.KEY_LEFT)
                else:
                    keys.discard(ecodes.KEY_RIGHT)

            pending = state["pending_shift_tap"]
            if (
                pending is not None
                and started - pending > DOUBLE_TAP_WINDOW
            ):
                state["pending_shift_tap"] = None

        if mouse_connected:
            speed = 0.0
            remainder_x = remainder_y = 0.0
            scroll_accumulator = 0.0

        elif right_shift:
            speed = 0.0
            remainder_x = remainder_y = 0.0

            vertical = (
                int(ecodes.KEY_UP in keys)
                - int(ecodes.KEY_DOWN in keys)
            )
            horizontal = (
                int(ecodes.KEY_RIGHT in keys)
                - int(ecodes.KEY_LEFT in keys)
            )

            if vertical or horizontal:
                scroll_accumulator += dt * SCROLL_TICKS_PER_SECOND

                while scroll_accumulator >= 1.0:
                    emit_scroll(vertical, horizontal)
                    scroll_accumulator -= 1.0
            else:
                scroll_accumulator = 0.0

        else:
            scroll_accumulator = 0.0

            dx = (
                int(ecodes.KEY_RIGHT in keys)
                - int(ecodes.KEY_LEFT in keys)
            )
            dy = (
                int(ecodes.KEY_DOWN in keys)
                - int(ecodes.KEY_UP in keys)
            )

            if dx or dy:
                magnitude = math.hypot(dx, dy)

                speed = min(
                    MAX_SPEED,
                    speed + ACCELERATION * dt,
                )

                move_x = dx / magnitude * speed * dt + remainder_x
                move_y = dy / magnitude * speed * dt + remainder_y

                px = math.trunc(move_x)
                py = math.trunc(move_y)

                remainder_x = move_x - px
                remainder_y = move_y - py

                with pointer_lock:
                    if px:
                        pointer_out.write(
                            ecodes.EV_REL, ecodes.REL_X, px
                        )

                    if py:
                        pointer_out.write(
                            ecodes.EV_REL, ecodes.REL_Y, py
                        )

                    if px or py:
                        pointer_out.syn()
            else:
                speed = 0.0
                remainder_x = remainder_y = 0.0

        elapsed = time.perf_counter() - started
        stop_event.wait(max(0.0, frame_time - elapsed))


def main():
    global source, keyboard_out, pointer_out

    source = find_keyd_keyboard()
    try:
        state["caps_click_mode"] = ecodes.LED_CAPSL in source.leds()
    except OSError:
        pass
    key_codes = source.capabilities(
        absinfo=False
    ).get(ecodes.EV_KEY, [])

    detected = detect_external_mouse()
    state["mouse"] = True if detected is None else detected

    keyboard_out = UInput(
        {ecodes.EV_KEY: key_codes},
        name="Arrow Mouse Keyboard Proxy",
        bustype=0x06,
        vendor=0xCAFE,
        product=0xFEED,
        version=1,
        phys="virtual/arrow-mouse-keyboard-proxy",
    )

    pointer_out = UInput(
        {
            ecodes.EV_KEY: [
                ecodes.BTN_LEFT,
                ecodes.BTN_RIGHT,
                ecodes.BTN_MIDDLE,
            ],
            ecodes.EV_REL: [
                ecodes.REL_X,
                ecodes.REL_Y,
                ecodes.REL_WHEEL,
                ecodes.REL_HWHEEL,
            ],
        },
        name="Arrow Mouse Fallback",
        bustype=0x06,
        vendor=0xCAFE,
        product=0xF00D,
        version=1,
        phys="virtual/arrow-mouse-fallback",
    )

    try:
        source.grab()

        print(
            "Mouse externo detectado: controles normales."
            if state["mouse"]
            else "Sin mouse: flechas controlan el cursor.",
            flush=True,
        )

        threading.Thread(
            target=keyboard_worker,
            daemon=True,
        ).start()

        threading.Thread(
            target=mouse_watcher,
            daemon=True,
        ).start()

        print("Controlador activo. Ctrl+C para salir.", flush=True)
        movement_loop()
        if keyboard_failed.is_set():
            raise RuntimeError("Se perdió la entrada del teclado; reiniciando.")

    except KeyboardInterrupt:
        print("\nControlador detenido.", flush=True)

    finally:
        stop_event.set()

        with state_lock:
            try:
                left_gesture.reset()
            except OSError:
                pass
            for code in list(state["forwarded_arrows"]):
                try:
                    emit_key(code, 0)
                except OSError:
                    pass

            state["forwarded_arrows"].clear()

            if state["right_shift_forwarded"]:
                try:
                    emit_key(RIGHT_SHIFT, 0)
                except OSError:
                    pass

            state["right_shift_forwarded"] = False

        try:
            source.ungrab()
        except (OSError, AttributeError):
            pass

        for device in (source, keyboard_out, pointer_out):
            if device is not None:
                try:
                    device.close()
                except OSError:
                    pass


if __name__ == "__main__":
    main()
