"""Synthetic local PTY workload; never runs commands from input."""

import os
import select
import sys
import tty
from pathlib import Path

root = Path(sys.argv[1])
tty.setraw(0)
(root / "app.pid").write_text(str(os.getpid()))
os.write(1, b"READY\r\n")
counter = 0
while True:
    control = root / "control"
    if control.exists():
        command = control.read_bytes()
        control.unlink()
    elif select.select([0], [], [], 0.05)[0]:
        command = os.read(0, 4096)
        if not command:
            break
    else:
        continue
    with (root / "input.log").open("ab") as log:
        log.write(command.hex().encode() + b"\n")
    if command in (b"H", b"F"):
        counter += 1
        output = b"".join(
            f"history-{counter}-{i:05d}-end\r\n".encode() for i in range(1500)
        )
        output += b"\r\n" * 100 + b"READY\r\n"
        while output:
            output = output[os.write(1, output) :]
        if command == b"F":
            break
    elif command == b"X":
        break
