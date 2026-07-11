# Supercapacitor & DSC Electrochemical Analysis Suite

Created by Ezzeldien Yousef ([ezzyousef2@aucegypt.edu](mailto:ezzyousef2@aucegypt.edu))
Copyright © 2026 Ezzeldien Yousef. All rights reserved.

A cross-platform (Windows/macOS/Linux) desktop application for:

- **Manual Calculator** — plug in known numbers directly (current, mass,
  voltage window, discharge time, scan rate, resistance, peak area, etc.)
  with no file needed, for GCD/CV capacitance, energy/power density, ionic
  conductivity, 2e/3e conversions, and DSC enthalpy.
- **GCD** (galvanostatic charge/discharge) analysis for 2-electrode and
  3-electrode supercapacitor systems, with automatic detection of whether
  a discharge curve needs the *normal (linear)* or *integral (non-linear)*
  capacitance formula, plus ESR, energy density, power density, and
  symmetric/asymmetric electrode-mass conversions.
- **CV** (cyclic voltammetry) specific capacitance / specific capacity,
  both the *direct/rectangular* form (ideal EDLC) and the *integral* form
  (pseudocapacitive/non-rectangular curves).
- **Rate Study**: capacitance vs. scan rate / current density, b-value
  analysis, **Dunn's method** (capacitive vs. diffusion-controlled current
  split), and **Trasatti's method** (outer/inner/total capacitance
  extrapolation).
- **EIS** (electrochemical impedance spectroscopy): Nyquist/Bode plots,
  low-frequency capacitance, ESR, **ionic conductivity**, and **Randles-
  type equivalent circuit fitting** (Rs + Rct∥CPE, with optional Warburg
  element) via nonlinear least squares.
- **DSC** water-state analysis for hydrogel/gel electrolytes: free water,
  freezable-bound water, and non-freezable-bound water classification, plus
  a raw heat-flow peak integrator for computing transition enthalpy (J/g).
- File support: **Excel (.xlsx/.xls)**, **CSV/TSV**, **EC-Lab (.mpt)** text
  exports, and **EC-Lab binary (.mpr)** exports (read via the third-party
  `galvani` package — BioLogic has never published the `.mpr` spec, so this
  goes through a maintained, widely-used reverse-engineered community
  parser rather than an in-house guess at the byte layout; cross-check a
  few values against EC-Lab's own display before trusting `.mpr`-derived
  numbers for a publication. See `docs/EQUATIONS.md` for more on this
  trade-off.)

**New to programming?** See `docs/BEGINNER_SETUP_VSCODE.md` for a complete,
no-experience-assumed, step-by-step walkthrough of installing Python,
Visual Studio Code, and running this app — including how to package it
into a standalone .exe.

See `docs/EQUATIONS.md` for every formula used, its literature source, and
the conventions/caveats that affect the numbers it produces (including two
methods — b-value and Dunn's method — that carry a documented literature
critique of their limitations). Read that before trusting a result for a
publication — capacitance/energy numbers are highly sensitive to
mass-basis and formula-choice conventions that this app cannot infer for
you.

## Install

Requires Python 3.10+. If you're new to this, use `docs/BEGINNER_SETUP_VSCODE.md` instead of this section.

```bash
cd supercap_suite
pip install -r requirements.txt
```

## Run

```bash
python main.py
```

## Project layout

```
supercap_suite/
├── main.py                   # entry point
├── core/                     # pure-Python analysis math (no GUI deps, unit-testable)
│   ├── data_io.py             # Excel / CSV / EC-Lab .mpt loading
│   ├── gcd_analysis.py        # GCD capacitance (normal + integral), ESR, energy/power density, rate capability
│   ├── cv_analysis.py         # CV specific capacitance / capacity (direct + integral forms), b-value
│   ├── dunn_method.py         # Dunn's method: capacitive/diffusive current split
│   ├── trasatti_method.py     # Trasatti's method: outer/inner/total capacitance
│   ├── eis_analysis.py        # EIS capacitance, ESR, ionic conductivity, equivalent circuit fitting
│   └── dsc_analysis.py        # DSC water-type classification + enthalpy
├── ui/                        # PySide6 GUI
│   ├── main_window.py
│   ├── calculator_tab.py       # manual, no-file calculators
│   ├── gcd_tab.py
│   ├── cv_tab.py
│   ├── rate_study_tab.py       # CV-vs-scan-rate and GCD-vs-current-density studies
│   ├── eis_tab.py
│   ├── dsc_tab.py
│   └── widgets.py
├── docs/
│   ├── EQUATIONS.md            # formula sources & caveats
│   └── BEGINNER_SETUP_VSCODE.md  # no-experience-assumed setup guide
└── requirements.txt
```

## Building a standalone executable / Windows installer

See `docs/BEGINNER_SETUP_VSCODE.md` Step 10 for a beginner-friendly walkthrough. Short version:

```bash
pip install pyinstaller
pyinstaller SupercapSuite.spec
```

This produces a single-file binary (`dist/SupercapSuite.exe` on Windows)
that bundles Python and every dependency — it needs **nothing** installed
on the machine it runs on, not even Python. It only builds for the OS you
run it on — there is no cross-compiling from Linux to a Windows/macOS
binary; to ship for a different OS, run PyInstaller on a machine with that
OS installed.

**Windows installer**: `dist/SupercapSuite.exe` alone is already runnable
on any Windows PC with no install step — just copy the one file. For a
proper installer instead (Start Menu shortcut, uninstaller, Add/Remove
Programs entry), install [Inno Setup 6](https://jrsoftware.org/isdl.php)
(free) once on the build machine, then run:

```powershell
.\build_installer.ps1
```

which builds the exe and compiles `installer/SupercapSuite.iss` into
`installer/output/SupercapSuiteSetup.exe` — that one file is the complete
installer; it needs nothing installed on the target PC either.

## Using the Manual Calculator tab

If you already have summary numbers (e.g. read off an instrument screen or
copied from a paper) and just want a direct calculation with no file to
load, use this tab. Sub-tabs cover GCD capacitance (normal or integral),
CV capacitance (direct or integral), energy/power density, ionic
conductivity, 2-electrode↔3-electrode conversions, and DSC enthalpy.

## Using the GCD tab

1. **Open** an Excel/CSV/.mpt file. Column mapping (time/voltage/current)
   is auto-guessed from common EC-Lab column names but is always editable.
2. **Select the discharge segment** by row range (0-indexed). Use
   "Preview segment on plot" to check you've picked the actual discharge
   (not charge) portion before analyzing.
3. Choose the **current source**: from a data column (with a unit
   selector — A/mA/µA) or a manually entered value.
4. Enter the **active mass** and choose the **cell configuration**
   (3-electrode, symmetric 2-electrode, or asymmetric/hybrid 2-electrode)
   — this determines which mass basis is expected and which conversion
   (if any) is shown alongside the raw result.
5. **Capacitance formula**: leave on "Auto-detect" to let the app fit the
   discharge curve and pick normal vs. integral form based on an R²
   linearity threshold (adjustable), or force one method explicitly.
6. Click **Analyze** to get capacitance, ESR, energy density, and power
   density, with the method and R² always shown so the choice is never
   hidden.

## Using the CV tab

Select one full CV cycle's voltage/current columns and row range, set the
scan rate, active mass, and whether to report specific capacitance (F/g,
for EDLC/pseudocapacitive materials) or specific capacity (C/g, for
battery-type materials with redox plateaus).

## Using the Rate Study tab

- **CV vs. scan rate**: enter a table of (scan rate, specific capacitance)
  pairs from your individual CV analyses (e.g. from the CV tab, run once
  per scan rate) to run **Trasatti's method**. Enter a table of (scan
  rate, peak current) pairs to run **b-value analysis**.
- **GCD vs. current density**: load a file, add several discharge segments
  (one per current tested) to build a rate-capability study — outputs a
  table and plot of capacitance, energy density, power density, and
  retention (%) vs. current density.

## Using the EIS tab

Load Z real / Z imaginary / frequency columns, preview the Nyquist plot,
compute low-frequency capacitance and ESR, compute ionic conductivity
(enter electrolyte thickness and electrode area), or fit a Randles-type
equivalent circuit (with optional Warburg element) to get Rs, Rct, CPE
(Q, n), and (if applicable) the Warburg coefficient, with fit-quality
(reduced chi-squared) and an overlay plot.

## Using the DSC tab

- **Raw curve → peak area / enthalpy**: load a heat-flow-vs-time (or
  vs-temperature, with a scan-rate conversion) curve, select the peak
  region, and integrate it against a linear baseline to get peak area (J)
  and specific enthalpy (J/g). A button sends the computed peak area
  directly into the water-classification tool.
- **Water-type classification**: enter sample water/dry mass and melting-
  peak area(s) to get the free / freezable-bound / non-freezable-bound
  water breakdown (Eqs. 1-6 in `docs/EQUATIONS.md`).

## Known limitations

- `.mpr` (EC-Lab binary) files are read via the third-party `galvani`
  parser, not an officially published spec (BioLogic has never released
  one) — if a `.mpr` file fails to load or looks wrong, re-export as
  `.mpt` or Excel from EC-Lab instead.
- Curved/sigmoidal DSC baselines are not implemented, only linear
  baselines between user-chosen peak start/end points.
- The GCD/CV row-range segment selection is manual; there is no automatic
  cycle-splitting from a `cycle number` column yet — if your file has one,
  filter/sort it in Excel first, or note the row range for the cycle you
  want.
- ESR is computed from a simple high-frequency-intercept estimate, not a
  fitted steady-state-resistance extrapolation (though the equivalent-
  circuit fit in the EIS tab gives a more rigorous Rs if you use it).
- Equivalent circuit fitting uses a single nonlinear-least-squares run
  from heuristic initial guesses (no multi-start global optimization) —
  can converge to a local minimum on noisy/sparse spectra; check the
  overlay plot.
- The b-value and Dunn's-method capacitive/diffusive split have a
  documented literature critique (Pervez & Stallard, *Small*, 2023) —
  treat results as indicative, not definitive (see `docs/EQUATIONS.md`).
- CV rate-study input (for Trasatti's/b-value) is table-based (you supply
  scan rate + capacitance/peak-current pairs from individual analyses),
  not automatic multi-curve extraction from one file.
