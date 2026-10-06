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

## Complete Resize-History Replay

The client retains every bounded resize-history batch rather than just the first
8 KiB/128-record slice. The selected terminal reflow model is carried through the
launcher and replay. Unicode, large archives, narrow widths and coloured Fish
output have distinct regressions; emulator limitations must remain visible.

## Measured Local History Restoration

After resize settles, a local DEC private cursor-position report measures the
history prefix pulled into view. That prefix is restored before redraw instead of
being erased by an inaccurate row estimate. Fragmented replies remain local;
ordinary keys pass through and unsupported-terminal fallback is bounded.

## Exact-Width Termux Cursor Boundaries

The Termux width-reflow model includes the cursor blank cell when the prompt
exactly fills the new width. Regressions check independently measured positions
and output ordering at 20, 12, 8, 5, 3 and 2 columns. Native wire protocol and VTE
model are unchanged. Termux's separate space-padding defect remains outstanding.

## Termux Source Bundles And Safe Upgrades

bundle-termux.sh emits a source archive, checksum and installer in build/termux-bundle.
Transfer those files to Download and run the installer inside a local Termux tab.
It checks the archive, installs libprotobuf plus the protoc compiler, validates
dependencies, builds in a new private directory, logs failures, and replaces only
recognised native-tool symlinks. Unrelated files, other links, old binaries, app
data and running sessions are preserved. It never installs or removes a Termux APK.

## Separate Termux Emulator Fix

The terminal-fixes/ patch preserves the soft-wrap flag of space-only wrapped rows
inside Termux's Java terminal buffer. The issue reproduces without Mosh or tmux.
This is an independently applicable APK-source patch, not part of either Mosh
build or the phone installer. Emulator regressions record the unpatched defect as
expected failures. No APK or app data is changed by building or packaging Mosh.

## Upstream Ancestry

This main branch starts at the upstream mosh-1.4.0 Git release, not an unrelated
root commit. The upstream source remains tracked. Each feature commit also
materializes its patch in the corresponding source files; the reproducible build
continues to start with the verified release archive. Following upstream master
requires a separate tested port, not merely attaching a different parent.
