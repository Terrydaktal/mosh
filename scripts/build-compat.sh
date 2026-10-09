#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
printf 'The separate compatibility build is retired; building unified Mosh.\n' >&2
exec bash "$root/scripts/build.sh" "$@"
