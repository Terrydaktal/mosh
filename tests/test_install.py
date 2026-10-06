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
