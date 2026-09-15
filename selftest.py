"""`SupercapSuite.exe --selftest`: exercise the application without a visible window.

Used to verify a packaged build: imports every module, runs core analyses on synthetic
data, builds a styled Origin graph against a stand-in Origin object, opens every page in
both themes. Prints plain ASCII, because a frozen Windows console uses the legacy code page.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def run_selftest() -> int:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    failures: list[str] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        print(("ok    " if ok else "FAIL  ") + label + ("" if ok else f"  ({detail})"))
        if not ok:
            failures.append(label)

    try:
        import numpy as np
        import pandas as pd
        from unittest.mock import MagicMock
        from core import eis_analysis, gcd_analysis, origin_export
        from ui.resources import APP_NAME, APP_VERSION
    except Exception as exc:                                    # noqa: BLE001
        print(f"FAIL  imports: {exc}")
        return 1
    frozen = "frozen" if getattr(sys, "frozen", False) else "source"
    print(f"{APP_NAME} {APP_VERSION} ({frozen} build)\n")

    try:
        t = np.linspace(0, 100, 200)
        linearity = gcd_analysis.classify_discharge_linearity(t, 1.0 - t / 100)
        check("GCD: a straight discharge is classified linear", bool(linearity.is_linear))
    except Exception as exc:                                    # noqa: BLE001
        check("GCD linearity", False, str(exc))

    try:
        w = np.logspace(5, -2, 60) * 2 * np.pi
        z = 2 + 10 / (1 + 1j * w * 1e-2)
        esr = eis_analysis.equivalent_series_resistance_from_nyquist(z.real, -z.imag)
        check(f"EIS: ESR from a synthetic Nyquist ({esr:.2f} ohm, expected ~2)", abs(esr - 2) < 0.5)
    except Exception as exc:                                    # noqa: BLE001
        check("EIS ESR", False, str(exc))

    try:
        df = pd.DataFrame({"graph_x_z_re_ohm": [1.0, 2.0, 3.0], "graph_y_neg_z_im_ohm": [1.0, 2.0, 1.0],
                           "graph_fit_y_neg_z_im_ohm": [1.1, 1.9, 1.0]})
        op, graph, layer = MagicMock(), MagicMock(), MagicMock()
        graph.__getitem__.return_value = layer
        op.new_graph.return_value = graph
        created = origin_export._plot_worksheet_data(op, MagicMock(), df, {c: i for i, c in enumerate(df.columns)}, "EIS")
        types = [c.kwargs.get("type") for c in layer.add_plot.call_args_list]
        check("Origin: styled graph (data as symbols, fit as a line)", created and types == ["s", "l"], str(types))
    except Exception as exc:                                    # noqa: BLE001
        check("Origin graph styling", False, str(exc))
    print(f"note  OriginLab automation {'is' if origin_export.is_available() else 'is not'} installed")

    try:
        from PySide6.QtWidgets import QApplication
        from ui import theme
        from ui.main_window import MainWindow

        app = QApplication.instance() or QApplication([])
        app.setStyle("Fusion")
        window = MainWindow()
        window.show()
        for mode in ("light", "dark"):
            window.apply_theme(mode)
            for key in window.page_keys:
                window.go_to(key)
                for _ in range(5):
                    app.processEvents()
        built = sum(window.is_page_built(k) for k in window.page_keys)
        check(f"interface: {built} of {len(window.page_keys)} pages built in light and dark",
              built == len(window.page_keys) and theme.mode() == "dark")
        check("no duplicate keyboard shortcuts", window.shortcut_conflicts() == [], str(window.shortcut_conflicts()))
        window.apply_theme("light")
        window.close()
    except Exception as exc:                                    # noqa: BLE001
        check("interface", False, f"{type(exc).__name__}: {exc}")

    print()
    if failures:
        print(f"SELF-TEST FAILED - {len(failures)} problem(s): {', '.join(failures)}")
        return 1
    print("SELF-TEST PASSED - this build is working.")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(run_selftest())
