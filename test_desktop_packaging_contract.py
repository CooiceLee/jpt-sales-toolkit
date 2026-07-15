"""Static and local runtime contracts for Windows/macOS desktop packaging."""

from __future__ import annotations

import tempfile
import threading
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from desktop_runtime.instance import InstanceLock, find_available_port
from desktop_runtime.paths import user_data_dir
from backend.app_v2 import create_app
from backend.routers.deps import get_current_user
from fastapi.testclient import TestClient


ROOT = Path(__file__).parent


def test_platform_data_paths() -> None:
    with patch("desktop_runtime.paths.platform.system", return_value="Windows"):
        with patch.dict("desktop_runtime.paths.os.environ", {"LOCALAPPDATA": "C:/Users/Test/AppData/Local"}):
            assert str(user_data_dir()).replace("\\", "/").endswith(
                "AppData/Local/JPT Sales Toolkit/data"
            )
    with patch("desktop_runtime.paths.platform.system", return_value="Darwin"):
        assert "Library/Application Support/JPT Sales Toolkit/data" in str(user_data_dir())


def test_single_instance_lock() -> None:
    with tempfile.TemporaryDirectory(prefix="jpt_instance_lock_") as temp_dir:
        path = Path(temp_dir) / "desktop.lock"
        first = InstanceLock(path)
        second = InstanceLock(path)
        assert first.acquire()
        assert not second.acquire()
        first.release()
        assert second.acquire()
        second.release()
        assert find_available_port(28765) >= 28765


def test_packaging_sources() -> None:
    spec = (ROOT / "packaging" / "jpt_sales_toolkit.spec").read_text(encoding="utf-8")
    for resource in ('"index.html"', '"fields.json"', '"schema.sql"'):
        assert resource in spec
    assert '"frontend/templates"' not in spec
    assert 'ROOT / "frontend"),' not in spec
    assert 'ROOT / "config"),' not in spec
    for prohibited in (
        "user.json", "team.json", "regression.html", "smoke-v09.html",
        ".jptauth", ".jptreq", ".xlsx", "database.sqlite",
    ):
        assert prohibited not in spec

    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "*.jptauth" in gitignore
    assert "*.jptreq" in gitignore
    workflow = (ROOT / ".github" / "workflows" / "build-installers.yml").read_text(
        encoding="utf-8"
    )
    for runner in ("windows-2022", "macos-15", "macos-15-intel"):
        assert runner in workflow
    assert "UNSIGNED-INTERNAL" in workflow
    assert '"*.jptauth"' in workflow
    assert "path: '*.jptauth'" not in workflow
    assert 'path: "*.jptauth"' not in workflow
    assert "Get-Content VERSION -Raw" in workflow
    assert 'version="$(< VERSION)"' in workflow
    assert "Start-Process -Wait -PassThru" in workflow
    assert "Installed executable remains after uninstall" in workflow
    assert "lipo -archs" in workflow
    assert "codesign --verify --deep --strict" in workflow
    assert 'hdiutil detach -force "$mount_dir"' in workflow
    for prohibited_pattern in ("*.xlsx", "*.jptauth", "*.jptreq", "database.sqlite"):
        assert prohibited_pattern in workflow

    installer = (ROOT / "packaging" / "windows" / "installer.iss").read_text(
        encoding="utf-8"
    )
    assert "PrivilegesRequired=lowest" in installer
    assert "UninstallDelete" not in installer
    assert "JPT Sales Toolkit.exe" in installer


def test_frontend_is_locally_bootstrapped() -> None:
    index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    assert "fonts.googleapis.com" not in index
    assert "unpkg.com" not in index
    for asset in (
        "frontend/vendor/leaflet/leaflet.js",
        "frontend/vendor/leaflet/leaflet.css",
        "frontend/vendor/leaflet/LICENSE",
    ):
        assert (ROOT / asset).is_file()
    # The source template remains a separately distributed release artifact.
    # It must not be embedded in the frozen application.
    template = ROOT / "frontend" / "templates" / "JPT标准导入模板.xlsx"
    assert template.is_file()
    with ZipFile(template) as workbook:
        assert workbook.testzip() is None
        assert "xl/workbook.xml" in workbook.namelist()
    regression = (ROOT / "frontend" / "regression.html").read_text(encoding="utf-8")
    smoke = (ROOT / "frontend" / "smoke-v09.html").read_text(encoding="utf-8")
    assert "LiJPT2026" not in regression
    assert "LeaderJPT2026" not in smoke


def test_authenticated_desktop_shutdown() -> None:
    stopped = threading.Event()
    app = create_app()
    app.state.desktop_shutdown = stopped.set
    app.dependency_overrides[get_current_user] = lambda: {"id": "local", "role": "sales"}
    with tempfile.TemporaryDirectory(prefix="jpt_shutdown_") as temp_dir:
        with patch.dict("os.environ", {"JPT_DATA_DIR": temp_dir}):
            with TestClient(app) as client:
                response = client.post("/api/desktop/shutdown")
    assert response.status_code == 200
    assert response.json() == {"status": "shutting_down"}
    assert stopped.wait(1)


def main() -> None:
    for test in (
        test_platform_data_paths,
        test_single_instance_lock,
        test_packaging_sources,
        test_frontend_is_locally_bootstrapped,
        test_authenticated_desktop_shutdown,
    ):
        test()
        print(f"PASS: {test.__name__}")
    print("PASS: desktop packaging contracts")


if __name__ == "__main__":
    main()
