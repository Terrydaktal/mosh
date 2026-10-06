"""Extreme direct-shell zoom: retain words and their original line structure."""

import base64
import json
import os
import sys

import pytest
from colored_table_workload import table
from terminal_harness import Attachment, Emulator
from test_terminal import Session
from test_terminal import (
    environment as environment,  # noqa: PLC0414 - re-export the pytest fixture
)
from test_zoom import compact


def prose():
    return (
        "\n".join(
            f"record-{row:02d}: alpha beta gamma delta epsilon zeta eta theta "
            f"iota kappa lambda mu nu xi omicron pi rho sigma tau :end-{row:02d}"
            for row in range(24)
        )
        + "\n"
    )


def payload(style):
    return prose() if style == "prose" else table()


def plain_payload(style):
    return prose() if style == "prose" else table(False)


def save_state(root, label, state, wire):
    (root / f"{label}.txt").write_bytes(state["text"])
    (root / f"{label}.json").write_text(
        json.dumps(
            {key: value for key, value in state.items() if not isinstance(value, bytes)}
            | {"wire_offset": len(wire)},
            indent=2,
        )
    )


@pytest.fixture(autouse=True)
def isolate_unpatched_termux(request, style, size):
    if (
        style == "table"
        and size[0] <= 12
        and os.environ.get("MOSH_TEST_TERMUX_WRAP_FIXED") != "1"
    ):
        request.node.add_marker(
            pytest.mark.xfail(
                strict=True,
                reason="Termux drops soft-wrap metadata on space-only rows; test the fixed oracle separately",
            )
        )


@pytest.mark.parametrize("style", ["prose", "table"])
@pytest.mark.parametrize("size", [(20, 12), (12, 8), (8, 6), (5, 4), (3, 3), (2, 2)])
def test_termux_only_tiny_zoom(style, size):
    term = Emulator("termux", 152, 161)
    try:
        term.feed((payload(style).replace("\n", "\r\n") + "prompt> ").encode())
        for cols, rows in (size, (152, 161)) * 2:
            term.command(f"SIZE {cols} {rows}")
        visible = [base64.b64decode(row).rstrip() for row in term.state["lines"]]
        expected = plain_payload(style).encode().splitlines()
        assert all(line in visible for line in expected), (
            "terminal-only line reflow changed"
        )
    finally:
        term.close()


@pytest.mark.parametrize("style", ["prose", "table"])
@pytest.mark.parametrize("size", [(20, 12), (12, 8), (8, 6), (5, 4), (3, 3), (2, 2)])
def test_mosh_tiny_zoom(environment, style, size):
    script = (
        "import os, signal, sys, tty; "
        "tty.setraw(0); signal.signal(signal.SIGWINCH, lambda *_: None); "
        "os.write(1, b'READY\\r\\n'); os.read(0, 1); "
        "os.write(1, sys.argv[1].encode()); "
        "\nwhile True:\n data = os.read(0, 4096)\n"
        " if not data: break\n"
        " os.write(1, b'\\r\\ninput:' + data.hex().encode() + b'\\r\\nprompt> ')\n"
    )
    session = Session(
        environment,
        program=[
            sys.executable,
            "-c",
            script,
            payload(style).replace("\n", "\r\n") + "prompt> ",
        ],
    )
    app = session.attachment
    expected = plain_payload(style).encode().splitlines()
    try:
        app.until(lambda state: b"READY" in state["screen"], timeout=8)
        Attachment.resize(app, 152, 161)
        app.pump(0.8)
        app.send(b"T")
        app.until(lambda state: b":end-20" in state["screen"], timeout=8)
        app.pump(0.5)
        for step, (cols, rows) in enumerate((size, (152, 161)) * 2):
            # Termux's emulator resizes synchronously. Leave the client running
            # as on Android rather than suspending it for each geometry change.
            Attachment.resize(app, cols, rows)
            state = app.pump(1)
            save_state(environment, f"step-{step}-{cols}x{rows}", state, app.wire)
            text = compact(state["text"])
            assert all(text.count(compact(line)) == 1 for line in expected), (
                "printed words lost or repeated"
            )
            positions = [text.index(compact(line)) for line in expected]
            assert positions == sorted(positions), "printed words reordered"
            if cols == 152:
                # The transport deliberately keeps retired viewport rows in
                # scrollback. Their contents must reflow correctly there too.
                physical = state["text"].splitlines()
                assert all(line in physical for line in expected), (
                    "Mosh line structure changed"
                )
        app.send(b"still-typing")
        app.until(lambda state: b"7374696c6c2d747970696e67" in state["screen"])
    finally:
        save_state(environment, "last", app.term.state, app.wire)
        (environment / "wire.bin").write_bytes(app.wire)
        session.close()
