#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
archive="$root/build/downloads/mosh-1.4.0.tar.gz"
sha=872e4b134e5df29c8933dff12350785054d2fd2839b5ae6b5587b14db1465ddd
mkdir -p "$root/build/downloads" "$root/build/runtime"
for command in curl tar patch autoreconf make pkg-config protoc; do
	if ! command -v "$command" >/dev/null; then
		printf 'Missing build prerequisite: %s\n' "$command" >&2
		exit 1
	fi
done
if [[ ! -f "$archive" ]]; then
	partial=$(mktemp "$archive.XXXXXX")
	trap '[[ ! -f "$partial" ]] || rm -- "$partial"' EXIT
	curl --fail --location --retry 2 --max-time 120 \
		https://github.com/mobile-shell/mosh/releases/download/mosh-1.4.0/mosh-1.4.0.tar.gz -o "$partial"
	printf '%s  %s\n' "$sha" "$partial" | sha256sum --check --status
	mv -- "$partial" "$archive"
	trap - EXIT
fi
printf '%s  %s\n' "$sha" "$archive" | sha256sum --check --status
work=$(mktemp -d "$root/build/release.XXXXXX")
tar -xzf "$archive" --strip-components=1 -C "$work"
shopt -s nullglob
patch_files=("$root"/patches/*.patch)
for patch_file in "${patch_files[@]}"; do
	patch --batch --forward -d "$work" -p1 <"$patch_file"
done
utempter=--with-utempter
if [[ ${PREFIX:-} == */com.termux/files/usr ]]; then
	utempter=--without-utempter
fi
(
	cd -- "$work"
	autoreconf -fi >autoreconf.log 2>&1
	./configure CXXFLAGS="${CXXFLAGS:--O2 -g -std=c++17}" "$utempter" "$@" >configure.log 2>&1
	make -j "${JOBS:-4}" >compile.log 2>&1
)
if [[ -n ${PREFIX:-} && -x "$PREFIX/bin/perl" ]]; then
	# Android has no /usr/bin/env. Do not depend on Termux exec interposition.
	sed -i "1c#!$PREFIX/bin/perl" "$work/scripts/mosh"
fi
names=(mosh mosh-client)
targets=("$work/scripts/mosh" "$work/src/frontend/mosh-client")
if [[ -x "$work/src/frontend/mosh-server" ]]; then
	names+=(mosh-server)
	targets+=("$work/src/frontend/mosh-server")
fi
for name in "${names[@]}"; do
	if [[ -e "$root/build/runtime/$name" && ! -L "$root/build/runtime/$name" ]]; then
		printf 'Refusing to replace non-symlink: %s\n' "$root/build/runtime/$name" >&2
		exit 1
	fi
done
for i in "${!names[@]}"; do
	ln -sfn -- "${targets[$i]}" "$root/build/runtime/${names[$i]}"
done
sha256sum "$archive" "${patch_files[@]}" "${targets[@]}" >"$work/BUILD-SHA256SUMS"
printf 'Built: %s\nBuild logs: %s\n' "$root/build/runtime" "$work"
