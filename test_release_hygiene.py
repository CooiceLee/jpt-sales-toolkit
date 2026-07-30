#!/usr/bin/env python3
"""Public-source release hygiene gates."""

from __future__ import annotations

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


def main() -> None:
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

    print("PASS: public-source tree excludes local paths, business workbooks and private artifacts")


if __name__ == "__main__":
    main()
