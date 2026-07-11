from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout, QLabel

from .gcd_tab import GcdTab
from .cv_tab import CvTab
from .dsc_tab import DscTab
from .eis_tab import EisTab
from .rate_study_tab import RateStudyTab
from .calculator_tab import CalculatorTab
from . import theme
from .resources import asset_path


class AboutTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        logo_row = QHBoxLayout()
        logo_label = QLabel()
        logo_pixmap = QPixmap(asset_path("eml_logo.png"))
        if not logo_pixmap.isNull():
            logo_label.setPixmap(logo_pixmap.scaledToHeight(90, Qt.TransformationMode.SmoothTransformation))
        logo_row.addWidget(logo_label)
        logo_row.addStretch()
        layout.addLayout(logo_row)

        text = QLabel(
            "<h2>Supercapacitor & DSC Electrochemical Analysis Suite</h2>"
            f"<p style='color:{theme.INK_DIM}'>Built for the Energy Materials Laboratory (EML)</p>"
            "<p>Tools for two- and three-electrode supercapacitor characterization "
            "and DSC gel-electrolyte water-state analysis.</p>"
            "<ul>"
            "<li><b>Manual Calculator</b>: plug in known numbers (current, mass, "
            "voltage window, discharge time, scan rate, resistance, etc.) directly "
            "-- no file required -- for GCD/CV capacitance, energy/power density, "
            "ionic conductivity, 2e/3e conversions, and DSC enthalpy.</li>"
            "<li><b>GCD tab</b>: loads galvanostatic charge/discharge data (Excel, CSV, "
            "or EC-Lab .mpt), auto-detects whether the discharge curve is linear "
            "(EDLC-like) or non-linear (pseudocapacitive/battery-like) and applies "
            "the matching capacitance formula (normal vs. integral form), plus ESR, "
            "energy density, power density, and 2-electrode/3-electrode conversions.</li>"
            "<li><b>CV tab</b>: specific capacitance or specific capacity from cyclic "
            "voltammetry cycle integration.</li>"
            "<li><b>Rate Study tab</b>: capacitance vs. scan rate / current density "
            "series, b-value analysis, Dunn's capacitive/diffusive split, and "
            "Trasatti's outer/inner/total capacitance extrapolation.</li>"
            "<li><b>EIS tab</b>: Nyquist/Bode plots, low-frequency capacitance, ESR, "
            "ionic conductivity, and Randles-type equivalent circuit fitting.</li>"
            "<li><b>DSC tab</b>: raw heat-flow peak integration and enthalpy "
            "calculation, plus free/freezable-bound/non-freezable-bound water "
            "classification for hydrogel electrolytes.</li>"
            "</ul>"
            f"<p style='color:{theme.INK_DIM}'><i>All formulas are standard literature "
            "conventions with known caveats (mass basis, IR-drop handling, "
            "heat-of-fusion reference value, b-value/Dunn's-method limitations, "
            "etc.) -- see docs/EQUATIONS.md in the project folder for sources and "
            "the exact assumptions each calculation makes. This tool does not "
            "replace understanding which convention is correct for your specific "
            "system.</i></p>"
            f"<p style='color:{theme.INK_DIM}'>&copy; {theme.COPYRIGHT_YEAR} Ezzeldien Yousef. "
            f"Created by Ezzeldien Yousef "
            f"(<a href='mailto:{theme.AUTHOR_EMAIL}' style='color:{theme.RAW}'>{theme.AUTHOR_EMAIL}</a>).</p>"
        )
        text.setWordWrap(True)
        text.setOpenExternalLinks(True)
        layout.addWidget(text)
        layout.addStretch()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Supercapacitor & DSC Analysis Suite")
        self.setWindowIcon(QIcon(asset_path("app_icon_256.png")))
        self.resize(1200, 800)

        tabs = QTabWidget()
        self.setCentralWidget(tabs)

        tabs.addTab(CalculatorTab(), "Manual Calculator")
        tabs.addTab(GcdTab(), "GCD (Charge/Discharge)")
        tabs.addTab(CvTab(), "Cyclic Voltammetry")
        tabs.addTab(RateStudyTab(), "Rate Study (Dunn's / Trasatti's)")
        tabs.addTab(EisTab(), "EIS (Impedance)")
        tabs.addTab(DscTab(), "DSC (Water / Enthalpy)")
        tabs.addTab(AboutTab(), "About & Equations")

        tabs.setIconSize(QSize(11, 11))
        for i, color in enumerate(theme.TAB_COLORS[:tabs.count()]):
            tabs.setTabIcon(i, theme.make_color_dot_icon(color))
