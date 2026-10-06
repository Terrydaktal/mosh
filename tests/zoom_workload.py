"""Static wide output: resize must not depend on the application repainting it."""

import os
import signal
import sys
import termios
import tty
from pathlib import Path


def records(style="ascii"):
    suffix = "\u7ea2\u9b54\u754c-e\u0301" if style == "unicode" else ""
    return [
        f"row-{row:02d}: "
        + "".join(
            f"[{row:02d}-{part:02d}-abcdefghijklmnopqrstuvwxyz{suffix}]"
            for part in range(6)
        )
        + f" :end-{row:02d}"
        for row in range(18)
    ]


def main():
    root = Path(sys.argv[1])
    style = sys.argv[2] if len(sys.argv) > 2 else "ascii"
    saved = termios.tcgetattr(0)
    tty.setraw(0)

    def geometry(*_):
        size = os.get_terminal_size(0)
        (root / "geometry").write_text(f"{size.columns}x{size.lines}")

    signal.signal(signal.SIGWINCH, geometry)
    geometry()
    try:
        os.write(1, b"READY\r\n")
        while data := os.read(0, 4096):
            if data == b"T":
                os.write(1, ("\r\n".join(records(style)) + "\r\nprompt> ").encode())
            elif data == b"Q":
                return
            else:
                os.write(1, b"\r\ninput:" + data.hex().encode() + b"\r\nprompt> ")
    finally:
        termios.tcsetattr(0, termios.TCSANOW, saved)


if __name__ == "__main__":
    main()
