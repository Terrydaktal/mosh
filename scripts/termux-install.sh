#!/usr/bin/env bash
set -euo pipefail
if [[ ${PREFIX:-} != */com.termux/files/usr ]]; then
	printf 'Run this inside a local Termux tab, not over SSH/Mosh.\n' >&2
	exit 1
fi
bundle_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
archive="$bundle_dir/mosh-native-source.tar.gz"
if [[ ! -r "$archive" || ! -r "$bundle_dir/mosh-native-source.sha256" ]]; then
	printf 'Cannot read the source bundle in %s. Check Termux shared-storage permission.\n' "$bundle_dir" >&2
	exit 1
fi
log="$bundle_dir/mosh-native-install.log"
exec > >(tee -a "$log") 2>&1
printf '\nStarting mosh-native client build: %s\n' "$(date -Is)"
(
	cd -- "$bundle_dir"
	sha256sum --check mosh-native-source.sha256
)
pkg install -y clang make autoconf automake pkg-config libprotobuf protobuf abseil-cpp \
	libandroid-support openssl ncurses patch curl tar perl
if ! command -v protoc >/dev/null 2>&1 || ! protoc --version; then
	printf 'The protobuf package must provide a working protoc compiler. Check its installation and PATH before retrying.\n' >&2
	exit 1
fi
mkdir -p "$HOME/.local/share"
root=$(mktemp -d "$HOME/.local/share/mosh-native.XXXXXX")
tar -xzf "$archive" -C "$root"
readarray -t absl_modules < <(pkg-config --list-all | awk '$1 ~ /^absl_/ {print $1}')
if [[ ${#absl_modules[@]} -gt 0 ]]; then
	# Termux's protobuf pkg-config metadata may omit its Abseil interface libs.
	LIBS="${LIBS:-} $(pkg-config --libs "${absl_modules[@]}") -landroid-support"
	export LIBS
fi
if ! JOBS=4 bash "$root/scripts/build.sh" --disable-server; then
	printf 'Build failed. Logs: %s/build/release.*/\n' "$root" >&2
	for build_log in "$root"/build/release.*/*{configure,compile,autoreconf}.log; do
		if [[ -f "$build_log" ]]; then
			printf '\n--- %s ---\n' "$build_log"
			tail -n 40 "$build_log"
		fi
	done
	exit 1
fi
bash "$root/scripts/link.sh" --upgrade-termux
printf '\nClient built and linked. Stock Mosh and running sessions were not changed.\n'
printf 'For a direct shell/app, from a local Termux tab use:\n  ~/.local/bin/mosh-native --server=/home/lewis/.local/bin/mosh-native-server YOUR_HOST -- fish -l\n'
printf 'For tmux sessions keep using ordinary mosh with /home/lewis/.local/bin/mosh-server.\n'
printf 'Build/source directory: %s\n' "$root"
