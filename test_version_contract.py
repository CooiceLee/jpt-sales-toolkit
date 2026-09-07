"""Single-source version contracts for source and frozen installers."""

from pathlib import Path

from backend.config import APP_VERSION
from scripts.stamp_build_version import version_values


ROOT = Path(__file__).parent


def main() -> None:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert APP_VERSION == version
    stamped_version, file_version = version_values(version)
    assert stamped_version == version
    installer = (ROOT / "packaging" / "windows" / "installer.iss").read_text(
        encoding="utf-8"
    )
    assert f'#define VersionInfoVersion "{file_version}"' in installer
    # Every place in the installer that names the version has to name this one.
    # The download's file name is the only version most people ever read, and
    # a package that keeps the previous release's name cannot be told apart
    # from the release it replaces.
    assert f'#define AppVersion "{version}"' in installer, (
        f"installer.iss does not declare AppVersion {version}"
    )
    expected_setup = (
        f'#define OutputBaseFilename "JPT-Sales-Toolkit-{version}'
        '-Windows-x64-UNSIGNED-INTERNAL-Setup"'
    )
    assert expected_setup in installer, (
        f"the Windows Setup would be named after another version, not {version}"
    )
    stale = [
        line for line in installer.splitlines()
        if "#define" in line and "0.1" in line and version not in line
        and file_version not in line
    ]
    assert not stale, f"installer.iss still names another version: {stale}"
    assert version_values("v1.2.3-beta.1") == ("1.2.3-beta.1", "1.2.3.0")
    assert version_values("1.2.3+build.7") == ("1.2.3+build.7", "1.2.3.0")
    assert version_values("1.2.3-rc.1+sha.abc") == (
        "1.2.3-rc.1+sha.abc",
        "1.2.3.0",
    )
    for invalid in (
        "1.2",
        "1/test",
        "1.2.3/asset",
        "1.2.3-alpha..1",
        "1.2.3-01",
        "latest",
    ):
        try:
            version_values(invalid)
        except ValueError:
            continue
        raise AssertionError(f"invalid version accepted: {invalid}")
    print("PASS: application and installer version contracts")


if __name__ == "__main__":
    main()
