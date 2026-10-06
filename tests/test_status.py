"""The direct-history server retains the standard authenticated packet-age API."""

import json
import os
import select
import socket
import subprocess
import tempfile
import time
from pathlib import Path

import mosh_cleanup
import mosh_status
import pytest
import tmux_clients as clients
from test_terminal import (
    SERVER,
    TMUX,
    Session,
)
from test_terminal import (
    environment as environment,  # noqa: PLC0414 - re-export the pytest fixture
)


def test_server_advertises_receive_status_without_changing_history_protocol():
    result = subprocess.run([SERVER, "--version"], capture_output=True, check=True)
    assert b"1.4.0-native3" in result.stdout
    assert b"[rx-status1]" in result.stdout


def test_no_timestamp_is_invented_before_first_authenticated_packet(
    environment, monkeypatch
):
    with tempfile.TemporaryDirectory(prefix="mosh-direct-rx-") as runtime:
        monkeypatch.setenv("XDG_RUNTIME_DIR", runtime)
        session = Session(environment)
        try:
            path = Path(runtime) / "mosh-status" / f"{session.server_pid}.sock"
            deadline = time.monotonic() + 2
            while not path.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert path.exists()
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(0.2)
                connection.connect(str(path))
                response = json.loads(connection.recv(512))
            assert response == {
                "version": 1,
                "pid": session.server_pid,
                "last_rx_monotonic_ms": None,
            }
            assert (
                mosh_status.read(clients.process(session.server_pid), clients.process)
                is None
            )
        finally:
            session.close()


@pytest.mark.parametrize(
    "legacy_client", [False, True], ids=["new-client", "existing-native2"]
)
def test_packet_age_inventory_and_cleanup_work_with_direct_history(
    environment, monkeypatch, legacy_client
):
    options = {}
    if legacy_client:
        previous = os.environ.get("MOSH_COMPAT_CLIENT")
        if not previous:
            pytest.skip(
                "set MOSH_COMPAT_CLIENT to exercise the previously installed client"
            )
        options["client"] = previous
    with tempfile.TemporaryDirectory(prefix="mosh-direct-rx-") as runtime:
        monkeypatch.setenv("XDG_RUNTIME_DIR", runtime)
        session = Session(environment, **options)
        try:
            app = session.attachment
            app.until(lambda state: b"READY" in state["screen"], timeout=8)
            owner = clients.process(session.server_pid)
            first = mosh_status.read(owner, clients.process)
            assert first is not None and first["idle_seconds"] <= 1

            session.link.paused = True
            app.pump(0.2)
            before = mosh_status.read(owner, clients.process)
            app.pump(1.15)
            paused = mosh_status.read(owner, clients.process)
            assert (
                paused["network_last_rx_monotonic_ms"]
                == before["network_last_rx_monotonic_ms"]
            )
            assert paused["idle_seconds"] >= 1

            # Queries, a replay and unauthenticated datagrams must not refresh age.
            assert session.link.last_client_packet is not None
            session.link.upstream.sendto(
                session.link.last_client_packet, session.link.server
            )
            session.link.upstream.sendto(b"invalid packet", session.link.server)
            app.pump(0.1)
            assert (
                mosh_status.read(owner, clients.process)["network_last_rx_monotonic_ms"]
                == paused["network_last_rx_monotonic_ms"]
            )

            snapshot = clients.inventory(
                clients.Server(TMUX / "build/runtime/tmux", environment / "absent.sock")
            )
            (entry,) = [
                row for row in snapshot["entries"] if row["mosh_pid"] == owner.pid
            ]
            assert entry["type"] == "DIRECT" and entry["idle_seconds"] >= 1
            assert (entry["width"], entry["height"]) == (80, 24)
            child = clients.process(int((environment / "app.pid").read_text()))
            cleanup = mosh_cleanup.cleanup(
                clients.process,
                older_than=1,
                dry_run=True,
                snapshot=({owner.pid: owner, child.pid: child}, ""),
            )
            assert cleanup["entries"][0]["action"] == "would-close"

            session.link.paused = False
            app.send(b"contact-resumed")
            app.until(
                lambda state: (
                    b"contact-resumed".hex().encode()
                    in (environment / "input.log").read_bytes()
                ),
                timeout=8,
            )
            resumed = mosh_status.read(owner, clients.process)
            assert (
                resumed["network_last_rx_monotonic_ms"]
                > paused["network_last_rx_monotonic_ms"]
            )
            assert resumed["idle_seconds"] <= 1
            app.send(b"X")
            app.until(
                lambda state: (
                    app.exited and bool(select.select([session.pidfd], [], [], 0)[0])
                ),
                timeout=8,
            )
        finally:
            session.close()
        assert not (
            Path(runtime) / "mosh-status" / f"{session.server_pid}.sock"
        ).exists()
