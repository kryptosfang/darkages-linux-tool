import asyncio
import subprocess


async def key(key_name: str) -> None:
    proc = await asyncio.create_subprocess_exec(
        "xdotool", "key", key_name,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL
    )
    await proc.wait()


async def mouse_click(button: int, x: int | None = None, y: int | None = None) -> None:
    if x is not None and y is not None:
        # Move relative to the current active window and click
        # Using shell=True for the subshell expansion
        cmd = f"xdotool mousemove --window $(xdotool getactivewindow) {x} {y} click {button}"
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await proc.wait()
    else:
        proc = await asyncio.create_subprocess_exec(
            "xdotool", "click", str(button),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await proc.wait()
