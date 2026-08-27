#!/usr/bin/env python3
"""Public-source release hygiene gates."""

from __future__ import annotations

import re
import subprocess
import zipfile
from pathlib import Path


ROOT = Path(__file__).parent
BANNED_SUFFIXES = {
    ".csv",
    ".db",
    ".jptauth",
    ".jptreq",
    ".key",
    ".pem",
    ".sqlite",
    ".sqlite3",
    ".xls",
    ".xlsx",
}
BANNED_TEXT = (
    "/Users/liliang",
    "欧洲小分队进度记录",
)
PUBLIC_TEMPLATE = "frontend/templates/JPT标准导入模板.xlsx"


# These files predate the repo's LF default and still hold CRLF. Writing one of
# them with a text-mode tool silently rewrites every ending, which turns a small
# edit into a whole-file diff. That has happened twice, so it is checked here
# rather than left to whoever is editing.
CRLF_FILES = (
    "README.md",
    "backend/__init__.py",
    "backend/services/__init__.py",
    "backend/services/email_parser.py",
    "config/fields.json",
    "config/products.json",
    "config/regions.json",
    "config/team.json",
    "frontend/css/style.css",
    "frontend/index.html",
    "frontend/js/app.js",
    "run.py",
)


def check_line_endings_were_not_flattened() -> None:
    root = Path(__file__).parent
    flattened = []
    for name in CRLF_FILES:
        path = root / name
        if not path.is_file():
            continue
        if b"\r\n" not in path.read_bytes():
            flattened.append(name)
    assert not flattened, (
        "these files hold CRLF and something rewrote them as LF; write them in "
        f"binary mode instead: {flattened}"
    )


def check_served_pages_are_packaged() -> None:
    """Every page a route reads from disk has to be in the build.

    The packaging spec lists frontend pages one by one, so a new page is served
    fine from source and returns 500 in the frozen app - which only shows up
    when somebody opens it.
    """
    root = Path(__file__).parent
    router = (root / "backend" / "app_v2.py").read_text(encoding="utf-8")
    spec = (root / "packaging" / "jpt_sales_toolkit.spec").read_text(encoding="utf-8")
    pages = set(re.findall(r'frontend_dir / "([\w.-]+\.html)"', router))
    assert pages, "expected the router to read at least one page from disk"
    missing = [
        page for page in sorted(pages)
        if f'"{page}"' not in spec and f"'{page}'" not in spec
    ]
    assert not missing, (
        f"these pages are served but not packaged, so the frozen app 500s: {missing}"
    )


def main() -> None:
    check_served_pages_are_packaged()
    tracked = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
    ).decode("utf-8").split("\0")
    tracked = [item for item in tracked if item]

    forbidden_files = [
        item
        for item in tracked
        if (
            Path(item).suffix.lower() in BANNED_SUFFIXES
            and item != PUBLIC_TEMPLATE
        )
        or item.startswith(("data/", "dist/", "build/", "release/"))
    ]
    assert not forbidden_files, f"private/generated files are tracked: {forbidden_files}"

    leaked_text: list[str] = []
    for relative in tracked:
        if relative == "test_release_hygiene.py":
            continue
        path = ROOT / relative
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if any(marker in text for marker in BANNED_TEXT):
            leaked_text.append(relative)
    assert not leaked_text, f"local or business source identifiers are tracked: {leaked_text}"

    template = ROOT / PUBLIC_TEMPLATE
    assert template.is_file(), "standard public workbook template is missing"
    with zipfile.ZipFile(template) as workbook:
        assert workbook.testzip() is None
        xml_text = "\n".join(
            workbook.read(name).decode("utf-8", errors="ignore")
            for name in workbook.namelist()
            if name.endswith(".xml")
        )
    assert not any(marker in xml_text for marker in BANNED_TEXT)

    check_line_endings_were_not_flattened()

    print("PASS: public-source tree excludes local paths, business workbooks and private artifacts")


if __name__ == "__main__":
    main()
