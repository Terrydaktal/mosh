"""Synthetic full-screen app for keyboard-resize checks, on private test PTYs."""

import os
import select
import signal
import sys
import tty
from pathlib import Path

root = Path(sys.argv[1])
tty.setraw(0)
dirty = True


def resized(_signum, _frame):
    global dirty
    dirty = True


signal.signal(signal.SIGWINCH, resized)
while True:
    if dirty:
        dirty = False
        cols, rows = os.get_terminal_size(0)
        with (root / "sizes.log").open("a") as log:
            log.write(f"{cols}x{rows}\n")
        output = b"\x1b[0m"
        for row in range(1, rows + 1):
            label = f"viewport-{cols}x{rows}" if row == 1 else f"row-{row:02d}"
            if row == rows:
                label = "input>"
            output += f"\x1b[{row};1H\x1b[2K{label}".encode()
        while output:
            output = output[os.write(1, output) :]
    if select.select([0], [], [], 0.02)[0]:
        data = os.read(0, 4096)
        if not data:
            break
        with (root / "input.log").open("ab") as log:
            log.write(data)
