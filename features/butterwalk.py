from __future__ import annotations
import asyncio
import subprocess
from evdev.events import InputEvent
from state import state

KEY_MAP: dict[str, str] = {
    "KEY_SPACE": "space",
    "KEY_LEFT": "Left",
    "KEY_RIGHT": "Right",
    "KEY_UP": "Up",
    "KEY_DOWN": "Down",
    "KEY_Z": "Left",
    "KEY_X": "Down",
    "KEY_C": "Up",
    "KEY_V": "Right",
    # DPAD
    "BTN_DPAD_LEFT": "Left",
    "BTN_DPAD_RIGHT": "Right",
    "BTN_DPAD_UP": "Up",
    "BTN_DPAD_DOWN": "Down",
    # Joysticks (Virtual Buttons)
    "BTN_JOY_LX_NEG": "Left",
    "BTN_JOY_LX_POS": "Right",
    "BTN_JOY_LY_NEG": "Up",
    "BTN_JOY_LY_POS": "Down",
}


def on_key_event(event: InputEvent, key_name: str) -> None:
    if event.value == 1:
        state["physical_keys_down"].add(key_name)
    elif event.value == 0:
        state["physical_keys_down"].discard(key_name)

    if event.value == 1:
        if key_name in ("KEY_KPMINUS", "KEY_MINUS"):
            state["multiplier"] = max(1, state["multiplier"] - 1)
        elif key_name in ("KEY_KPPLUS", "KEY_EQUAL"):
            state["multiplier"] = min(5, state["multiplier"] + 1)


async def injection_loop() -> None:
    while state["running"]:
        if state["butterwalk"] and state["active"] and state["physical_keys_down"]:
            active_targets: set[str] = set()
            for k in state["physical_keys_down"]:
                # Check physical arrow/zxcv/dpad/joystick keys
                if k in KEY_MAP:
                    if (
                        k in ("KEY_Z", "KEY_X", "KEY_C", "KEY_V")
                        and not state["zxcv_enabled"]
                    ):
                        continue
                    if (
                        k.startswith("BTN_DPAD_")
                        and not state["dpad_enabled"]
                    ):
                        continue
                    if (
                        k == "KEY_SPACE"
                        and not state["space_enabled"]
                    ):
                        continue
                    active_targets.add(KEY_MAP[k])
                
                # Check keybinds for virtual arrow keys
                for macro in state["macros"]:
                    if (
                        macro.get("enabled", True)
                        and macro.get("kind") == "keybind"
                        and macro["trigger"] == k
                    ):
                        if macro["steps"]:
                            val = macro["steps"][0]["value"]
                            valid_targets = ["Left", "Right", "Up", "Down"]
                            if state["space_enabled"]:
                                valid_targets.append("space")
                            
                            if val in valid_targets:
                                active_targets.add(val)

            for target in active_targets:
                for _ in range(state["multiplier"]):
                    # Bypass shell parsing overhead by using exec directly
                    proc = await asyncio.create_subprocess_exec(
                        "xdotool", "key", target,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL
                    )
                    # Yield control back to the event loop while waiting for this specific key to finish
                    await proc.wait()
                    
                    # Tiny yield to ensure X11 registers the event before the next iteration
                    await asyncio.sleep(0.001)

        await asyncio.sleep(state["loop_interval"])
