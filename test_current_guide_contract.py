"""The current guide has to describe the program that is actually shipping.

The documents a new reader is sent to first drifted two minor versions behind:
they described schema 6, an upgrade path superseded twice, and an interface
where the trip page still had a planning-mode switch. Nothing checked them, so
nobody noticed.

This checks the things a guide can be wrong about in a way that costs somebody
their afternoon: the version and data version, the entry points it names, the
buttons it tells people to press, and whether its own links resolve.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GUIDE = ROOT / "docs" / "current-team-guide.md"
INDEX = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()

# The documents that claim to describe the current candidate.
CURRENT = ("README.md", "docs/current-internal-runbook.md", "docs/current-team-guide.md")


def check_the_guide_exists_and_is_linked() -> None:
    assert GUIDE.is_file(), "there is no current team guide"
    for name in ("README.md", "docs/current-internal-runbook.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "current-team-guide.md" in text, (
            f"{name} does not send the reader to the current guide"
        )


def check_every_local_link_resolves() -> None:
    for name in CURRENT:
        doc = ROOT / name
        text = doc.read_text(encoding="utf-8")
        for label, target in re.findall(r"\[([^\]]+)\]\(([^)#]+)\)", text):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            assert (doc.parent / target).resolve().exists(), (
                f"{name}: the link {label!r} points at {target}, which is not there"
            )


def check_the_eight_scenarios_are_covered() -> None:
    """The roadmap's list, in the guide's own words."""
    text = GUIDE.read_text(encoding="utf-8")
    for topic, marker in (
        ("first record by hand", "+ New Inquiry"),
        ("importing history", "预检"),
        ("leader distribution", ".jpttask"),
        ("sales on their own machine", "待回传"),
        ("what tech cannot do", "不能"),
        ("the trip end to end", "执行与回传"),
        ("what each file is for", "完整备份"),
        ("when it goes wrong", "连接不上 JPT Sales Toolkit"),
    ):
        assert marker in text, f"the guide does not cover {topic} ({marker!r})"


def check_the_buttons_it_names_exist() -> None:
    """A guide that names a button nobody can find is worse than no guide."""
    text = GUIDE.read_text(encoding="utf-8")
    for label in re.findall(r"\*\*(\+ [^*]+|Search existing customers|Save inquiry)\*\*", text):
        assert label in INDEX, (
            f"the guide tells people to press {label!r}, which is not on the page"
        )


def check_every_message_it_quotes_is_one_the_program_says() -> None:
    """A quoted message nobody ever sees sends people looking for the wrong thing.

    The troubleshooting table is read while something has gone wrong, and it is
    matched against what is on screen word for word. Every message it puts in
    quotes has to exist in the interface or in the code that produces it.
    """
    text = GUIDE.read_text(encoding="utf-8")
    i18n = (ROOT / "frontend" / "js" / "i18n.js").read_text(encoding="utf-8")
    device = (ROOT / "backend" / "authorization" / "device.py").read_text(encoding="utf-8")
    quoted = re.findall(r'\*\*"([^"]{6,})"\*\*', text)
    assert len(quoted) >= 8, f"the troubleshooting table lost its quotes: {quoted}"
    missing = [line for line in quoted if line not in i18n and line not in device]
    assert not missing, f"the guide quotes messages the program never says: {missing}"


def check_the_activation_steps_name_real_controls() -> None:
    """The activation walkthrough names buttons; they have to be on the page."""
    text = GUIDE.read_text(encoding="utf-8")
    for label in ("Add member", "Download Device Request",
                  "Issue Device Authorization", "Activate This Device"):
        if label in text:
            assert label in INDEX, f"the guide names {label!r}, which is not on any page"


def check_the_self_check_page_works_without_a_network() -> None:
    """The checklist is read on a laptop that may have no network at all.

    It is also the page that says what not to send back, so it must not promise
    to save or send anything itself: every claim on it has to be true offline.
    """
    page = ROOT / "docs" / "guides" / "05-团队自助验收清单.html"
    assert page.is_file(), "the self-check page is missing"
    text = page.read_text(encoding="utf-8")
    assert "http://" not in text and "https://" not in text, (
        "the self-check page pulls something from the network"
    )
    for src in re.findall(r'<img[^>]*src="([^"]+)"', text):
        assert (page.parent / src).is_file(), f"missing screenshot: {src}"
    assert "不会保存" in text and "不上传" in text, (
        "the page no longer says that it neither saves nor uploads anything"
    )
    # The four roles and the quick route, each as its own checklist.
    for heading in ("快速体验路线", "Leader 验收清单", "Sales 验收清单",
                    "Tech 验收清单", "出差验收清单", "反馈要写什么"):
        assert heading in text, f"the self-check page lost its {heading} section"
    assert text.count('type="checkbox"') >= 20
    assert "docs/guides/05-团队自助验收清单.html" in GUIDE.read_text(encoding="utf-8"), (
        "the guide no longer points at the self-check page"
    )


def check_it_does_not_describe_a_removed_interface() -> None:
    text = GUIDE.read_text(encoding="utf-8")
    for gone, why in (
        ("规划模式", "the planning-mode switch was removed"),
        ("中国出发时间窗", "the separate travel windows were removed"),
        ("返回中国时间窗", "the separate travel windows were removed"),
        ("schema 6", "the data version is 15"),
        ("schema 9", "the data version is 15"),
    ):
        assert gone not in text, f"the guide still describes {gone}: {why}"


def check_the_data_version_is_the_real_one() -> None:
    from backend.repositories import APP_SCHEMA_VERSION

    text = GUIDE.read_text(encoding="utf-8")
    assert f"schema {APP_SCHEMA_VERSION}" in text, (
        f"the guide does not state the current data version (schema {APP_SCHEMA_VERSION})"
    )
    current = tuple(int(part) for part in VERSION.split("-")[0].split("."))
    assert f"v{VERSION.split('-')[0]}-internal" in text, (
        f"the guide never names the candidate this tree builds ({VERSION})"
    )
    # An older version may be named, but only where the sentence is about the
    # package the team is still holding: "on 0.13.2 this button does something
    # else" is what a reader needs while they wait for the new one. An older
    # number anywhere else is drift.
    for number, line in [
        (match, line)
        for line in text.splitlines()
        for match in re.findall(r"v(\d+\.\d+\.\d+)-internal", line)
    ]:
        if tuple(int(part) for part in number.split(".")) >= current:
            continue
        assert any(word in line for word in ("已分发", "旧", "停止分发", "上", "升级")), (
            f"the guide names {number} in a line that does not say it is the "
            f"older, already distributed package: {line[:80]}"
        )


def check_no_document_claims_a_version_nobody_built() -> None:
    """A version number is a promise about a package somebody can install.

    The guide described `v0.13.2-internal` as the candidate it documented while
    the working tree was still `0.13.1-internal` and most of what it described
    existed only in source. A reader with the 0.13.2 package in front of them
    could not tell which half of the document applied to it.
    """
    import subprocess

    tags = subprocess.run(
        ["git", "tag", "--list", "v*-internal"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    # A checkout without tags cannot answer the question this check asks. CI
    # clones shallow by default, and an empty list there meant "nothing was
    # ever built", which failed every document that names the package the team
    # is actually holding. Not knowing is not the same as knowing nothing was
    # built; the workflow fetches tags so the check really runs there.
    if tags.returncode != 0 or not tags.stdout.strip():
        return  # Not a checkout; there is nothing to compare against.
    built = {line.strip().lstrip("v") for line in tags.stdout.splitlines() if line.strip()}
    built.add(VERSION)
    for name in CURRENT:
        text = (ROOT / name).read_text(encoding="utf-8")
        for stated in set(re.findall(r"v(\d+\.\d+\.\d+-internal)", text)):
            assert stated in built, (
                f"{name} names v{stated}, which has never been built: a reader "
                "cannot install it, so nothing can be said to be in it"
            )


def check_the_guide_separates_what_shipped_from_what_did_not() -> None:
    """Half the guide describes work that is still only in the source tree."""
    text = GUIDE.read_text(encoding="utf-8")
    assert "〔候选〕" in text, (
        "the guide does not mark which parts need a version nobody has yet"
    )
    boundary = text[:text.index("## 1.")]
    # A candidate can now be built and still not be in anybody's hands, so
    # either wording counts - what must be said is that the reader does not
    # have it yet.
    assert "已分发" in boundary and ("未打包" in boundary or "尚未分发" in boundary), (
        "the guide does not say, before the first instruction, which of it "
        "applies to the package the reader has"
    )
    # The sections whose entry points do not exist in the shipped package.
    for section in ("## 1. 〔候选〕", "## 6. 〔候选〕"):
        assert section in text, f"{section} is not marked as unreleased"
    for name in ("README.md", "docs/current-internal-runbook.md"):
        declaration = (ROOT / name).read_text(encoding="utf-8")
        assert "尚未打包" in declaration or "尚未分发" in declaration, (
            f"{name} presents unreleased work as part of a released package"
        )


def check_it_is_honest_about_what_is_unfinished() -> None:
    text = GUIDE.read_text(encoding="utf-8")
    assert "Pending" in text, (
        "the guide does not say which gates are still outstanding"
    )
    # Either the pictures are there, or the guide says they are not. What it
    # may not do is describe a screen it never shows and leave the reader to
    # guess. Now that they are there, the files have to be too.
    images = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)
    if "截图待补" in text:
        assert not images, "the guide says pictures are coming and also has them"
    else:
        assert images, (
            "the guide neither carries screenshots nor says they are still to come"
        )
        for target in images:
            assert (GUIDE.parent / target).is_file(), (
                f"the guide shows a picture that is not in the repository: {target}"
            )


def main() -> None:
    check_the_guide_exists_and_is_linked()
    check_every_local_link_resolves()
    check_the_eight_scenarios_are_covered()
    check_the_buttons_it_names_exist()
    check_it_does_not_describe_a_removed_interface()
    check_every_message_it_quotes_is_one_the_program_says()
    check_the_activation_steps_name_real_controls()
    check_the_self_check_page_works_without_a_network()
    check_the_data_version_is_the_real_one()
    check_no_document_claims_a_version_nobody_built()
    check_the_guide_separates_what_shipped_from_what_did_not()
    check_it_is_honest_about_what_is_unfinished()
    print("PASS: the current guide describes the program that is shipping")


if __name__ == "__main__":
    main()
