"""Session-wide test hooks."""
import sys

# Origin is not installed on the test machines. Importing originpro there loads its native
# OriginExt module, and on Windows CI the interpreter then crashed during shutdown
# (access violation after every test had passed). The tests never talk to Origin -- the
# Origin export tests use stand-ins -- so the real package is kept out of the test process;
# the app then reports Origin as "not installed", which is the truth on these machines.
sys.modules.setdefault("originpro", None)


def pytest_sessionfinish(session, exitstatus):
    # Let any background fit finish and drop the references to it while the
    # QApplication still exists, so no QThread outlives it at interpreter exit.
    try:
        from ui.workers import _LIVE, wait_for_workers
    except Exception:  # noqa: BLE001 - nothing to clean up if the UI was never imported
        return
    wait_for_workers(30000)
    _LIVE.clear()
