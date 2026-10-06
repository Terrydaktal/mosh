import hashlib
import os
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_link_install_is_symlink_only_and_idempotent(tmp_path):
    destination = tmp_path / "bin"
    for _ in range(2):
        result = subprocess.run(
            [str(ROOT / "scripts/link.sh"), str(destination)],
            capture_output=True,
            timeout=5,
        )
        assert result.returncode == 0, result.stderr
        for name in ("mosh-native", "mosh-native-client", "mosh-native-server"):
            assert (destination / name).is_symlink()
            assert os.readlink(destination / name) == str(ROOT / "build/runtime" / name)


def test_conflict_is_preserved_without_partial_install(tmp_path):
    protected = tmp_path / "mosh-native-client"
    protected.write_text("unrelated user file")
    result = subprocess.run(
        [str(ROOT / "scripts/link.sh"), str(tmp_path)], capture_output=True, timeout=5
    )
    assert result.returncode != 0
    assert protected.read_text() == "unrelated user file"
    assert not (tmp_path / "mosh-native").exists()


def test_phone_installer_refuses_desktop_without_running_package_manager(tmp_path):
    environment = os.environ.copy()
    environment.pop("PREFIX", None)
    environment["HOME"] = str(tmp_path)
    result = subprocess.run(
        [str(ROOT / "scripts/termux-install.sh")],
        env=environment,
        capture_output=True,
        timeout=5,
    )
    assert result.returncode != 0
    assert b"inside a local Termux" in result.stderr
    assert not (tmp_path / ".local").exists()


@pytest.mark.parametrize("compiler", ["working", "missing", "broken"])
def test_phone_installer_installs_and_checks_compiler(tmp_path, compiler):
    home = tmp_path / "home"
    home.mkdir()
    prefix = tmp_path / "com.termux/files/usr"
    bin_dir = prefix / "bin"
    bin_dir.mkdir(parents=True)
    # A private PATH prevents the desktop's protoc from hiding a missing package.
    for command in (
        "bash",
        "dirname",
        "tee",
        "date",
        "sha256sum",
        "mkdir",
        "mktemp",
        "tar",
        "gzip",
        "awk",
        "tail",
        "chmod",
    ):
        target = shutil.which(command)
        assert target, f"test prerequisite missing: {command}"
        (bin_dir / command).symlink_to(target)

    def executable(path, contents):
        path.write_text("#!/bin/sh\nset -eu\n" + contents)
        path.chmod(0o755)

    executable(
        bin_dir / "pkg",
        'printf "%s\\n" "$@" > "$HOME/packages"\n'
        'for package in "$@"; do\n'
        '  if [ "$package" = protobuf ] && [ "$TEST_COMPILER" != missing ]; then\n'
        '    status=0; [ "$TEST_COMPILER" != broken ] || status=1\n'
        '    printf "#!/bin/sh\\nexit %s\\n" "$status" > "$PREFIX/bin/protoc"\n'
        '    chmod +x "$PREFIX/bin/protoc"\n'
        "  fi\n"
        "done\n",
    )
    executable(bin_dir / "pkg-config", "exit 0\n")
    source = tmp_path / "source/scripts"
    source.mkdir(parents=True)
    executable(
        source / "build.sh",
        ': > "$HOME/build-started"\nprotoc --version\n'
        'printf "%s\\n" "$@" > "$HOME/build-args"\n',
    )
    executable(source / "link.sh", 'printf "%s\\n" "$@" > "$HOME/link-started"\n')
    download = tmp_path / "Download"
    download.mkdir()
    shutil.copyfile(ROOT / "scripts/termux-install.sh", download / "install.sh")
    archive = download / "mosh-native-source.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        bundle.add(source, arcname="scripts")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (download / "mosh-native-source.sha256").write_text(f"{digest}  {archive.name}\n")
    environment = os.environ.copy()
    environment.update(
        HOME=str(home), PREFIX=str(prefix), PATH=str(bin_dir), TEST_COMPILER=compiler
    )
    result = subprocess.run(
        [str(bin_dir / "bash"), str(download / "install.sh")],
        env=environment,
        capture_output=True,
        timeout=10,
    )
    assert "protobuf" in (home / "packages").read_text().splitlines()
    if compiler == "working":
        assert result.returncode == 0, result.stdout + result.stderr
        assert (home / "build-args").read_text().strip() == "--disable-server"
        assert (home / "link-started").exists()
        assert (home / "link-started").read_text().strip() == "--upgrade-termux"
    else:
        assert result.returncode != 0
        assert b"working protoc compiler" in result.stdout + result.stderr
        assert not (home / "build-started").exists()
        assert not (home / "link-started").exists()
        assert not (home / ".local").exists()


@pytest.mark.parametrize("foreign", [False, True])
def test_termux_upgrade_only_replaces_owned_links(tmp_path, foreign):
    home = tmp_path / "home"
    old_root = home / ".local/share/mosh-native.A1b2C3"
    old_runtime = old_root / "build/runtime"
    old_runtime.mkdir(parents=True)
    old_root.chmod(0o700)
    (old_root / "verification.json").write_text('{"product": "mosh-native"}\n')
    destination = home / ".local/bin"
    destination.mkdir()
    names = ("mosh-native", "mosh-native-client", "mosh-native-server")
    previous = {}
    for name in names:
        target = old_runtime / name
        target.write_text("old binary left in place")
        if foreign and name == "mosh-native-client":
            target = tmp_path / "unrelated-client"
            target.write_text("unrelated user binary")
        previous[name] = str(target)
        (destination / name).symlink_to(target)
    environment = os.environ.copy()
    environment.update(HOME=str(home), PREFIX=str(tmp_path / "com.termux/files/usr"))
    result = subprocess.run(
        [str(ROOT / "scripts/link.sh"), "--upgrade-termux"],
        env=environment,
        capture_output=True,
        timeout=5,
    )
    assert (result.returncode != 0) == foreign, result.stderr
    for name in names:
        assert (old_runtime / name).read_text() == "old binary left in place"
        expected = previous[name] if foreign else str(ROOT / "build/runtime" / name)
        assert os.readlink(destination / name) == expected
