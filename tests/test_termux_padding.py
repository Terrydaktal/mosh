"""Keep the terminal's own extreme-zoom defect separate from transport tests."""

import base64

import pytest
from colored_table_workload import table
from terminal_harness import Emulator


@pytest.mark.xfail(
    strict=True,
    reason="Termux drops soft-wrap flags on space-only rows during width reflow",
)
def test_termux_reflows_space_padded_rows_without_mosh():
    term = Emulator("termux", 81, 59)
    try:
        term.feed((table().replace("\n", "\r\n") + "prompt> ").encode())
        for cols, rows in ((20, 14), (10, 7), (5, 4), (10, 7), (20, 14), (152, 161)):
            term.command(f"SIZE {cols} {rows}")
        visible = [base64.b64decode(row).rstrip() for row in term.state["lines"]]
        for line in table(False).encode().splitlines():
            assert line in visible, "Termux split a previously soft-wrapped table row"
    finally:
        term.close()
