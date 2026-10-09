#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
runtime=${BUILD_RUNTIME:-"$root/build/runtime"}
mkdir -p "$root/build" "$runtime"
for command in tar autoreconf make pkg-config protoc; do
	if ! command -v "$command" >/dev/null; then
		printf 'Missing build prerequisite: %s\n' "$command" >&2
		exit 1
	fi
done
work=$(mktemp -d "$root/build/release.XXXXXX")
trap 'echo "Build logs: $work/{autoreconf,configure,compile}.log" >&2' ERR
bash "$root/scripts/source-snapshot.sh" "$work"
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
names=(mosh mosh-client mosh-native mosh-native-client)
targets=("$work/scripts/mosh" "$work/src/frontend/mosh-client" "$work/scripts/mosh" "$work/src/frontend/mosh-client")
if [[ -x "$work/src/frontend/mosh-server" ]]; then
	names+=(mosh-server mosh-native-server)
	targets+=("$work/src/frontend/mosh-server" "$work/src/frontend/mosh-server")
fi
for name in "${names[@]}"; do
	if [[ -e "$runtime/$name" && ! -L "$runtime/$name" ]]; then
		printf 'Refusing to replace non-symlink: %s\n' "$runtime/$name" >&2
		exit 1
	fi
done
for target in "${targets[@]}"; do
	[[ -x "$target" ]] || {
		printf 'Build did not produce executable: %s\n' "$target" >&2
		exit 1
	}
done
sha256sum "$work/SOURCE-SHA256SUMS" "${targets[@]}" >"$work/BUILD-SHA256SUMS"
for i in "${!names[@]}"; do
	ln -sfn -- "${targets[$i]}" "$runtime/${names[$i]}"
done
printf 'Built: %s\nBuild logs: %s\n' "$runtime" "$work"
