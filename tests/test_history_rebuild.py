"""A direct app's history replacement is not append-only terminal output."""

import re
import sys

import pytest
from test_terminal import ROOT, Session
from test_terminal import environment as environment  # noqa: PLC0414


def settled(app, cols, rows, serial=None):
    marker = f"input-{cols}x{rows}-".encode()
    if serial is not None:
        marker += str(serial).encode()
    app.until(
        lambda state: marker in state["screen"] and b"replay-0000-end" in state["text"],
        timeout=20,
    )
    return app.pump(0.3)


def assert_transcript(state):
    numbers = re.findall(rb"replay-(\d{4})-end", state["text"])
    assert list(map(int, numbers)) == list(range(80))


@pytest.mark.parametrize("kind", ["termux", "vte"])
@pytest.mark.parametrize("lossy", [False, True])
def test_direct_replay_replaces_history_and_uses_full_keyboard_height(
    environment, kind, lossy
):
    session = Session(
        environment,
        kind,
        lossy,
        program=[sys.executable, str(ROOT / "tests/history_rebuild_workload.py")],
    )
    try:
        app = session.attachment
        assert_transcript(settled(app, 80, 24))
        app.send(b"r")
        assert_transcript(settled(app, 80, 24, serial=2))
        for cols, rows in [(80, 12), (80, 40), (50, 24), (80, 24)]:
            app.resize(cols, rows)
            state = settled(app, cols, rows)
            assert_transcript(state)
            assert f"input-{cols}x{rows}-".encode() in state["screen"].splitlines()[-1]
        app.send(b"k")
        app.until(lambda state: b"KEY-RECEIVED" in state["screen"], timeout=10)
    finally:
        session.close()
