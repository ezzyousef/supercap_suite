"""Licensing integration: enforcement off, test-key licences only (never the real key)."""
import os
import sys
import uuid
from datetime import date
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core import licensing  # noqa: E402
from labkit.licence import DEVICE_RE, LicenceError, LicenceStore  # noqa: E402

LABKIT_SRC = Path(r"E:\Lab Apps\labkit")


@pytest.fixture
def store(tmp_path):
    return LicenceStore(licensing.PRODUCT, folder=tmp_path / "lic")


@pytest.fixture
def test_key(monkeypatch):
    pytest.importorskip("cryptography")
    if not (LABKIT_SRC / "labkit_issuer" / "issuer.py").is_file():
        pytest.skip("labkit issuer source not available")
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    import base64
    key = Ed25519PrivateKey.generate()
    pub = base64.b64encode(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()
    monkeypatch.setattr(licensing, "PUBLIC_KEYS", {"test-key": pub})
    return key


def _issue(key, product):
    sys.path.insert(0, str(LABKIT_SRC))
    try:
        from labkit_issuer.issuer import make_licence
    finally:
        sys.path.remove(str(LABKIT_SRC))
    claims = {"product": product, "edition": "pro", "kind": "commercial", "serial": "SS-00001",
              "lid": uuid.uuid4().hex, "issued": date.today().isoformat(), "name": "Test Lab",
              "device": licensing.device_id(), "features": ["*"]}
    return make_licence(key, "test-key", claims)


def test_settings():
    assert licensing.PRODUCT == "supercap-suite"
    assert licensing.ENFORCE is False
    assert "*" in licensing.FREE_FEATURES
    assert licensing.RELEASE_DATE == date(2026, 11, 14)


def test_no_licence_everything_allowed(store):
    st = licensing.status(store)
    assert not st.ok
    assert st.reason
    assert st.can_save
    for feature in ("origin-export", "eis", "drt", "anything-at-all"):
        assert licensing.allowed(feature, store)
    assert licensing.allowed("x")          # default store too, no exception


def test_device_id_and_request():
    assert DEVICE_RE.match(licensing.device_id())
    assert licensing.activation_request().startswith("REQ-")


def test_test_key_licence_installs_and_verifies(store, test_key):
    claims = licensing.install(_issue(test_key, licensing.PRODUCT), store)
    assert claims["product"] == licensing.PRODUCT
    st = licensing.status(store)
    assert st.ok, st.reason
    assert st.edition == "pro"
    assert licensing.allowed("anything", store)


def test_other_product_refused(store, test_key):
    with pytest.raises(LicenceError):
        licensing.install(_issue(test_key, "figure-studio"), store)
    assert store.read() is None
    assert not licensing.status(store).ok


def test_dialog_shows_device_id(qapp_dialog, store, tmp_path, test_key):
    from ui.licence_dialog import LicenceDialog
    dlg = LicenceDialog(store=store)
    assert dlg.device_edit.text() == licensing.device_id()
    assert dlg.device_edit.isReadOnly()
    assert "Free" in dlg.edition_label.text()
    bad = tmp_path / "other.json"
    bad.write_text(_issue(test_key, "figure-studio"), encoding="utf-8")
    assert not dlg.install_from_path(bad)
    assert "not this application" in dlg.result_label.text()
    good = tmp_path / "good.json"
    good.write_text(_issue(test_key, licensing.PRODUCT), encoding="utf-8")
    assert dlg.install_from_path(good)
    assert "Pro" in dlg.edition_label.text()
    dlg.copy_activation_request()
    from PySide6.QtWidgets import QApplication
    assert QApplication.clipboard().text().startswith("REQ-")


def test_main_window_has_licence_menu(qapp_dialog):
    from ui.main_window import MainWindow
    win = MainWindow()
    labels = [a.text() for a in win._menu("&Help").actions()]
    assert "&Licence…" in labels


@pytest.fixture
def qapp_dialog():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])
