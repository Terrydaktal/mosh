"""Rapid font zoom must not duplicate already printed shell output."""

import json
import os
import shlex
import shutil
import sys
from types import SimpleNamespace

import pytest
from colored_table_workload import table
from terminal_harness import Attachment
from test_terminal import CLIENT, ROOT, SERVER, Session
from test_terminal import (
    environment as environment,  # noqa: PLC0414 - re-export the pytest fixture
)
from test_zoom import compact, missing_records
from zoom_workload import records


@pytest.mark.parametrize("delay", [0.01, 0.05, 0.3])
def test_zoom_burst_preserves_output(environment, delay):
    session = Session(
        environment,
        client=CLIENT,
        server=SERVER,
        program=[
            sys.executable,
            str(ROOT / "tests/zoom_workload.py"),
            str(environment),
            "ascii",
        ],
    )
    app = session.attachment
    expected = compact("".join(records()).encode())
    try:
        app.until(lambda state: b"READY" in state["screen"], timeout=8)
        app.resize(81, 59)
        app.until(lambda _: (environment / "geometry").read_text() == "81x59")
        app.pump(0.5)
        app.send(b"T")
        app.until(lambda state: not missing_records(state, "ascii"), timeout=8)
        for cycle in range(3):
            for step, (cols, rows) in enumerate(
                (
                    (61, 45),
                    (40, 29),
                    (20, 14),
                    (10, 7),
                    (5, 4),
                    (10, 7),
                    (20, 14),
                    (40, 29),
                    (61, 45),
                    (81, 59),
                    (110, 81),
                    (152, 161),
                )
            ):
                app.resize(cols, rows)
                state = app.pump(delay)
                (environment / f"step-{cycle}-{step}-{cols}x{rows}.txt").write_bytes(
                    state["text"]
                )
                (environment / f"step-{cycle}-{step}-{cols}x{rows}.json").write_text(
                    json.dumps(
                        {
                            "wire_offset": len(app.wire),
                            "x": state.get("x"),
                            "y": state.get("y"),
                            "history": state.get("history"),
                            "lines": state.get("lines"),
                        },
                        indent=2,
                    )
                )
            app.until(lambda _: (environment / "geometry").read_text() == "152x161")
            state = app.pump(1)
            (environment / f"output-{cycle}.txt").write_bytes(state["text"])
            assert not missing_records(state, "ascii"), "printed records were lost"
            assert compact(state["text"]).count(expected) == 1, (
                "printed records duplicated or reordered"
            )
    finally:
        (environment / "wire.bin").write_bytes(app.wire)
        (environment / "last-output.txt").write_bytes(app.term.state["text"])
        session.close()


@pytest.mark.parametrize("via", ["direct", "mosh"])
@pytest.mark.parametrize("delay", [0.01, 0.3])
def test_fish_coloured_table_survives_zoom(environment, via, delay):
    fish = shutil.which("fish")
    assert fish
    session = None
    if via == "mosh":
        session = Session(environment, program=[fish, "--no-config", "-i"])
        app = session.attachment
    else:
        env = os.environ.copy()
        env["TERMUX_VERSION"] = "terminal-oracle"
        app = Attachment(
            SimpleNamespace(socket=environment / "unused.sock", env=env),
            argv=[fish, "--no-config", "-i"],
        )
    expected = compact(table(False).encode())
    try:
        app.pump(1)
        app.send(
            b"function fish_prompt; printf 'fish-test> '; end; functions -e fish_right_prompt\r"
        )
        app.until(lambda state: b"fish-test>" in state["screen"], timeout=8)
        app.resize(81, 59)
        app.pump(1)
        command = " ".join(
            shlex.quote(arg)
            for arg in [sys.executable, str(ROOT / "tests/colored_table_workload.py")]
        )
        app.send(command.encode() + b"\r")
        app.until(lambda state: expected in compact(state["text"]), timeout=8)
        for cycle in range(3):
            for step, (cols, rows) in enumerate(
                (
                    (61, 45),
                    (40, 29),
                    (20, 14),
                    (10, 7),
                    (5, 4),
                    (10, 7),
                    (20, 14),
                    (40, 29),
                    (61, 45),
                    (81, 59),
                    (110, 81),
                    (152, 161),
                )
            ):
                app.resize(cols, rows)
                state = app.pump(delay)
                (environment / f"step-{cycle}-{step}-{cols}x{rows}.txt").write_bytes(
                    state["text"]
                )
                (environment / f"step-{cycle}-{step}-{cols}x{rows}.json").write_text(
                    json.dumps(
                        {
                            "wire_offset": len(app.wire),
                            "x": state.get("x"),
                            "y": state.get("y"),
                            "history": state.get("history"),
                            "lines": state.get("lines"),
                        },
                        indent=2,
                    )
                )
            state = app.pump(1.5)
            (environment / f"fish-output-{cycle}.txt").write_bytes(state["text"])
            assert compact(state["text"]).count(expected) == 1, (
                "coloured table corrupted"
            )
            for index in range(21):
                assert compact(state["text"]).count(f":end-{index:02d}".encode()) == 1
            assert b"fish-test>" in state["screen"], "Fish prompt disappeared"
    finally:
        (environment / "wire.bin").write_bytes(app.wire)
        (environment / "last-output.txt").write_bytes(app.term.state["text"])
        (environment / "state.json").write_text(
            json.dumps(
                {k: v for k, v in app.term.state.items() if not isinstance(v, bytes)},
                indent=2,
            )
        )
        if session:
            session.close()
        else:
            app.close()
