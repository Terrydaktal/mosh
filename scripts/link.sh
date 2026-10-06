#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
upgrade_termux=0
if [[ ${1:-} == --upgrade-termux ]]; then
	upgrade_termux=1
	shift
	if [[ ${PREFIX:-} != */com.termux/files/usr ]]; then
		printf 'Termux upgrades must run inside Termux.\n' >&2
		exit 1
	fi
fi
destination=${1:-$HOME/.local/bin}

owned_termux_link() {
	local name=$1 previous=$2 old_root
	[[ $upgrade_termux == 1 ]] || return 1
	old_root=${previous%/build/runtime/"$name"}
	[[ "$old_root/build/runtime/$name" == "$previous" ]] || return 1
	[[ ${old_root%/*} == "$HOME/.local/share" ]] || return 1
	[[ ${old_root##*/} =~ ^mosh-native\.[[:alnum:]]{6}$ ]] || return 1
	[[ -d "$old_root" && ! -L "$old_root" && -O "$old_root" ]] || return 1
	[[ -r "$old_root/verification.json" ]] || return 1
	grep -Eq '"product"[[:space:]]*:[[:space:]]*"mosh-native"' "$old_root/verification.json"
}

names=(mosh-native mosh-native-client)
if [[ -x "$root/build/runtime/mosh-native-server" ]]; then
	names+=(mosh-native-server)
fi
for name in "${names[@]}"; do
	target="$root/build/runtime/$name"
	[[ -x "$target" ]] || {
		printf 'Build first: %s\n' "$root/scripts/build.sh" >&2
		exit 1
	}
	if [[ -e "$destination/$name" || -L "$destination/$name" ]]; then
		if [[ ! -L "$destination/$name" ]]; then
			printf 'Refusing to replace existing path: %s\n' "$destination/$name" >&2
			exit 1
		fi
		previous=$(readlink -- "$destination/$name")
		if [[ $previous != "$target" ]] && ! owned_termux_link "$name" "$previous"; then
			printf 'Refusing to replace unrelated symlink: %s\n' "$destination/$name" >&2
			exit 1
		fi
	fi
done
mkdir -p -- "$destination"
for name in "${names[@]}"; do
	ln -sfn -- "$root/build/runtime/$name" "$destination/$name"
done
printf 'Linked separate native-history tools in %s; stock Mosh is unchanged.\n' "$destination"
