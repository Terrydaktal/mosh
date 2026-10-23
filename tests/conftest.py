"""Use the maintained terminal oracles and local session-reporting helpers."""

import os
import sys
from pathlib import Path

parent = Path(__file__).resolve().parents[2]
shared = next(
    (parent / name for name in ("tmux", "tmux-simple") if (parent / name).is_dir()),
    parent / "tmux",
)
sys.path.insert(0, str(shared))
sys.path.insert(0, str(shared / "tests"))
sys.path.insert(
    0, str(Path(os.environ.get("TMUX_MOSH_ROOT", Path.home() / "Dev/tmux-mosh")))
)
