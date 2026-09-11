"""This machine has to be the same machine every time it starts.

The fingerprint is read from the hardware id and hashed; that part is
unchanged, so a computer that was authorized before keeps the identity it had.
What changed is the failure path. It used to fall back to
`platform.node():uuid.getnode():platform.machine()`, and uuid.getnode() returns
a *random* number whenever the hardware address cannot be read - so a program
started with a PATH that did not contain ioreg looked like a brand-new device
on every launch, and the authorization installed on this one silently stopped
matching. Measured: two consecutive starts, two different fingerprints, and a
Leader who could no longer log in.

Now the reader is told the machine could not be identified, and nothing is
invented: no request is written, no authorization is touched, and the failure
reaches the status, the login and the device request as the same answer.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEST_DIR = Path(tempfile.mkdtemp(prefix="jpt_device_identity_"))
os.environ["JPT_DATA_DIR"] = str(TEST_DIR)

sys.path.insert(0, str(ROOT))

from backend.authorization import device as device_module  # noqa: E402
from backend.authorization.device import (  # noqa: E402
    DeviceIdentityError,
    build_device_request,
    device_fingerprint,
)


def fresh_fingerprint(path_value: str) -> str:
    """One fingerprint from a brand-new process, with that PATH."""
    environment = dict(os.environ, PATH=path_value)
    result = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, '.');"
         "from backend.authorization.device import device_fingerprint;"
         "print(device_fingerprint())"],
        capture_output=True, text=True, cwd=ROOT, env=environment, timeout=60,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    return result.stdout.strip()


def check_the_fingerprint_does_not_depend_on_who_started_the_program() -> None:
    """Finder, a launcher and a service manager each hand over a different PATH."""
    if sys.platform != "darwin":                      # pragma: no cover - platform
        return
    full = fresh_fingerprint("/usr/sbin:/usr/bin:/bin")
    stripped = fresh_fingerprint("/usr/bin:/bin")     # no ioreg on this PATH
    second = fresh_fingerprint("/usr/bin:/bin")
    assert len(full) == 64 and full == stripped == second, (
        "the machine identifies itself differently depending on the PATH it "
        f"was started with: {full[:12]} / {stripped[:12]} / {second[:12]}"
    )


def check_a_known_hardware_id_still_hashes_to_the_same_fingerprint() -> None:
    """The identity of machines that are already authorized may not move."""
    sample = "B062D1A0-1E16-5D91-820C-9111FE0C0615"
    expected = hashlib.sha256(f"jpt-device-v1:{sample}".encode("utf-8")).hexdigest()
    original = device_module._platform_identifier
    device_fingerprint.cache_clear()
    device_module._platform_identifier = lambda: sample
    try:
        assert device_fingerprint() == expected, (
            "the hash of a known hardware id changed, so every authorized "
            "machine would have to be authorized again"
        )
    finally:
        device_module._platform_identifier = original
        device_fingerprint.cache_clear()


def check_an_unreadable_machine_stops_instead_of_inventing_one() -> None:
    failures = {
        "timed out": subprocess.TimeoutExpired(cmd="ioreg", timeout=5),
        "not there": FileNotFoundError("/usr/sbin/ioreg"),
        "refused": subprocess.CalledProcessError(1, "ioreg"),
    }
    original = subprocess.check_output
    for name, error in failures.items():
        def failing(*args, _error=error, **kwargs):
            raise _error
        subprocess.check_output = failing
        device_fingerprint.cache_clear()
        try:
            device_module._darwin_identifier()
        except DeviceIdentityError as raised:
            assert "could not be identified" in str(raised), (name, str(raised))
        else:
            raise AssertionError(f"{name}: an unreadable machine still produced an identity")
        finally:
            subprocess.check_output = original
            device_fingerprint.cache_clear()

    # An answer that has no identity in it is the same kind of failure.
    subprocess.check_output = lambda *args, **kwargs: "nothing useful here\n"
    device_fingerprint.cache_clear()
    try:
        device_module._darwin_identifier()
    except DeviceIdentityError as raised:
        assert "could not be identified" in str(raised)
    else:
        raise AssertionError("an answer without a hardware id still produced one")
    finally:
        subprocess.check_output = original
        device_fingerprint.cache_clear()


def check_nothing_random_is_left_in_the_identity() -> None:
    source = (ROOT / "backend" / "authorization" / "device.py").read_text(encoding="utf-8")
    identifier = source[source.index("def _platform_identifier"):]
    assert "uuid.getnode" not in identifier, (
        "uuid.getnode() is random when the hardware address cannot be read, so "
        "the machine would change identity between starts"
    )
    assert "/usr/sbin/ioreg" in source, (
        "the hardware id is read through the caller's PATH again"
    )


def check_a_machine_without_an_identity_writes_no_request() -> None:
    original = device_module._platform_identifier
    device_fingerprint.cache_clear()
    def refuse():
        raise DeviceIdentityError("This machine could not be identified: test")
    device_module._platform_identifier = refuse
    try:
        try:
            build_device_request()
        except DeviceIdentityError:
            pass
        else:
            raise AssertionError("a device request was written for a machine with no identity")
    finally:
        device_module._platform_identifier = original
        device_fingerprint.cache_clear()


def check_windows_reads_the_same_key_and_does_not_fall_back() -> None:
    """No Windows here, so the registry is a double - and said so in the report."""
    source = (ROOT / "backend" / "authorization" / "device.py").read_text(encoding="utf-8")
    assert r"SOFTWARE\Microsoft\Cryptography" in source and "MachineGuid" in source, (
        "the Windows machine id no longer comes from the key it always came from"
    )
    class Key:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False

    class Registry:
        HKEY_LOCAL_MACHINE = object()
        def __init__(self, value):
            self.value = value
        def OpenKey(self, root, path):
            assert path == r"SOFTWARE\Microsoft\Cryptography", path
            return Key()
        def QueryValueEx(self, key, name):
            assert name == "MachineGuid", name
            if isinstance(self.value, Exception):
                raise self.value
            return (self.value, 1)

    saved = sys.modules.get("winreg")
    try:
        sys.modules["winreg"] = Registry("8f0e7a3c-1111-2222-3333-444455556666")
        assert device_module._windows_identifier() == "8f0e7a3c-1111-2222-3333-444455556666"
        for broken in (OSError("no access"), ):
            sys.modules["winreg"] = Registry(broken)
            try:
                device_module._windows_identifier()
            except DeviceIdentityError as raised:
                assert "could not be identified" in str(raised)
            else:
                raise AssertionError("an unreadable registry still produced an identity")
        sys.modules["winreg"] = Registry("")
        try:
            device_module._windows_identifier()
        except DeviceIdentityError:
            pass
        else:
            raise AssertionError("an empty MachineGuid still produced an identity")
    finally:
        if saved is None:
            sys.modules.pop("winreg", None)
        else:
            sys.modules["winreg"] = saved


def check_the_page_and_the_request_answer_instead_of_failing() -> None:
    """Run it: an unidentifiable machine must not end in a 500 anywhere.

    The status page, the login and the device request are three different ways
    into the same fact, and each of them used to be a different kind of wrong:
    a crash, "wrong password", and a signed request for a device that does not
    exist.
    """
    from fastapi.testclient import TestClient

    from backend.app_v2 import create_app
    from backend.repositories import close_db

    original = device_module._platform_identifier
    device_fingerprint.cache_clear()

    def refuse():
        raise DeviceIdentityError(
            "This machine could not be identified: the hardware id could not "
            "be read (/usr/sbin/ioreg)."
        )

    device_module._platform_identifier = refuse
    try:
        with TestClient(create_app()) as client:
            status_response = client.get("/api/authorization/status")
            assert status_response.status_code == 200, status_response.text
            body = status_response.json()
            assert body["mode"] == "unidentified", body
            assert "could not be identified" in (body.get("device_error") or ""), body
            assert body["activated"] is False and body["device_id"] is None, body

            request_response = client.post("/api/authorization/device-request")
            assert request_response.status_code == 400, (
                f"asking for a device request ended in {request_response.status_code}, "
                "not a refusal with a reason"
            )
            assert "could not be identified" in request_response.text, request_response.text

            login_response = client.post("/api/auth/login", json={
                "username": "nobody", "password": "NotThePoint2026"})
            assert login_response.status_code in (401, 403), login_response.text
    finally:
        device_module._platform_identifier = original
        device_fingerprint.cache_clear()
        close_db()


def check_the_same_answer_reaches_status_login_and_the_request() -> None:
    """One reason, said the same way wherever the reader meets it."""
    service = (ROOT / "backend" / "services"
               / "offline_authorization_service.py").read_text(encoding="utf-8")
    assert "DeviceIdentityError" in service and "unidentified_device_status" in service, (
        "the status page turns an unidentifiable machine into a 500"
    )
    assert 'status.get("device_error")' in service, (
        "login does not refuse a machine that cannot be identified"
    )
    router = (ROOT / "backend" / "routers" / "auth.py").read_text(encoding="utf-8")
    assert 'device_error' in router, (
        "login still answers 'wrong password' when the machine is the problem"
    )
    public = (ROOT / "backend" / "routers"
              / "authorization_public.py").read_text(encoding="utf-8")
    block = public[public.index("/device-request"):public.index("/activate")]
    assert "raise_service_error" in block, (
        "asking for a device request on an unidentifiable machine ends in a 500"
    )


STARTUP_HARNESS = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

// The status the server sends when it cannot identify the machine.
const UNIDENTIFIED = {
    mode: 'unidentified', activated: false, device_id: null,
    device_error: 'This machine could not be identified: the hardware id could '
        + 'not be read (/usr/sbin/ioreg).',
    trust_required: true, member: null, authorization: null,
    issuer: { initialized: false, trusted: false, can_initialize: false, fingerprint: null },
};
const NORMAL = {
    mode: 'legacy', activated: false, device_id: 'a'.repeat(64), trust_required: true,
    member: null, authorization: null,
    issuer: { initialized: false, trusted: false, can_initialize: true, fingerprint: null },
};

function run(status) {
    const shown = [];
    const hidden = [];
    const text = {};
    const element = id => ({
        id,
        style: {},
        classList: {
            _on: new Set(),
            add(name) { this._on.add(name); if (name === 'hidden') hidden.push(id); },
            remove(name) { this._on.delete(name); },
            contains(name) { return this._on.has(name); },
            toggle(name, on) { on ? this.add(name) : this.remove(name); },
        },
        set textContent(value) { text[id] = value; },
        get textContent() { return text[id] || ''; },
        value: '',
        focus() {},
    });
    const elements = {};
    const context = {
        console: { error() {}, log() {} },
        document: {
            getElementById: id => (elements[id] ||= element(id)),
            querySelector: () => null,
            querySelectorAll: () => [],
            addEventListener() {},
        },
        I18n: { t: (value, params = {}) => Object.entries(params)
            .reduce((out, [key, param]) => out.split('{' + key + '}').join(param), value) },
        ApiClient: {
            getAuthorizationStatus: async () => status,
            clearAuth() {},
        },
        setText: (id, value) => { (elements[id] ||= element(id)).textContent = value; },
        showModal: id => shown.push(id),
        hideModal: id => hidden.push(id),
        hideModal_: null,
    };
    context.window = context;
    vm.createContext(context);
    for (const file of ['modules/authorization-model.js', 'modules/authorization-activation.js']) {
        vm.runInContext(fs.readFileSync('frontend/js/' + file, 'utf8'), context, { filename: file });
    }
    return context.initAuthorizationActivation().then(allowed => ({
        allowed, shown, hidden, text,
    }));
}

run(UNIDENTIFIED).then(result => {
    assert.strictEqual(result.allowed, false,
      'login was allowed on a machine the program cannot identify');
    assert.ok(result.shown.includes('activation-modal'),
      'nothing was shown to explain why login is impossible');
    assert.ok(result.hidden.includes('login-modal'),
      'the password box stayed up, so the reader types a password that cannot work');
    assert.match(result.text['activation-modal-title'], /could not be identified/);
    assert.match(result.text['activation-message'], /hardware id could not be read/,
      'the reason the program was given never reached the screen');
    assert.match(result.text['activation-message'], /will not help/,
      'the screen does not say that a new authorization file changes nothing');
    assert.match(result.text['activation-device-id'], /Could not be read/);
    for (const section of ['activation-bootstrap-section', 'activation-member-section',
                           'activation-leader-recovery', 'activation-back-to-setup']) {
        assert.ok(result.hidden.includes(section), `${section} was left on a screen that cannot use it`);
    }
    return run(NORMAL);
}).then(result => {
    assert.strictEqual(result.allowed, true,
      'a normal installation was blocked from logging in');
    assert.ok(!result.shown.includes('activation-modal'));
}).catch(error => { console.error(error); process.exit(1); });
"""


def check_the_startup_screen_says_it_instead_of_asking_for_a_password() -> None:
    """The reason reaches the screen the reader is actually looking at.

    The server already answers `device_error` and refuses the login with it.
    The page dropped that field and fell through to the password box, so the
    first thing a reader saw was a login that refuses every password without
    ever saying that the machine, not the password, is the problem.
    """
    result = subprocess.run(
        ["node", "-e", STARTUP_HARNESS], cwd=ROOT, text=True, capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def main() -> None:
    check_the_fingerprint_does_not_depend_on_who_started_the_program()
    check_a_known_hardware_id_still_hashes_to_the_same_fingerprint()
    check_an_unreadable_machine_stops_instead_of_inventing_one()
    check_nothing_random_is_left_in_the_identity()
    check_a_machine_without_an_identity_writes_no_request()
    check_windows_reads_the_same_key_and_does_not_fall_back()
    check_the_same_answer_reaches_status_login_and_the_request()
    check_the_page_and_the_request_answer_instead_of_failing()
    check_the_startup_screen_says_it_instead_of_asking_for_a_password()
    print("PASS: this machine identifies itself the same way every start, and "
          "says so when it cannot")


if __name__ == "__main__":
    main()
