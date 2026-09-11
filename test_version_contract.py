"""Single-source version contracts for source and frozen installers."""

from pathlib import Path

from backend.config import APP_VERSION
from scripts.stamp_build_version import version_values


ROOT = Path(__file__).parent


# The documents a reader is sent to first, and the phrase each uses to declare
# which candidate it describes.
# "待测" was true when the working tree and the released package were the same
# thing. A hotfix released from its own branch made them different: the package
# the team holds is 0.13.2, and this tree is the candidate after it. The word
# says which of the two the sentence is about.
# Two candidates now, and a reader has to be able to tell them apart: the one
# the team is holding, and the one this tree builds. A build that is not
# distributed yet cannot be called "已分发", and the install guide ships inside
# the new package, so it names the new one.
BUILT_DOCS = (
    ("README.md", "本次内测候选：`v"),
    ("docs/current-internal-runbook.md", "本次内测候选：`v"),
    ("docs/deployment/member-install-guide.md", "适用版本：`v"),
)
DISTRIBUTED_DOCS = (
    ("README.md", "当前已分发候选：`v"),
    ("docs/current-internal-runbook.md", "当前已分发候选：`v"),
)


def _release(value: str) -> tuple:
    """(0, 13, 2) from "0.13.2-internal", for comparing two candidates."""
    core = value.split("-", 1)[0].split("+", 1)[0]
    return tuple(int(part) for part in core.split("."))


def _stated(relative: str, phrase: str) -> str:
    path = ROOT / relative
    assert path.is_file(), f"missing current document: {relative}"
    text = path.read_text(encoding="utf-8")
    assert phrase in text, (
        f"{relative} does not declare which candidate it describes "
        f"(expected a line containing {phrase!r})"
    )
    return text.split(phrase, 1)[1].split("`", 1)[0]


def check_current_docs_name_a_current_version(version: str) -> None:
    """A guide that names the wrong package sends people to the wrong package.

    These drifted two minor versions behind while the application moved on -
    still describing schema 6 and an upgrade path that had already been
    superseded twice - because nothing checked them. The candidate this tree
    builds has to be named exactly, and the one the team is still holding can
    never be newer than it: saying a build is already distributed, before
    anybody has distributed it, is the same kind of mistake pointing the other
    way.
    """
    current = _release(version)
    for relative, phrase in BUILT_DOCS:
        stated = _stated(relative, phrase)
        assert _release(stated) == current, (
            f"{relative} describes {stated}, but this tree builds {version}"
        )
    for relative, phrase in DISTRIBUTED_DOCS:
        stated = _stated(relative, phrase)
        assert _release(stated) <= current, (
            f"{relative} says {stated} is already distributed, which is newer "
            f"than the candidate this tree builds ({version})"
        )


def main() -> None:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert APP_VERSION == version
    stamped_version, file_version = version_values(version)
    assert stamped_version == version
    installer = (ROOT / "packaging" / "windows" / "installer.iss").read_text(
        encoding="utf-8"
    )
    assert f'#define VersionInfoVersion "{file_version}"' in installer
    check_current_docs_name_a_current_version(version)
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
