"""Session-wide test hooks."""


def pytest_sessionfinish(session, exitstatus):
    # Let any background fit finish and drop the references to it while the
    # QApplication still exists, so no QThread outlives it at interpreter exit.
    try:
        from ui.workers import _LIVE, wait_for_workers
    except Exception:  # noqa: BLE001 - nothing to clean up if the UI was never imported
        return
    wait_for_workers(30000)
    _LIVE.clear()
