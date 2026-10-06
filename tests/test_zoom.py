"""Wide history and prompts survive severe font-zoom geometry changes."""

import re
import sys

import pytest
from test_terminal import CLIENT, ROOT, SERVER, Session
from test_terminal import (
    environment as environment,  # noqa: PLC0414 - re-export the pytest fixture
)
from zoom_workload import records


def compact(data):
    return re.sub(rb"\s+", b"", data)


def missing_records(state, style):
    text = compact(state["text"])
    return [
        index
        for index, record in enumerate(records(style))
        if compact(record.encode()) not in text
    ]


@pytest.mark.parametrize("style", ["ascii", "unicode"])
@pytest.mark.parametrize("size", [(61, 38), (40, 26), (20, 12), (10, 6), (5, 4)])
def test_severe_zoom_preserves_wide_output(environment, style, size):
    session = Session(
        environment,
        client=CLIENT,
        server=SERVER,
        program=[
            sys.executable,
            str(ROOT / "tests/zoom_workload.py"),
            str(environment),
            style,
        ],
    )
    app = session.attachment
    try:
        app.until(lambda state: b"READY" in state["screen"], timeout=8)
        app.resize(93, 71)
        app.until(
            lambda _: (environment / "geometry").read_text() == "93x71", timeout=8
        )
        app.pump(0.4)
        app.send(b"T")
        app.until(lambda state: not missing_records(state, style), timeout=8)
        expected = compact("".join(records(style)).encode())
        for step, (cols, rows) in enumerate((size, (93, 71)) * 3):
            app.resize(cols, rows)
            app.until(
                lambda _, cols=cols, rows=rows: (
                    (environment / "geometry").read_text() == f"{cols}x{rows}"
                ),
                timeout=8,
            )
            state = app.pump(0.8)
            (environment / f"visible-{step}-{cols}x{rows}.txt").write_bytes(
                state["text"]
            )
            assert not missing_records(state, style), {
                "geometry": (cols, rows),
                "missing_records": missing_records(state, style),
                "client": CLIENT,
            }
            assert compact(state["text"]).count(expected) == 1, (
                "output order/duplication changed"
            )
        app.send(b"still-typing")
        app.until(
            lambda state: b"7374696c6c2d747970696e67" in state["screen"], timeout=8
        )
        assert not missing_records(app.term.state, style)
    finally:
        session.close()
