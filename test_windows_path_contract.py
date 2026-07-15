"""Prevent tracked paths that cannot be checked out on Windows."""

from __future__ import annotations

import re
import subprocess
from pathlib import PurePosixPath


INVALID_CHARS = set('<>:"\\|?*')
RESERVED_NAME = re.compile(
    r"^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?$",
    re.IGNORECASE,
)


def path_problem(path: str) -> str | None:
    for component in PurePosixPath(path).parts:
        if any(character in INVALID_CHARS or ord(character) < 32 for character in component):
            return "contains a Windows-invalid character"
        if component.endswith((" ", ".")):
            return "ends with a space or period"
        if RESERVED_NAME.fullmatch(component):
            return "uses a reserved Windows device name"
    return None


def main() -> None:
    tracked = subprocess.check_output(
        ["git", "ls-files", "-z"],
        text=True,
    ).split("\0")
    problems = {
        path: problem
        for path in tracked
        if path and (problem := path_problem(path))
    }
    assert not problems, f"Windows-incompatible tracked paths: {problems}"
    print("PASS: all tracked paths are Windows-compatible")


if __name__ == "__main__":
    main()
