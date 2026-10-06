#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
binary=$(readlink -f "$root/build/runtime/mosh-native-server")
source_dir=${MOSH_BUILD:-${binary%/src/frontend/mosh-native-server}}
mkdir -p "$root/build/tests"
read -r -a flags <<<"$(pkg-config --cflags --libs protobuf ncursesw openssl)"
includes=()
for dir in frontend terminal statesync protobufs crypto util; do
	includes+=("-I$source_dir/src/$dir")
done
"${CXX:-c++}" -std=c++17 -O2 -g -DHAVE_CONFIG_H -I"$source_dir/src/include" \
	"${includes[@]}" "$root/tests/native_history_test.cc" \
	-Wl,--start-group "$source_dir"/src/{statesync,terminal,crypto,util,protobufs}/libmosh*.a \
	-Wl,--end-group "${flags[@]}" -o "$root/build/tests/native-history-test"
"$root/build/tests/native-history-test"
