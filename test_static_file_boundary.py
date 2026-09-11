"""The page route serves the page, and nothing outside its own directory.

A URL is text. `%2e%2e/VERSION` is text that names a file one level above the
page directory, and the route used to join it on and send whatever it found:
the version file, the backend source, anything the process could read, to
anybody who could reach the port. Filtering the characters `../` does not help,
because every other spelling of the same escape still arrives decoded.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent
TEST_DIR = Path(tempfile.mkdtemp(prefix="jpt_static_boundary_"))
os.environ["JPT_DATA_DIR"] = str(TEST_DIR)

from fastapi.testclient import TestClient  # noqa: E402

from backend.app_v2 import create_app  # noqa: E402

# Files that exist outside the page directory and have no business being
# downloadable from it. Their real content is read from disk, so the assertion
# cannot pass by matching a string this test made up.
OUTSIDE_FILES = ("VERSION", "backend/app_v2.py", "backend/schema.sql")

ESCAPES = (
    "/%2e%2e/{name}",
    "/..%2f{name}",
    "/../{name}",
    "/%2e%2e%2f{name}",
    "/js/%2e%2e/%2e%2e/{name}",
    "/js/../../{name}",
    "/static/..%2f{name}",
    "/%2e%2e/./{name}",
    "/.%2e/{name}",
)

PAGE_ASSETS = ("/js/i18n.js", "/css/style.css", "/static/js/i18n.js")


def check_nothing_outside_the_page_directory_is_served(client: TestClient) -> None:
    """Every spelling of the escape returns the page, never the file.

    There are only two honest answers to a request for something the page
    directory does not contain: the page, because the address might be one of
    its routes, or not found. Anything else is a file being handed out.
    """
    for name in OUTSIDE_FILES:
        secret = (ROOT / name).read_text(encoding="utf-8")
        assert secret.strip(), f"the probe file is empty: {name}"
        for template in ESCAPES:
            url = template.format(name=name)
            response = client.get(url)
            assert response.status_code in (200, 404), (
                f"{url} answered {response.status_code}"
            )
            body = response.text
            assert secret.strip() != body.strip(), (
                f"{url} handed back the whole of {name}"
            )
            if response.status_code == 404:
                continue
            assert "<!DOCTYPE html>" in body[:80], (
                f"{url} answered with something that is not the page: {body[:120]!r}"
            )


def check_the_page_and_its_assets_still_load(client: TestClient) -> None:
    """The fix must not cost the application its own files."""
    page = client.get("/")
    assert page.status_code == 200 and "<!DOCTYPE html>" in page.text[:80], (
        f"the page itself stopped loading: {page.status_code}"
    )
    for path in PAGE_ASSETS:
        response = client.get(path)
        assert response.status_code == 200, f"{path} answered {response.status_code}"
        assert len(response.text) > 200, f"{path} came back nearly empty"
    for route in ("/dashboard", "/trip-planner", "/anything/at/all"):
        response = client.get(route)
        assert response.status_code == 200, f"{route} answered {response.status_code}"
        assert "<!DOCTYPE html>" in response.text[:80], (
            f"{route} is a page route and must render the page"
        )


def check_the_api_prefix_is_still_the_api(client: TestClient) -> None:
    """An unknown API path is an error, not the page."""
    response = client.get("/api/nothing-here")
    assert response.status_code == 404, response.status_code
    assert "<!DOCTYPE html>" not in response.text, (
        "an unknown API path answered with the page, which reads as success"
    )


def check_a_signed_in_caller_has_no_more_reach(client: TestClient) -> None:
    """The boundary is the directory, not who is asking.

    Signing in is what the page is for; it must not become a way to read files
    the page never contained.
    """
    version = (ROOT / "VERSION").read_text(encoding="utf-8")
    signed_in = client.get(
        "/%2e%2e/VERSION", headers={"Authorization": "Bearer whatever"}
    )
    assert version.strip() != signed_in.text.strip(), (
        "an Authorization header turned the escape back on"
    )


def check_the_rule_is_where_the_path_lands(tmp_root: Path) -> None:
    """What decides is the resolved path, not the spelling of the request.

    A link inside the directory can point anywhere, and a request for it
    carries no `..` at all. Only resolving the path and asking where it landed
    answers this; a filter on the characters `../` says the link is fine.
    """
    from backend.app_v2 import _page_file

    pages = tmp_root / "frontend"
    (pages / "js").mkdir(parents=True)
    (pages / "js" / "app.js").write_text("inside", encoding="utf-8")
    outside = tmp_root / "secret.txt"
    outside.write_text("outside", encoding="utf-8")
    (pages / "escape.txt").symlink_to(outside)

    served = _page_file(pages, "js/app.js")
    assert served is not None and served.read_text(encoding="utf-8") == "inside", (
        f"a file inside the page directory must be served, got {served}"
    )
    assert _page_file(pages, "escape.txt") is None, (
        "a link out of the page directory was served; the check is on the "
        "spelling of the request rather than on where it lands"
    )
    assert _page_file(pages, "../secret.txt") is None
    assert _page_file(pages, "js/../../secret.txt") is None
    assert _page_file(pages, "") is None, "the directory itself is not a file"
    assert _page_file(pages, "js") is None, "a directory is not a download"
    assert _page_file(pages, "js/missing.js") is None


def main() -> None:
    check_the_rule_is_where_the_path_lands(
        Path(tempfile.mkdtemp(prefix="jpt_page_rule_"))
    )
    client = TestClient(create_app())
    check_nothing_outside_the_page_directory_is_served(client)
    check_the_page_and_its_assets_still_load(client)
    check_the_api_prefix_is_still_the_api(client)
    check_a_signed_in_caller_has_no_more_reach(client)
    print("PASS: the page route stays inside the page directory")


if __name__ == "__main__":
    main()
