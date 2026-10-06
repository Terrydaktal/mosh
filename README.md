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

## Upstream Ancestry

This main branch starts at the upstream mosh-1.4.0 Git release, not an unrelated
root commit. The upstream source remains tracked. Each feature commit also
materializes its patch in the corresponding source files; the reproducible build
continues to start with the verified release archive. Following upstream master
requires a separate tested port, not merely attaching a different parent.
