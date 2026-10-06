#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
destination="$root/build/termux-bundle"
mkdir -p "$destination"
source=$(mktemp -d "$root/build/termux-source.XXXXXX")
trap 'rm -rf -- "$source"' EXIT
bash "$root/scripts/source-snapshot.sh" "$source"
tar -czf "$destination/mosh-native-source.tar.gz" -C "$source" .
(
	cd -- "$destination"
	sha256sum mosh-native-source.tar.gz >mosh-native-source.sha256
)
cp -- "$root/scripts/termux-install.sh" "$destination/mosh-native-install.sh"
printf 'Termux bundle: %s\n' "$destination"
