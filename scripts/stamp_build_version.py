#!/usr/bin/env python3
"""Validate a release version, stamp VERSION, and emit CI environment values."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRERELEASE_IDENTIFIER = r"(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)"
SEMVER = re.compile(
    rf"^(?P<major>0|[1-9]\d*)\."
    rf"(?P<minor>0|[1-9]\d*)\."
    rf"(?P<patch>0|[1-9]\d*)"
    rf"(?:-(?P<prerelease>{PRERELEASE_IDENTIFIER}(?:\.{PRERELEASE_IDENTIFIER})*))?"
    r"(?:\+(?P<build>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)


def version_values(raw_version: str) -> tuple[str, str]:
    version = raw_version.strip().removeprefix("v")
    match = SEMVER.fullmatch(version)
    if not match:
        raise ValueError(f"Version must be SemVer (for example 1.2.3 or 1.2.3-beta.1): {raw_version}")
    file_version = ".".join(
        (match.group("major"), match.group("minor"), match.group("patch"), "0")
    )
    return version, file_version


def stamp_version(raw_version: str, path: Path = ROOT / "VERSION") -> tuple[str, str]:
    version, file_version = version_values(raw_version)
    path.write_text(f"{version}\n", encoding="utf-8")
    return version, file_version


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: stamp_build_version.py VERSION")
    try:
        version, file_version = stamp_version(sys.argv[1])
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"BUILD_VERSION={version}")
    print(f"FILE_VERSION={file_version}")


if __name__ == "__main__":
    main()
