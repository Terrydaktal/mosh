#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
destination=${1:-$HOME/.local/bin}

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
		if [[ $previous != "$target" ]]; then
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
