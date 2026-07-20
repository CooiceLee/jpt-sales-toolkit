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
