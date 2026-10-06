#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
before="$root/build/upstream/mosh-1.4.0"
after="$root/build/development"
files=(
	configure.ac scripts/Makefile.am scripts/mosh.pl
	src/frontend/Makefile.am src/frontend/mosh-server.cc src/frontend/stmclient.cc src/frontend/stmclient.h src/frontend/nativeviewport.h
	src/network/network.h src/network/networktransport-impl.h
	src/protobufs/hostinput.proto src/protobufs/userinput.proto
	src/statesync/completeterminal.cc src/statesync/completeterminal.h src/statesync/user.cc src/statesync/user.h
	src/terminal/Makefile.am src/terminal/nativehistory.cc src/terminal/nativehistory.h
	src/terminal/terminal.h src/terminal/terminaldisplay.cc src/terminal/terminaldisplay.h
	src/terminal/terminaldisplayinit.cc src/terminal/terminalframebuffer.cc src/terminal/terminalframebuffer.h
	src/terminal/terminalfunctions.cc
)
temporary=$(mktemp "$root/patches/native-history.XXXXXX")
for file in "${files[@]}"; do
	original="$before/$file"
	[[ -f "$original" ]] || original=/dev/null
	diff -u --label "a/$file" --label "b/$file" "$original" "$after/$file" >>"$temporary" || [[ $? == 1 ]]
done
mv -- "$temporary" "$root/patches/0001-native-history.patch"
