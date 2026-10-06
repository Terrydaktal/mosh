"""Real Mosh protocol on loopback, real PTYs, independent terminal emulators."""

import ctypes
import os
import re
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from conftest import shared

ROOT = Path(__file__).resolve().parents[1]
TMUX = shared
sys.path.insert(0, str(TMUX))
sys.path.insert(0, str(TMUX / "tests"))
from terminal_harness import Attachment

BUILD = Path(
    os.environ.get(
        "MOSH_BUILD", (ROOT / "build/runtime/mosh-native-server").resolve().parents[2]
    )
)
CLIENT = os.environ.get(
    "MOSH_TEST_CLIENT", str(BUILD / "src/frontend/mosh-native-client")
)
SERVER = os.environ.get(
    "MOSH_TEST_SERVER", str(BUILD / "src/frontend/mosh-native-server")
)
LIBC = ctypes.CDLL(None, use_errno=True)


class Link:
    """Two loopback-only sockets model loss, duplicates, outages and roaming."""

    def __init__(self, server_port, lossy=False):
        self.server = ("127.0.0.1", server_port)
        self.downstream = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.downstream.bind(("127.0.0.1", 0))
        self.upstream = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.upstream.bind(("127.0.0.1", 0))
        self.port = self.downstream.getsockname()[1]
        self.client = None
        self.last_client_packet = None
        self.lossy, self.paused, self.roam = lossy, False, False
        self.packets = 0

    def pump(self):
        import select

        if self.roam:
            self.upstream.close()
            self.upstream = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.upstream.bind(("127.0.0.1", 0))
            self.roam = False
        for source in select.select([self.downstream, self.upstream], [], [], 0)[0]:
            data, address = source.recvfrom(65536)
            if source is self.downstream:
                self.client = address
                target, destination = self.upstream, self.server
            elif self.client:
                target, destination = self.downstream, self.client
            else:
                continue
            self.packets += 1
            if self.paused or (self.lossy and self.packets % 7 == 0):
                continue
            if source is self.downstream:
                self.last_client_packet = data
            target.sendto(data, destination)
            if self.lossy and self.packets % 11 == 0:
                target.sendto(data, destination)

    def close(self):
        self.downstream.close()
        self.upstream.close()


class MoshAttachment(Attachment):
    def __init__(self, link, *args, **kwargs):
        self.link = link
        super().__init__(*args, **kwargs)

    def pump(self, duration=0.05):
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            self.link.pump()
            super().pump(min(0.005, max(0, deadline - time.monotonic())))
        return self.term.state

    def resize(self, cols, rows):
        # VTE's headless geometry call settles asynchronously. Do not let that
        # test-only delay render old-size frames into the already-resized screen.
        os.kill(self.pid, signal.SIGSTOP)
        os.waitpid(self.pid, os.WUNTRACED)
        try:
            super().pump(0.02)
            super().resize(cols, rows)
        finally:
            os.kill(self.pid, signal.SIGCONT)


@pytest.fixture
def environment(tmp_path, monkeypatch):
    for key in (
        "HOME",
        "XDG_CONFIG_HOME",
        "XDG_CACHE_HOME",
        "XDG_DATA_HOME",
        "XDG_RUNTIME_DIR",
    ):
        monkeypatch.setenv(key, str(tmp_path))
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.setenv("LANG", "C.UTF-8")
    monkeypatch.setenv("LC_ALL", "C.UTF-8")
    monkeypatch.setenv("MOSH_PREDICTION_DISPLAY", "never")
    monkeypatch.setenv("MOSH_SERVER_NETWORK_TMOUT", "30")
    monkeypatch.setenv("MOSH_TITLE_NOPREFIX", "1")
    monkeypatch.setenv("TMUX_MOSH_OPSEC_CONTROL_PATH", str(tmp_path / "no-vm-master"))
    monkeypatch.delenv("MOSH_NO_TERM_INIT", raising=False)
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.delenv("TMUX_PANE", raising=False)
    return tmp_path


class Session:
    def __init__(
        self,
        root,
        kind="termux",
        lossy=False,
        program=None,
        client=CLIENT,
        server=SERVER,
    ):
        self.link, self.attachment, self.pidfd = None, None, None
        # The OS chooses a free test port; bind failures fail this fixture.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        self.env = os.environ.copy()
        # Use the actual environment marker of the terminal being emulated.
        if kind == "termux":
            self.env["TERMUX_VERSION"] = "terminal-oracle"
            self.env["MOSH_NATIVE_TERMUX"] = "1"
        else:
            self.env.pop("TERMUX_VERSION", None)
            self.env.pop("PREFIX", None)
            self.env["MOSH_NATIVE_TERMUX"] = "0"
        args = [server, "new", "-i", "127.0.0.1", "-p", str(port), "-c", "256", "--"]
        args += program or [sys.executable, str(ROOT / "tests/workload.py"), str(root)]
        result = subprocess.run(
            args,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            env=self.env,
            timeout=5,
            check=False,
        )
        assert result.returncode == 0, result.stderr.decode(errors="replace")
        handshake = re.search(rb"MOSH CONNECT (\d+) ([A-Za-z0-9/+]{22})", result.stdout)
        assert handshake, "server did not provide a handshake"
        pid = int(re.search(rb"detached, pid = (\d+)", result.stderr)[1])
        self.pidfd = LIBC.pidfd_open(pid, 0)
        self.server_pid = pid
        if self.pidfd < 0:
            raise OSError(ctypes.get_errno(), "pidfd_open for owned test server failed")
        self.env["MOSH_KEY"] = handshake[2].decode()
        self.link = Link(port, lossy)
        backend = SimpleNamespace(socket=root / "unused.sock", env=self.env)
        try:
            self.attachment = MoshAttachment(
                self.link,
                backend,
                kind=kind,
                cols=80,
                rows=24,
                argv=[client, "127.0.0.1", str(self.link.port)],
            )
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.attachment:
            self.attachment.close()
        if self.pidfd is not None:
            LIBC.pidfd_send_signal(self.pidfd, signal.SIGTERM, None, 0)
            import select

            if not select.select([self.pidfd], [], [], 0.3)[0]:
                LIBC.pidfd_send_signal(self.pidfd, signal.SIGKILL, None, 0)
            os.close(self.pidfd)
        if self.link:
            self.link.close()


def assert_records(state, generation=1):
    records = re.findall(
        rb"history-" + str(generation).encode() + rb"-(\d{5})-end", state["text"]
    )
    assert len(records) == 1500, {
        "count": len(records),
        "missing": sorted(set(range(1500)) - set(map(int, records))),
    }
    assert sorted(map(int, records)) == list(range(1500))


@pytest.mark.parametrize("kind", ["termux", "vte"])
@pytest.mark.parametrize("lossy", [False, True])
def test_history_reaches_native_scrollback(environment, kind, lossy):
    session = Session(environment, kind, lossy)
    app = session.attachment
    try:
        app.until(lambda s: b"READY" in s["screen"], timeout=10)
        app.send(b"H")
        state = app.until(lambda s: b"history-1-01499-end" in s["text"], timeout=30)
        assert_records(state)
        assert not re.search(rb"\x1b\[\?(?:1049|1047|47|1000|1002|1003)h", app.wire)
        if kind == "termux":
            assert not state["alternate"]
            assert not state["mouse"]
        app.send(b"typing-still-works")
        app.until(
            lambda s: (
                b"747970696e672d7374696c6c2d776f726b73"
                in (environment / "input.log").read_bytes()
            )
        )
    finally:
        session.close()


def test_outage_and_roaming_recover_undelivered_history(environment):
    session = Session(environment, lossy=True)
    app = session.attachment
    try:
        app.until(lambda s: b"READY" in s["screen"], timeout=10)
        session.link.paused = True
        (environment / "control").write_bytes(b"H")
        app.until(lambda s: (environment / "input.log").exists())
        # Output is generated while every packet is dropped, not just slowed.
        app.pump(0.5)
        assert b"history-1-00000-end" not in app.term.state["text"]
        session.link.roam = True
        session.link.paused = False
        state = app.until(lambda s: b"history-1-01499-end" in s["text"], timeout=30)
        assert_records(state)
    finally:
        session.close()


def test_finite_command_drains_history_before_exit(environment):
    session = Session(environment)
    app = session.attachment
    try:
        app.until(lambda s: b"READY" in s["screen"], timeout=10)
        app.send(b"F")
        state = app.until(lambda s: app.exited, timeout=30)
        assert_records(state)
    finally:
        session.close()


def test_ordinary_mosh_path_remains_stock_wire_compatible(environment):
    from loopback_harness import Session as OrdinarySession

    session = OrdinarySession(
        environment,
        client=str(TMUX / "build/runtime/mosh-client"),
        server=str(TMUX / "build/runtime/mosh-server"),
        program=[sys.executable, str(ROOT / "tests/workload.py"), str(environment)],
    )
    try:
        app = session.attachment
        app.until(lambda state: b"READY" in state["screen"], timeout=8)
        app.send(b"ordinary-mosh")
        app.until(lambda state: (environment / "input.log").exists())
        assert (
            bytes.fromhex((environment / "input.log").read_text()) == b"ordinary-mosh"
        )
    finally:
        session.close()


def test_wrapper_resolves_its_own_client_outside_path(environment):
    script = BUILD / "scripts/mosh-native"
    result = subprocess.run(
        [str(script), "--help"],
        capture_output=True,
        timeout=5,
        cwd=environment,
        check=False,
    )
    assert result.returncode == 0
    assert b"mosh-native-server" in result.stdout


@pytest.mark.parametrize("kind", ["termux", "vte"])
@pytest.mark.parametrize("size", [(51, 39), (80, 39), (51, 16), (101, 24)])
def test_resize_during_history_transfer(environment, kind, size):
    session = Session(environment, kind, lossy=True)
    app = session.attachment
    try:
        app.until(lambda s: b"READY" in s["screen"], timeout=10)
        app.send(b"H")
        app.until(lambda s: b"history-1-00000-end" in s["text"], timeout=15)
        app.resize(*size)
        state = app.until(lambda s: b"history-1-01499-end" in s["text"], timeout=30)
        assert_records(state)
        if kind == "termux":
            assert not state["alternate"]
            assert not state["mouse"]
    finally:
        session.close()


@pytest.mark.parametrize("kind", ["termux", "vte"])
def test_resize_after_delivery_and_before_any_history(environment, kind):
    session = Session(environment, kind)
    app = session.attachment
    try:
        app.until(lambda s: b"READY" in s["screen"], timeout=10)
        app.resize(80, 39)
        assert app.until(lambda s: b"READY" in s["screen"])["text"].count(b"READY") == 1
        app.resize(80, 24)
        app.send(b"H")
        app.until(lambda s: b"history-1-01499-end" in s["text"], timeout=30)
        app.resize(80, 120)
        app.send(b"typed-after-resize")
        state = app.until(
            lambda s: (
                b"74797065642d61667465722d726573697a65"
                in (environment / "input.log").read_bytes()
            ),
            timeout=10,
        )
        assert_records(state)
    finally:
        session.close()


@pytest.mark.parametrize("kind", ["termux", "vte"])
def test_keyboard_resize_never_draws_old_geometry(environment, kind):
    session = Session(
        environment,
        kind,
        program=[
            sys.executable,
            str(ROOT / "tests/resize_workload.py"),
            str(environment),
        ],
    )
    app = session.attachment
    try:
        app.until(lambda s: b"viewport-80x24" in s["screen"], timeout=10)
        session.link.paused = True
        app.resize(80, 12)
        wire_start = len(app.wire)
        # Deliberately keep the old remote frame around longer than a resize burst.
        app.pump(0.35)
        drawn_rows = [
            int(row) for row in re.findall(rb"\x1b\[(\d+);\d+H", app.wire[wire_start:])
        ]
        assert all(row <= 12 for row in drawn_rows), drawn_rows
        app.send(b"typed-with-keyboard")
        session.link.paused = False
        app.until(lambda s: b"viewport-80x12" in s["screen"], timeout=10)
        app.until(
            lambda s: (
                (environment / "input.log").exists()
                and b"typed-with-keyboard" in (environment / "input.log").read_bytes()
            ),
            timeout=10,
        )
        app.resize(80, 24)
        app.until(lambda s: b"viewport-80x24" in s["screen"], timeout=10)
    finally:
        session.close()
