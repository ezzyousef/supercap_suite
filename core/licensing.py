"""Licensing for Supercap Suite, built on the shared ``labkit.licence`` SDK.

Enforcement is OFF. Prices and editions have not been decided, so every feature stays
available whether or not a licence is installed: ``allowed()`` returns True for anything while
``ENFORCE`` is False, and ``FREE_FEATURES`` is everything. The Help > Licence dialog only shows
the status, the device id and lets a licence file be installed, ready for later.

No network access happens here.
"""
from __future__ import annotations

from datetime import date

from labkit import licence
from labkit.licence import LicenceError, LicenceStore, Status  # noqa: F401 - re-exported

PRODUCT = "supercap-suite"
PUBLIC_KEYS = {"labapps-2026": "g93gW00t+FyNNul4QhlGPReeosESePiX9vmr0UEL6hs="}
RELEASE_DATE = date(2026, 11, 14)
ENFORCE = False
FREE_FEATURES = frozenset({"*"})      # everything is free while ENFORCE is False


def store() -> LicenceStore:
    return LicenceStore(PRODUCT)


def status(licence_store: LicenceStore | None = None) -> Status:
    """The installed licence's status for this computer, today. Never raises."""
    try:
        return licence.check(PRODUCT, PUBLIC_KEYS, store=licence_store, release_date=RELEASE_DATE,
                             free_features=FREE_FEATURES)
    except Exception as e:  # noqa: BLE001 - a licence problem must never stop the app
        return Status(ok=False, reason=f"The licence could not be checked: {e}",
                      features=FREE_FEATURES)


def allowed(feature: str, licence_store: LicenceStore | None = None) -> bool:
    """Whether ``feature`` may be used. Always True while enforcement is off."""
    if not ENFORCE:
        return True
    st = status(licence_store)
    return st.entitled(feature) or feature in FREE_FEATURES or "*" in FREE_FEATURES


def device_id() -> str:
    return licence.device_id(PRODUCT)


def activation_request() -> str:
    return licence.activation_request(PRODUCT)


def install(text: str, licence_store: LicenceStore | None = None) -> dict:
    """Verify and save a licence. Raises LicenceError with a sentence for the user."""
    return (licence_store or store()).install(text, PRODUCT, PUBLIC_KEYS)
