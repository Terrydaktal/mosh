"""Replay a source-backed transcript after Codex-style main-screen clears."""

import os
import select
import signal
import tty


def output(data):
    while data:
        data = data[os.write(1, data) :]


dirty = True
serial = 0
alternate = False


def resized(*_):
    global dirty
    dirty = True


tty.setraw(0)
signal.signal(signal.SIGWINCH, resized)
while True:
    if dirty and not alternate:
        dirty = False
        serial += 1
        cols, rows = os.get_terminal_size(0)
        region = rows
        # Codex clears visible output AND saved lines before rebuilding history.
        output(b"\033[r\033[0m\033[H\033[2J\033[3J\033[H")
        output(f"\033[1;{region}r\033[H".encode())
        output(b"".join(f"replay-{i:04d}-end\r\n".encode() for i in range(80)))
        output(f"\033[r\033[{rows};1Hinput-{cols}x{rows}-{serial}".encode())
    if not select.select([0], [], [], 0.05)[0]:
        continue
    key = os.read(0, 1)
    if key in (b"", b"q"):
        break
    if key == b"r":
        dirty = True
    elif key == b"a":
        alternate = True
        output(b"\033[?1049h\033[3J\033[HALTERNATE-READY")
    elif key == b"b":
        alternate = False
        output(b"\033[?1049l")
    elif key == b"k":
        output(b"\033[2;1HKEY-RECEIVED")
