from __future__ import annotations
from typing import Callable, Any
from collections.abc import Coroutine
import evdev
from evdev import ecodes, InputDevice, UInput
from evdev.events import InputEvent

EventCallback = Callable[[InputEvent, str], None]

_callbacks: list[EventCallback] = []
_keyboards: list[InputDevice[str]] = []
_mice: list[InputDevice[str]] = []
_uinput: UInput | None = None


def register(cb: EventCallback) -> None:
    _callbacks.append(cb)


def _normalize_key_name(code: int) -> str | None:
    try:
        names = ecodes.lookup(code, (ecodes.EV_KEY,))
        if names:
            return names[0] if isinstance(names[0], str) else names[0][0]
    except Exception:
        pass
    
    try:
        raw = ecodes.KEY[code]
        return raw if isinstance(raw, str) else raw[0]
    except (KeyError, IndexError, TypeError):
        pass
        
    return f"CODE_{code}"


def _fire_callbacks(event: InputEvent, key_name: str, device_name: str = "Unknown", value_override: int | None = None) -> None:
    from state import state
    val = value_override if value_override is not None else event.value
    type_code = getattr(event, 'type', ecodes.EV_KEY)
    type_name = ecodes.EV[type_code] if type_code in ecodes.EV else str(type_code)
    state["last_event"] = f"[{type_name}] {key_name} ({device_name})"
    
    # We allow EV_KEY and specifically mapped EV_ABS (pseudo-keys)
    # callbacks like MacroFeature.on_key_event check event.value
    for cb in _callbacks:
        try:
            if value_override is not None:
                # Create a minimal proxy object that has the expected attributes
                class MappedEvent:
                    def __init__(self, t, c, v):
                        self.type = t
                        self.code = c
                        self.value = v
                cb(MappedEvent(type_code, getattr(event, 'code', 0), val), key_name)
            else:
                cb(event, key_name)
        except Exception:
            pass


def setup_devices() -> None:
    global _uinput
    try:
        all_devices: list[InputDevice[str]] = [
            evdev.InputDevice(path) for path in evdev.list_devices()
        ]
        # Create virtual device for re-emission
        _uinput = UInput(name="DarkAges-Virtual-Input")
    except Exception:
        all_devices = []

    for d in all_devices:
        if d.name == "DarkAges-Virtual-Input":
            continue
            
        caps = d.capabilities()
        if ecodes.EV_KEY in caps or ecodes.EV_REL in caps or ecodes.EV_ABS in caps:
            ev_key_codes = []
            if ecodes.EV_KEY in caps:
                ev_key_codes = [c[0] if isinstance(c, tuple) else c for c in caps[ecodes.EV_KEY]]
            
            if ecodes.BTN_LEFT in ev_key_codes or ecodes.EV_REL in caps:
                _mice.append(d)
            else:
                _keyboards.append(d)


def toggle_suppression(enabled: bool) -> None:
    for kb in _keyboards:
        try:
            if enabled: kb.grab()
            else: kb.ungrab()
        except Exception:
            pass


async def _read_device(device: InputDevice[str]) -> None:
    from state import state
    axis_states: dict[int, int] = {}
    THRESHOLD = 16000

    try:
        async for event in device.async_read_loop():
            if not state["running"]: break

            suppressed = False
            
            if event.type == ecodes.EV_KEY:
                key_name = _normalize_key_name(event.code)
                if key_name:
                    if state["suppress_triggers"] and state["active"]:
                        is_trigger = any(m["trigger"] == key_name for m in state["macros"])
                        if is_trigger:
                            suppressed = True
                    
                    _fire_callbacks(event, key_name, device.name)

            elif event.type == ecodes.EV_ABS:
                # Always report raw ABS changes to the footer for debugging
                old_val = axis_states.get(event.code, 0)
                if abs(event.value - old_val) > 10: # Small noise gate
                    _fire_callbacks(event, f"ABS_{event.code}={event.value}", device.name)

                # Handle DPAD (Hats)
                if event.code == ecodes.ABS_HAT0X:
                    old = axis_states.get(event.code, 0)
                    if event.value == -1: _fire_callbacks(event, "BTN_DPAD_LEFT", device.name, value_override=1)
                    elif event.value == 1: _fire_callbacks(event, "BTN_DPAD_RIGHT", device.name, value_override=1)
                    elif event.value == 0:
                        if old == -1: _fire_callbacks(event, "BTN_DPAD_LEFT", device.name, value_override=0)
                        elif old == 1: _fire_callbacks(event, "BTN_DPAD_RIGHT", device.name, value_override=0)
                    axis_states[event.code] = event.value
                elif event.code == ecodes.ABS_HAT0Y:
                    old = axis_states.get(event.code, 0)
                    if event.value == -1: _fire_callbacks(event, "BTN_DPAD_UP", device.name, value_override=1)
                    elif event.value == 1: _fire_callbacks(event, "BTN_DPAD_DOWN", device.name, value_override=1)
                    elif event.value == 0:
                        if old == -1: _fire_callbacks(event, "BTN_DPAD_UP", device.name, value_override=0)
                        elif old == 1: _fire_callbacks(event, "BTN_DPAD_DOWN", device.name, value_override=0)
                    axis_states[event.code] = event.value
                
                # Handle Joystick Axes
                elif event.code in (ecodes.ABS_X, ecodes.ABS_Y, ecodes.ABS_RX, ecodes.ABS_RY):
                    axis_map = {ecodes.ABS_X: "LX", ecodes.ABS_Y: "LY", ecodes.ABS_RX: "RX", ecodes.ABS_RY: "RY"}
                    axis_name = axis_map[event.code]
                    old = axis_states.get(event.code, 0)
                    
                    if event.value > THRESHOLD and old <= THRESHOLD:
                        _fire_callbacks(event, f"BTN_JOY_{axis_name}_POS", device.name, value_override=1)
                    elif event.value <= THRESHOLD and old > THRESHOLD:
                        _fire_callbacks(event, f"BTN_JOY_{axis_name}_POS", device.name, value_override=0)
                    
                    if event.value < -THRESHOLD and old >= -THRESHOLD:
                        _fire_callbacks(event, f"BTN_JOY_{axis_name}_NEG", device.name, value_override=1)
                    elif event.value >= -THRESHOLD and old < -THRESHOLD:
                        _fire_callbacks(event, f"BTN_JOY_{axis_name}_NEG", device.name, value_override=0)
                    
                    axis_states[event.code] = event.value
                
                # Handle Analog Triggers
                elif event.code in (ecodes.ABS_Z, ecodes.ABS_RZ, ecodes.ABS_GAS, ecodes.ABS_BRAKE):
                    is_left = event.code in (ecodes.ABS_Z, ecodes.ABS_BRAKE)
                    axis_name = "L2" if is_left else "R2"
                    old = axis_states.get(event.code, 0)
                    
                    # Use a low threshold (e.g. 10%) for trigger 'press'
                    # Assuming 0-255 or 0-1023
                    T_THRESH = 50 
                    if event.value > T_THRESH and old <= T_THRESH:
                        _fire_callbacks(event, f"BTN_{axis_name}", device.name, value_override=1)
                    elif event.value <= T_THRESH and old > T_THRESH:
                        _fire_callbacks(event, f"BTN_{axis_name}", device.name, value_override=0)
                    axis_states[event.code] = event.value

                axis_states[event.code] = event.value

            # Re-emit only if suppression is active (keyboard is grabbed)
            if _uinput and state["suppress_triggers"] and not suppressed and device in _keyboards:
                if event.type == ecodes.EV_SYN:
                    # Write the hardware sync event data first, then flush the packet
                    _uinput.write_event(event)
                    _uinput.syn()
                elif event.type != ecodes.EV_ABS:
                    # Pass normal key/relative events through without forcing an early flush
                    _uinput.write_event(event)

    except Exception:
        pass
    finally:
        try: device.ungrab()
        except: pass


def get_device_counts() -> tuple[int, int]:
    return len(_keyboards), len(_mice)


def get_device_names() -> list[str]:
    return [d.name for d in _keyboards + _mice]


def get_read_tasks() -> list[Coroutine[Any, Any, None]]:
    return [_read_device(d) for d in _keyboards + _mice]
