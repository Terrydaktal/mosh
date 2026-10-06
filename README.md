# mosh

This fork records maintained changes to Mosh on `main`. Start with the pinned
Mosh 1.4.0 archive and apply the patches present in this revision in filename order.

## Structure And Operation

```text
COPYING             Upstream GPL license and exception
scripts/build.sh    Verify the source archive, apply patches and compile
build/downloads/    Ignored cached archive
build/release.*/    Ignored fresh build directories and logs
build/runtime/     Ignored symlinks to the newly compiled programs
verification.json  Project identity and verification record
```

Run `scripts/build.sh` first. Inputs are the pinned source archive, compiler and
patches; outputs are client/server/wrapper symlinks, logs and checksums in `build/`.
Use `JOBS=N` to limit parallel compilation. This does not activate installed links
or restart live servers. Dependencies include the C++17 compiler, autotools,
protobuf/protoc, OpenSSL, ncurses, zlib, curl, Perl, make and patch.

## Native Terminal History

The history-aware client/server retain bounded main-screen scrollback and deliver
it with acknowledgements alongside the live screen. Both endpoints must use this
profile; it is not ordinary-Mosh wire compatible. Alternate-screen and partial
scroll-region output are not normal history. Finite commands drain acknowledged
history before exit. Run scripts/link.sh after building to install separate native
tools by symlink; unrelated files and links are refused before changes occur.
tests/ contains isolated PTY/emulator and C++ protocol checks; unit-tests.sh uses
the fresh compiled source. update-patch.sh regenerates the core patch from builds.

## Keyboard And Rapid Resizing

The native client settles resize bursts for 120 ms, notices geometry changes even
before SIGWINCH is processed, and withholds remote frames for obsolete dimensions.
The bounded debounce does not reinterpret ordinary input as resize events.

## Authenticated Client Packet Age

Both native-history and ordinary-wire-protocol servers expose the monotonic time
of their last authenticated client packet through a local owner-restricted status
socket. This is not keyboard idle or session-start time; no timestamp is invented
before the first packet. Existing clients need no status protocol change. The
compat/ patch/header and scripts/build-compat.sh build the ordinary profile,
which is suitable for tmux-owned history. Status tests use private loopback peers.

## Main-Screen Width Reflow

Wrapped main-screen rows are joined and rewrapped at the new terminal width while
preserving character content, styling and cursor position. Retained history tracks
rows already archived locally so a later redraw need not replay them twice. Wide
table regression cases remain tests; this does not promise all emulators agree.

## Upstream Ancestry

This main branch starts at the upstream mosh-1.4.0 Git release, not an unrelated
root commit. The upstream source remains tracked. Each feature commit also
materializes its patch in the corresponding source files; the reproducible build
continues to start with the verified release archive. Following upstream master
requires a separate tested port, not merely attaching a different parent.
