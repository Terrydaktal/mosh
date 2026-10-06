"""Synthetic coloured connection table; never inspects real sessions."""

import sys


def table(colour=True):
    lines = [
        "VIA                    TYPE        SESSION          APP                   IDLE  PEER           SIZE     SIZING"
    ]
    for index in range(21):
        label = f"row-{index:02d}-terminal"
        if colour and index % 3 == 0:
            label = f"\033[41m{label}\033[0m"
        # Padding counts printable cells, not the SGR escape sequence.
        lines.append(
            label
            + " " * (23 - len(f"row-{index:02d}-terminal"))
            + f"{'opsec-tmux' if index % 4 == 0 else 'tmux':<12}"
            + f"{'pi-85ce9bb01a55' if index % 4 == 0 else 'diet':<17}"
            + f"{'python3.14 (3573358)':<22}"
            + f"{'0s':<6}{'100.70.36.28':<15}{'152x161':<9}"
            + f"unknown :end-{index:02d}"
        )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.stdout.write(table())
