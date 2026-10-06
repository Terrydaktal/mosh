# mosh

This fork is published as [Terrydaktal/mosh](https://github.com/Terrydaktal/mosh),
with the maintained patch series and build tooling on `main`.

`main` descends from upstream tag `mosh-1.4.0`
(`bc73a26316ede2a79259d859f8ee309b32412420`). Upstream source and history
are retained, and the history-profile patches are also applied to the tracked
source. The reproducible builders still use the pinned 1.4.0 archive; the
ordinary-protocol profile remains independently built from that archive.
The fork has twelve changes on top of that release. Commits added to upstream
`master` after 1.4.0 remain separate until the patches are ported and verified.
The `mosh-native` executable and local directory names identify the history-aware
protocol profile and remain compatible with existing client commands.
The `compat/` directory also records the ordinary-protocol packet-age profile
used by tmux; `scripts/build-compat.sh` builds that profile independently.

Mosh 1.4.0 client/server extension for native terminal scrollback and resize-safe
rendering in direct shell/app connections. Both endpoints must use the native
history protocol; it is not wire-compatible with ordinary Mosh. The separate
compatibility fork used for tmux keeps that ordinary protocol and adds packet-age
reporting. Host `mosh`, `mosh-client` and `mosh-server` now use that fork's build,
not distro binaries. Its running sessions are not restarted by changing links.

## Use

For a direct shell, run from a fresh local Termux tab:

```sh
~/.local/bin/mosh-native \
  --ssh="ssh -p 22 -i $HOME/storage/downloads/Telegram/client_lewis_key" \
  --server=/home/lewis/.local/bin/mosh-native-server \
  lewis@100.74.187.127 -- fish -l
```

Use your own host, SSH key and command when needed. The wrapper uses SSH for
authentication and the history-aware Mosh transport afterward. Replace `fish -l`
with a direct app command if preferred. An explicit `--server` avoids depending
on the remote login shell's PATH.

For a tmux session keep using ordinary Mosh instead:

```sh
mosh --server=/home/lewis/.local/bin/mosh-server YOUR_HOST -- \
  /home/lewis/.local/bin/tmux -S /run/user/1000/tmux-simple-1000/server.sock \
  attach-session -t diet
```

The native path is for direct shells/apps, not tmux. No tmux sizing monitor is
involved: the direct application's PTY follows its single Mosh client's terminal
dimensions. Keyboard and zoom resize bursts settle for 120 ms before rendering
the matching remote geometry, with retained output restored into local scrollback.
Native history rendering already avoids entering the alternate screen;
`--no-init` is not required and is not itself a scrollback/resize fix.

The October 2026 server adds authenticated packet-age reporting without changing
the native wire protocol. Old clients can still connect, but protocol compatibility
does not imply safe wide-output resizing: the native2 client loses some text after
zoom round trips. Use the native6 client on Termux for the current resize replay
fix. Fresh native connections use the linked host server; existing servers do not
upgrade in place.

Direct Mosh survives network interruptions, but a new direct connection starts a
new shell/app; it does not reattach to the old program. Deliberately ending the
connection can close its app. Use tmux when persistent reattachment is required.

Do not launch this through an outer stock Mosh connection: that outer transport
would still discard history. Use a fresh local terminal. No mouse/copy mode,
keyboard prefix or server-side scrolling UI is added. Programs that request
mouse reporting still own mouse events while that reporting is active.

## Build And Install

Desktop prerequisites: C++17 compiler, make, autoconf, automake, pkg-config,
protoc/protobuf development files, OpenSSL, ncurses, zlib, Perl, curl and patch.

```sh
scripts/build.sh
scripts/link.sh
```

The build verifies the pinned upstream archive, applies the ordered patches in
a new directory, regenerates autotools files, compiles, and publishes symlinks under
`build/runtime`. The link script creates symlinks in `~/.local/bin` and refuses
conflicting existing paths. It does not stop, replace or migrate live servers.
Use `JOBS=N` to limit build parallelism. Build logs and hashes remain beside each
build. Run the build before the link script.

For Termux, `scripts/bundle-termux.sh` prepares a source archive, checksum and
installer under `build/termux-bundle`. Transfer those three files to Download,
then run inside a local Termux tab:

```sh
bash /sdcard/Download/mosh-native-install.sh
```

The installer verifies the bundle, installs build dependencies using Termux's
package manager, builds only the client in a fresh private directory, and
creates separate native-tool symlinks. It does not overwrite ordinary Mosh or
alter running Termux sessions. Termux needs permission to read shared storage.
It installs both `libprotobuf` (the library) and `protobuf` (the `protoc`
compiler), and checks that the compiler runs before extracting build sources.
ADB file transfer alone does not grant access to Termux's private app directory.
The Mosh client installer never reinstalls or replaces the Termux APK.
Build output and the tail of any failing build logs are also written to
`Download/mosh-native-install.log`. On Termux, rerunning the installer builds in
a fresh directory and replaces only symlinks recognized as belonging to an
earlier mosh-native bundle under `~/.local/share/mosh-native.XXXXXX`. Regular
files and unrelated links are refused before any links change. Old binaries
are retained for running processes. Reconnect the phone's Mosh client afterward;
do not stop the persistent tmux session or its program.

### Zoom And Client Versions

Check the phone client from a local Termux tab:

```sh
~/.local/bin/mosh-native-client --version
```

The current client is `1.4.0-native6`. Updating
only the host server cannot replace the client's local scrollback replay code.
The installer keeps old binaries for running connections; reconnect from the
local Termux tab to start using the new client. A fresh direct connection creates
a new shell, so finish valuable work before deliberately closing its predecessor.

Native3 handles ordinary wrapped resizes, but its resize archive retained only
the first network batch. At very narrow widths, especially with Unicode output,
the archive can exceed 8 KiB or 128 records. Later batches then replayed text
already stored by Termux, duplicating lines and disturbing their order. Patch
0004 retains every batch within the existing bounded local recorder, without a
wire-protocol change. It also records the terminal-specific reflow corrections
that were already present in the previously activated native3 host build, so a
fresh phone build no longer omits them.

Native4 also underestimated scrollback pulled into view after very narrow,
space-padded table output. The Google Play Termux `2025.10.05` emulator drops
soft-wrap metadata on space-only rows. Its resulting physical history can be
longer than the logical-record estimate; clearing the viewport then erased text
that had not been returned to scrollback. Patch 0005 measures the local cursor
with DEC's private position report after resize settles, preserves at least the
existing canonical row minimum, and restores the measured prefix before redraw.
Replies stay local rather than becoming Fish input. Fragmented replies, resize
races, normal keys and a bounded unsupported-terminal fallback have unit tests.
This fixes the reproduced Mosh text loss, not Termux's own padding/reflow defect.

Native5 also missed the cursor's empty cell when a prompt exactly filled the
new width. For an eight-character prompt shrunk to eight columns, Termux reflows
that cursor onto another row; Mosh's model left it in a phantom end column.
It consequently remembered too short a scrollback prefix and replayed a fragment
that Termux had already stored. Patch 0006 includes the cursor cell in the
Termux-specific width-reflow model. Its C++ regression uses independently
measured Termux cursor positions, and the integration tests check words, order,
duplication and actual line structure at 20, 12, 8, 5, 3 and 2 columns.
The VTE model and the native wire protocol are unchanged.

### Remaining Termux Alignment Defect

Updating Mosh alone is not a complete fix for the extreme-zoom table corruption.
The Google Play Termux `googleplay.2025.10.05` buffer skips an all-space wrapped
row as if it were an ordinary blank line. Re-inserting it loses the soft-wrap
flag, so columns break into separate lines on zoom-out. This also reproduces
with the emulator alone, without Fish, Mosh or tmux.

`terminal-fixes/termux-preserve-space-wrap.patch` fixes that condition in the
Termux app's `terminal-emulator/.../TerminalBuffer.java`. It is separate from the
ordered Mosh patches; neither Mosh build nor phone installer applies it to an APK.
The source-matched emulator passes the narrow table/prose cases with that patch.
The unmodified emulator's table alignment failures remain explicit expected
failures, not successful Mosh tests. Set `MOSH_TEST_TERMUX_WRAP_FIXED=1` only
when testing the independently patched terminal oracle.

The APK patch has not been installed. A Google Play APK's signing key prevents
an independently signed build from replacing it in place. Do not uninstall it
or change install sources without a verified backup and a deliberate migration
decision. Mosh's installer does not modify Termux app data or close live sessions.

## Protocol And Pipeline

1. The server's emulator records rows scrolled out of the full main-screen
   region. Soft-wrapped rows are joined into logical records with SGR styling.
   Alternate-screen scrolling and partial-region redraws are not chat history.
2. A bounded recorder assigns monotonically increasing record numbers. A small
   history batch is synchronized alongside the latest screen, with a separate
   application-level acknowledgement cursor. Unacknowledged records are offered
   again; screen updates do not wait for the entire history backlog.
3. The client skips already delivered records, clears only the visible viewport,
   writes new historical records into the terminal's normal scrollback, and
   acknowledges only after the output write succeeds. It then redraws the live
   screen. Native repainting neither enters the alternate screen nor uses
   screen-scroll shortcuts that would duplicate historical rows.
   Before repainting a taller terminal, the client restores history pulled into
   view by Termux/VTE resizing. It checks geometry before rendering, including
   when a resume signal arrives before the resize notification.
   Keyboard/resize bursts wait for 120 ms of stable geometry before sending the
   final size. Input and network processing continue during that pause. The
   client does not draw a remote frame with mismatched dimensions; that avoids
   scrolling an old tall frame through a newly shortened terminal. History and
   the screen redraw are written together after the geometry agrees.
   A resize can archive several network batches locally. The client remembers
   all of them, including a final partial logical record, rather than replaying
   all but the first batch into scrollback again.
   On Termux, a local cursor query supplements the logical row estimate. It runs
   only during a main-screen resize with acknowledged history, not on every
   redraw. Network and keyboard input continue while its reply is pending. A
   terminal that does not reply within 250 ms falls back to the existing estimate.
4. After a network interruption, the existing Mosh connection resumes delivery
   from that cursor. Starting a fresh direct connection starts a new server/app;
   persistent tmux reattachment uses the separate ordinary-Mosh path.
5. A finite command's EOF waits for outstanding history to drain. Explicit
   client shutdown and Mosh's configured network timeout can cancel that wait.

History uses the existing authenticated/encrypted Mosh connection, not an
additional listener, plaintext side channel, transcript file, or clipboard
service. A separate protocol ID prevents silent mixing with stock endpoints.

## Limits

- Prototype, not a claim of complete terminal emulation or zero overhead.
- Retention is capped at 8 MiB and 100,000 logical records per Mosh server.
  If the client falls behind that cap, it receives an explicit expiry notice.
- A record is capped at 32 KiB; an overlong logical line is replaced by an
  explicit omission notice. Incomplete soft-wrapped lines are published once
  committed as a complete logical line, or when the program ends.
- Batches normally contain at most 8 KiB and 128 records; one larger record can
  occupy a batch by itself. History shares the UDP transport and consumes
  bandwidth. This is not a guarantee of unchanged latency on a saturated link.
- Termux/VTE retain their own scrollback limits. Server history retention does
  not increase the terminal emulator's configured scrollback capacity.
- A disconnected client can leave an EOF-draining server alive until it resumes
  or a configured `MOSH_SERVER_NETWORK_TMOUT` expires. Retained memory is bounded.
- No stock-Mosh compatibility fallback. If a peer reports a protocol mismatch,
  use native builds on both sides or the working SSH path.
- Actual Android build/install, touch gestures, clipboard UI, cellular roaming,
  complex width/Unicode reflow and long-duration load require device validation.
  Tests cover short records, long ASCII/Unicode records and repeated Termux
  zoom round trips down to 2 columns by 2 rows. They do not establish lossless
  reflow for every combination of content, cursor location and terminal model.
- Three desktop VTE wide-table resize cases still fail on the current native6
  profile, as on native3 and native4. The Termux zoom fix does not resolve that
  separate issue; these tests remain failing rather than being silently skipped.
- Termux's own extreme-width reflow can split space-padded rows even without
  Mosh. `tests/test_termux_padding.py` is an expected failure isolating that
  defect. Native6 fixes the additional cursor-boundary duplication, but cannot
  repair already damaged native scrollback layout or restore previously lost text.
- `native2` uses the same history protocol as `native1`. Its keyboard-resize fix
  is client-side, so that fix alone does not require restarting a server. The
  newer packet-status API needs a fresh server connection.
- During a resize, the last local screen stays visible until matching remote
  dimensions arrive. An interrupted network can extend that visual pause;
  key handling and normal Mosh reconnect processing are not paused.

## Packet Reporting

Patch 0002 supplies the same owner-only `mosh-status/PID.sock` API as the current
ordinary Mosh server. It exposes the timestamp of the last fresh authenticated
client packet, not keyboard idle time. Unauthenticated traffic, replayed packets
and local status queries do not refresh it. No extra network listener or polling
thread is added; requests use the existing event loop and are bounded.

`tmux-mosh clients` recognizes native servers as `mosh (PID)` / `direct`, reports
their packet `IDLE`, foreground app/command and PTY size. `tmux-mosh cleanup
--dry-run` previews cleanup using the same packet timestamp; actual cleanup can
terminate a direct app. Old native servers without this patch keep running but
cannot expose an exact packet age; start a fresh connection to use the new build.

## Verification

Tests use synthetic programs, private HOME/XDG directories and loopback-only UDP
sockets. They never attach to production sessions, scan a network, or drive the
real phone UI. The independent VTE and upstream Termux emulators are reused from
the maintained sibling `tmux-simple` project. The status tests also exercise its
read-only inventory and scoped cleanup dry-run helpers.

```sh
scripts/unit-tests.sh
UV_CACHE_DIR=/data/.cache/uv uv run --project ../tmux-simple pytest -q tests
shellcheck scripts/*.sh
shfmt -d scripts/*.sh
```

Tests select the currently linked release by default. `MOSH_BUILD` can select
another release, and `MOSH_COMPAT_CLIENT` tests a previous native client against
the current server. `verification.json` maps contracts, evidence and manual gaps.
The original native2 desktop clean build passed 31 integration/installer cases,
six additional native1-server compatibility cases, and the C++ history/resize
checks. The restored October release passed 35 integration/installer cases,
including the previous native2 client against the new packet-reporting server,
plus the C++ history/resize checks. The user confirmed the phone already has
`1.4.0-native2`; no phone rebuild was needed solely for packet-age reporting.
The later zoom-loss reproductions require the current native6 client on the
phone, with the independent Termux APK alignment defect still outstanding.
`tests/test_zoom.py` checks complete output, order
and continued input across repeated narrow/wide resizes; the C++ suite separately
checks resize archives exceeding each wire-batch limit. Physical keyboard
animation, touch behavior and the full upstream terminal-emulation suite remain
manual gates.

## Project Structure

```text
mosh/
  configure.ac, Makefile.am           upstream build definitions with native-profile changes
  src/frontend/                     client, server, viewport and local status endpoint
  src/network/                      authenticated transport and history protocol
  src/statesync/, src/protobufs/    state synchronization and protocol messages
  src/terminal/                     terminal emulator, history retention and reflow
  src/crypto/, src/util/            upstream cryptography and utilities
  src/tests/                        upstream unit checks
  scripts/mosh.pl                    tracked history-profile launcher
  autogen.sh, conf/, m4/             retained upstream bootstrap inputs
  man/, debian/, fedora/, macosx/    retained upstream documentation and packaging
  patches/0001-native-history.patch   emulator, protocol, client, server and wrapper changes
  patches/0002-last-received.patch    same-user status socket and authenticated packet timestamp
  patches/0003-main-screen-reflow.patch  main-screen wrapping and resize archive tracking
  patches/0004-complete-client-reflow.patch  terminal-specific reflow and multi-batch resize replay
  patches/0005-measured-termux-history.patch  local cursor query before resize-history restoration
  patches/0006-cursor-boundary-reflow.patch  Termux cursor-cell reflow and resize deduplication
  compat/last-received.patch          ordinary-protocol authenticated packet-age profile
  compat/server-status.h             owner-restricted local status endpoint for that profile
  terminal-fixes/termux-preserve-space-wrap.patch  separate Termux APK source fix, not automatically installed
  scripts/build.sh                   pinned archive + ordered patches -> binaries and hashes
  scripts/build-compat.sh             pinned archive + compat profile -> ordinary-protocol fork binaries
  scripts/link.sh                    built tools -> non-overwriting user-local symlinks
  scripts/unit-tests.sh              built libraries + C++ tests -> bounded protocol checks
  scripts/update-patch.sh             development source versus pristine source -> patch
  scripts/bundle-termux.sh            source, scripts and archive -> portable phone bundle
  scripts/termux-install.sh           phone bundle -> Termux dependencies, build and symlinks
  tests/native_history_test.cc        acknowledgement, replay, bounds and mode tests
  tests/test_terminal.py              direct Mosh/PTY/emulator and ordinary-Mosh compatibility
  tests/test_status.py                authenticated age, replay rejection, inventory and cleanup
  tests/conftest.py                   maintained sibling helpers/oracles for desktop tests
  tests/test_install.py               symlink collision, repeat-install and platform guards
  tests/workload.py                   synthetic input/output workload and private test log
  tests/resize_workload.py            synthetic fullscreen app and private resize/input logs
  tests/zoom_workload.py              static wide ASCII/Unicode output without app repaint
  tests/test_tiny_zoom.py             prose/table content and exact line structure down to 2x2
  tests/test_zoom.py                  repeated severe zoom, text/order preservation and input
  tests/wrapped_workload.py           synthetic shell table, geometry and input logs
  tests/test_wrapped_resize.py        existing Termux/VTE wide-table resize checks
  verification.json                  behavior inventory and recorded verification results
  build/                             ignored source trees, binaries and phone bundle
  artifacts/                         ignored synthetic test results
```

The patch is based on upstream Mosh 1.4.0, licensed under GPLv3 or later with
Mosh's OpenSSL linking exception; see `COPYING` and source-file notices.

References: [Mosh's protocol explanation](https://mosh.org/#techinfo),
[upstream source](https://github.com/mobile-shell/mosh),
[Termux Mosh build recipe](https://github.com/termux/termux-packages/tree/master/packages/mosh).
