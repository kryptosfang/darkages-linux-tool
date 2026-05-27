# DarkAges Linux Tool (DALT)

## Project Context
DALT is a Linux movement and input automation tool designed as a hardened fork of `ughlis`. It provides low-level input hooks (via `evdev`) and automated macro execution, leveraging a non-blocking asyncio architecture to maintain zero-lag input processing.

## Tech Stack
- **Language**: Python 3
- **GUI Framework**: CustomTkinter / Tkinter
- **Dependencies**: `evdev` (input handling), `xdotool` (window interactions)
- **Core Approach**: Async process execution and cooperative asynchronous tasks for event loops.

## Directory Structure
- `assets/`: Image resources and desktop configuration.
- `scripts/`: Shell scripts for setup, permission configuration, and running the app.
- `ui/` & `gui/`: CustomTkinter interface components.
- `features/`: Core functionality blocks (macros, inputs).
- `main.py`: Primary application entry point.

## Development Guidelines
- **Input Processing**: Do not introduce synchronous blocking calls (`time.sleep`, `subprocess.run`) into the main async event loop. Always use `asyncio.sleep` or `asyncio.create_subprocess_exec`.
- **Permissions**: The application relies on `/dev/input/` access. Users must be part of the `input` group (managed via `scripts/setup_permissions.sh`).
- **Assets**: Reference visual assets (e.g., icons) using paths relative to the project root like `assets/icon.png`.
- **Window Hooks**: The tool relies on exact window name matching for targeted macro execution. Do not use partial text search for window finding.