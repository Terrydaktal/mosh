"""A one-shot wide table followed by an idle prompt on a private test PTY."""

import os
import select
import signal
import sys
import tty
from pathlib import Path


def table():
    lines = [b"Snapshot: wide wrapped output before resize"]
    for index in range(18):
        lines.append(
            (
                f"row-{index:02d}  mosh-{index:04d}  direct  session-{index:02d}  "
                f"python3-{index:04d}  tty-{index:02d}  idle-{index:02d}s  "
                f"peer-100.70.36.{index:02d}  size-93x71  sizing-none  "
                f"command-{index:02d}-abcdefghijklmnopqrstuvwxyz-ABCDEFGHIJKLMNOPQRSTUVWXYZ-end"
            ).encode()
        )
    return b"\r\n".join(lines) + b"\r\nTABLE-END\r\nprompt> "


def main():
    root = Path(sys.argv[1])
    tty.setraw(0)
    generation = 0

    def resized(_signum, _frame):
        nonlocal generation
        generation += 1
        size = os.get_terminal_size(0)
        (root / "geometry").write_text(f"{size.columns}x{size.lines}")
        os.write(
            1,
            f"\x1b]0;native-size-{size.columns}x{size.lines}-{generation}\x07".encode(),
        )

    signal.signal(signal.SIGWINCH, resized)
    resized(None, None)
    os.write(1, b"READY\r\n")
    while True:
        if not select.select([0], [], [], 0.05)[0]:
            continue
        command = os.read(0, 4096)
        if not command or command == b"X":
            return
        if command == b"T":
            output = table()
            while output:
                output = output[os.write(1, output) :]
        else:
            with (root / "input.log").open("ab") as log:
                log.write(command)


if __name__ == "__main__":
    main()
