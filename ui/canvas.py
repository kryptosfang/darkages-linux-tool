from __future__ import annotations
import curses

Chunk = str | tuple[str, int]


class Canvas:
    """Boundary-safe drawing primitives over a curses window.

    All methods clip to the window and swallow curses errors, so callers never
    need try/except around placement.
    """

    win: curses.window
    h: int
    w: int

    def __init__(self, win: curses.window) -> None:
        self.win = win
        self.h, self.w = win.getmaxyx()

    def put(self, row: int, col: int, text: str, attr: int = 0) -> int:
        if row < 0 or row >= self.h or col >= self.w or not text:
            return col
        if col < 0:
            text = text[-col:]
            col = 0
        budget = self.w - col - 1
        if budget <= 0:
            return col
        snippet = text[:budget]
        try:
            self.win.addstr(row, col, snippet, attr)
        except curses.error:
            pass
        return col + len(snippet)

    def line(self, row: int, col: int, *chunks: Chunk) -> int:
        """Write a run of chunks left-to-right. Each chunk is either a string
        or a (string, attr) tuple. Returns the next free column."""
        for chunk in chunks:
            if isinstance(chunk, tuple):
                text, attr = chunk
            else:
                text, attr = chunk, 0
            col = self.put(row, col, text, attr)
        return col

    def right(self, row: int, *chunks: Chunk, pad: int = 2) -> int:
        """Right-align a run of chunks on `row`, inset by `pad` from the edge."""
        total = sum(len(c[0] if isinstance(c, tuple) else c) for c in chunks)
        col = max(0, self.w - total - pad)
        return self.line(row, col, *chunks)

    def fill(self, row: int, attr: int) -> None:
        _ = self.put(row, 0, " " * max(0, self.w - 1), attr)

    def hrule(self, row: int, attr: int = 0, char: str = "─") -> None:
        _ = self.put(row, 0, char * max(0, self.w - 1), attr)
