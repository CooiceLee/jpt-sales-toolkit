"""Static and local runtime contracts for Windows/macOS desktop packaging."""

from __future__ import annotations

import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from zipfile import ZipFile

from desktop_runtime.instance import InstanceLock, find_available_port
from desktop_runtime.paths import user_data_dir
from desktop_launcher import instance_version_mismatch, main as desktop_main, running_from_disk_image
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


def test_disk_image_detection() -> None:
    with patch("desktop_launcher.sys.platform", "darwin"):
        with patch("desktop_launcher.sys.executable", "/Volumes/JPT/JPT Sales Toolkit"):
            assert running_from_disk_image()
        with patch("desktop_launcher.sys.executable", "/private/tmp/mount/JPT Sales Toolkit"):
            with patch("desktop_launcher.os.statvfs", return_value=SimpleNamespace(f_flag=1)):
                assert running_from_disk_image()
        with patch("desktop_launcher.sys.executable", "/Applications/JPT Sales Toolkit"):
            with patch("desktop_launcher.os.statvfs", return_value=SimpleNamespace(f_flag=0)):
                assert not running_from_disk_image()
    with patch("desktop_launcher.APP_VERSION", "0.11.3-internal"):
        assert instance_version_mismatch({"version": "0.11.0-internal"})
        assert not instance_version_mismatch({"version": "0.11.3-internal"})
        assert instance_version_mismatch({})


def test_old_instance_guard() -> None:
    args = SimpleNamespace(data_dir=None, port=8765, no_browser=False)
    logger = SimpleNamespace(error=lambda *_args: None)
    lock = SimpleNamespace(acquire=lambda: False)
    with tempfile.TemporaryDirectory(prefix="jpt_old_instance_") as temp_dir:
        with patch.dict("desktop_launcher.os.environ", {}, clear=False):
            with patch("desktop_launcher.arguments", return_value=args), \
                 patch("desktop_launcher.user_data_dir", return_value=Path(temp_dir)), \
                 patch("desktop_launcher.prepare_data_dir"), \
                 patch("desktop_launcher.configure_logging", return_value=logger), \
                 patch("desktop_launcher.InstanceLock", return_value=lock), \
                 patch("desktop_launcher.read_instance_port", return_value=8765), \
                 patch("desktop_launcher.wait_until_healthy", return_value=True), \
                 patch("desktop_launcher.read_instance_health", return_value={"status": "ok"}), \
                 patch("desktop_launcher.show_instance_version_warning") as warning, \
                 patch("desktop_launcher.webbrowser.open") as open_browser:
                assert desktop_main() == 2
    warning.assert_called_once()
    open_browser.assert_not_called()


def test_packaging_sources() -> None:
    spec = (ROOT / "packaging" / "jpt_sales_toolkit.spec").read_text(encoding="utf-8")
    frozen_smoke = (ROOT / "scripts" / "smoke_frozen.py").read_text(encoding="utf-8")
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
    assert '"region": "GLOBAL"' in frozen_smoke

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
    assert "--expect-disk-image" in workflow
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


def test_frontend_language_and_backup_controls() -> None:
    index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    styles = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
    i18n = (ROOT / "frontend" / "js" / "i18n.js").read_text(encoding="utf-8")
    api = (ROOT / "frontend" / "js" / "api-client.js").read_text(encoding="utf-8")
    transfer = (ROOT / "frontend" / "js" / "modules" / "data-transfer.js").read_text(
        encoding="utf-8"
    )
    actions = (ROOT / "frontend" / "js" / "modules" / "spreadsheet-import-actions.js").read_text(
        encoding="utf-8"
    )
    app = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
    assert 'id="language-toggle"' in index
    assert index.index('id="header-actions"') < index.index('id="language-toggle"')
    assert "position: static" in styles
    assert 'id="runtime-version"' in index
    assert index.index("/static/js/i18n.js") < index.index("/static/js/app.js")
    assert "jpt_ui_language" in i18n
    assert "MutationObserver" in i18n
    assert "Spreadsheet Preflight" in i18n and "Excel 预检" in i18n
    assert 'id="create-backup-btn"' in index
    assert "createFullBackup" in api
    assert "ApiClient.createFullBackup()" in transfer
    assert 'data-transfer-target="spreadsheet"' in index
    assert 'data-transfer-target="json"' in index
    assert 'id="json-import-file"' in index
    assert 'id="import-preflight-result" class="import-preflight-scroll"' in index
    assert "height:clamp(200px,28vh,360px)" in styles
    assert ".import-resolution-group" in styles and "overflow-y:auto" in styles
    assert "await refreshAllCounts()" in transfer
    assert "await refreshAllCounts()" in actions
    assert "setText('nav-parser-total', counts.total)" in app
    assert index.index("spreadsheet-import-state.js") < index.index(
        "spreadsheet-import-progress.js"
    ) < index.index("spreadsheet-import-view.js")


def test_desktop_cache_and_install_location_contract() -> None:
    with tempfile.TemporaryDirectory(prefix="jpt_cache_policy_") as temp_dir:
        with patch.dict("os.environ", {
            "JPT_DATA_DIR": temp_dir,
            "JPT_RUNNING_FROM_DISK_IMAGE": "1",
        }):
            with TestClient(create_app()) as client:
                index = client.get("/")
                static = client.get("/static/js/i18n.js")
                health = client.get("/api/health")
    assert index.status_code == 200
    assert index.headers["cache-control"] == "no-store, max-age=0"
    assert static.status_code == 200
    assert static.headers["cache-control"] == "no-store, max-age=0"
    assert health.json()["running_from_disk_image"] is True


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
        test_disk_image_detection,
        test_old_instance_guard,
        test_packaging_sources,
        test_frontend_is_locally_bootstrapped,
        test_frontend_language_and_backup_controls,
        test_desktop_cache_and_install_location_contract,
        test_authenticated_desktop_shutdown,
    ):
        test()
        print(f"PASS: {test.__name__}")
    print("PASS: desktop packaging contracts")


if __name__ == "__main__":
    main()
