from __future__ import annotations
import curses

# Color-pair indices. Pair 0 is reserved by curses for the terminal default.
ACCENT = 1  # titles, headings
SUCCESS = 2  # on / active / enabled
DANGER = 3  # off / inactive / errors
WARN = 4  # hints, numbers, help text
MUTED = 5  # secondary/dim text
BAR = 6  # inverse bars (top title, bottom footer)


def init() -> None:
    curses.start_color()
    try:
        curses.use_default_colors()
        bg = -1
    except curses.error:
        bg = curses.COLOR_BLACK

    curses.init_pair(ACCENT, curses.COLOR_CYAN, bg)
    curses.init_pair(SUCCESS, curses.COLOR_GREEN, bg)
    curses.init_pair(DANGER, curses.COLOR_RED, bg)
    curses.init_pair(WARN, curses.COLOR_YELLOW, bg)
    # bright black = grey on 256-colour terminals; falls back cleanly elsewhere.
    try:
        curses.init_pair(MUTED, 8, bg)
    except curses.error:
        curses.init_pair(MUTED, curses.COLOR_WHITE, bg)
    curses.init_pair(BAR, curses.COLOR_BLACK, curses.COLOR_CYAN)


def accent(bold: bool = False) -> int:
    return curses.color_pair(ACCENT) | (curses.A_BOLD if bold else 0)


def success(bold: bool = False) -> int:
    return curses.color_pair(SUCCESS) | (curses.A_BOLD if bold else 0)


def danger(bold: bool = False) -> int:
    return curses.color_pair(DANGER) | (curses.A_BOLD if bold else 0)


def warn(bold: bool = False) -> int:
    return curses.color_pair(WARN) | (curses.A_BOLD if bold else 0)


def muted(bold: bool = False) -> int:
    return curses.color_pair(MUTED) | (curses.A_BOLD if bold else 0)


def bar(bold: bool = False) -> int:
    return curses.color_pair(BAR) | (curses.A_BOLD if bold else 0)
