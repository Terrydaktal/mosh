#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
destination="$root/build/termux-bundle"
mkdir -p "$destination"
tar --exclude=__pycache__ --exclude='*.pyc' -czf "$destination/mosh-native-source.tar.gz" -C "$root" \
	README.md COPYING patches scripts tests verification.json build/downloads/mosh-1.4.0.tar.gz
(
	cd -- "$destination"
	sha256sum mosh-native-source.tar.gz >mosh-native-source.sha256
)
cp -- "$root/scripts/termux-install.sh" "$destination/mosh-native-install.sh"
printf 'Termux bundle: %s\n' "$destination"
