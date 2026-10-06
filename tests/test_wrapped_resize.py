"""Wide shell output must survive zoom and keyboard geometry round trips."""

import json
import sys
import time

import pytest
from test_terminal import ROOT, Session
from test_terminal import (
    environment as environment,  # noqa: PLC0414 - re-export the pytest fixture
)
from wrapped_workload import table


def compact(text):
    return b"".join(text.split())


def resize_and_settle(app, environment, cols, rows):
    start = len(app.wire)
    app.resize(cols, rows)
    (environment / f"local-resize-{cols}x{rows}.txt").write_bytes(
        app.term.state["text"]
    )
    (environment / f"local-resize-{cols}x{rows}-screen.txt").write_bytes(
        app.term.state["screen"]
    )
    marker = f"native-size-{cols}x{rows}-".encode()
    last = [len(app.wire), time.monotonic()]

    def painted(_state):
        if len(app.wire) != last[0]:
            last[:] = [len(app.wire), time.monotonic()]
        return (
            (environment / "geometry").read_text() == f"{cols}x{rows}"
            and marker in app.wire[start:]
            and time.monotonic() - last[1] >= 0.2
        )

    return app.until(painted, timeout=8)


@pytest.mark.parametrize("kind", ["termux", "vte"])
@pytest.mark.parametrize("size", [(61, 38), (93, 20), (51, 85)])
def test_wide_table_survives_resize_round_trip(environment, kind, size):
    session = Session(
        environment,
        kind,
        program=[
            sys.executable,
            str(ROOT / "tests/wrapped_workload.py"),
            str(environment),
        ],
    )
    app = session.attachment
    expected = compact(table())
    geometry = (80, 24)
    try:
        app.until(lambda state: b"READY" in state["screen"], timeout=8)
        geometry = (93, 71)
        resize_and_settle(app, environment, 93, 71)
        app.send(b"T")
        app.until(lambda state: expected in compact(state["text"]), timeout=8)
        for cols, rows in (size, (93, 71), (81, 85), (93, 71)):
            geometry = (cols, rows)
            state = resize_and_settle(app, environment, cols, rows)
            assert expected in compact(state["text"])
            for index in range(18):
                assert compact(state["text"]).count(f"row-{index:02d}".encode()) == 1
        app.send(b"typed-after-zoom")
        app.until(
            lambda state: (
                (environment / "input.log").exists()
                and b"typed-after-zoom" in (environment / "input.log").read_bytes()
            ),
            timeout=8,
        )
    finally:
        final = app.term.state
        (environment / "last-output.txt").write_bytes(final["text"])
        (environment / "resize-summary.json").write_text(
            json.dumps(
                {
                    "geometry": geometry,
                    "cursor": [final.get("x"), final.get("y")],
                    "history": final.get("history"),
                    "rows": {
                        f"row-{index:02d}": compact(final["text"]).count(
                            f"row-{index:02d}".encode()
                        )
                        for index in range(18)
                    },
                },
                indent=2,
            )
        )
        session.close()
