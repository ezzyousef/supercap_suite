# Review log

Three independent reviews of the Supercapacitor & DSC Analysis Suite were run:
- science and statistics;
- code and data handling;
- user experience.

This file lists what they found and what was done about each finding.

Status:
- **fixed**: changed, with a regression test where one could be written. The tests are in `tests/test_review_fixes.py` and `tests/test_review_ui_fixes.py`.
- **changed wording**: the documentation or labels changed.
- **open**: not addressed in this round, with the reason.

## GCD

| Finding | Status |
|---|---|
| The integral form integrated absolute V. Whenever V_min ≠ 0 this inflated C, and a window running negative (three-electrode, against a reference) made it meaningless. | **fixed**: integrates V − V_min. A linear discharge now gives exactly I·Δt/ΔV for any window. |
| The IR drop was included in ΔV and Δt | **fixed**: the IR step is detected and excluded by default (there is a checkbox), and the excluded drop is reported |
| ESR = ΔV_IR/I applied straight after charging, where the current changes by 2I | **fixed**: there is an option for the current-reversal convention ΔV_IR/2I (the default) or for starting from rest. The label states which convention was used. |
| IR drop estimated from the first two samples only | **fixed**: the whole step is used when it spans several samples |
| Energy and power density reported for three-electrode (single-electrode) data | **fixed**: shown as n/a, with the reason. The Ragone plot says it applies to two-electrode cells only. |
| Coulombic efficiency taken as the time ratio, which is wrong for unequal currents | **fixed**: Q_discharge/Q_charge when the file has a current column. The result says which form was used. |
| Retention always relative to cycle 1, which is often unrepresentative | **fixed**: the baseline can be the mean of the first N cycles |

## CV

| Finding | Status |
|---|---|
| Stacked cycles integrated together (charge adds up, so C is about N times too large) | **fixed**: a warning appears when no cycle is picked from a cycle column, and also when the selected rows look like more than one cycle |
| The current unit stayed at mA from the previous file | **fixed** |
| The rectangularity score gave an ideal rectangle 0.5 | **fixed**: computed on \|I\| |

## EIS, equivalent circuits, Kramers–Kronig, DRT

| Finding | Status |
|---|---|
| The "Randles" circuits with a Warburg element put W in series with the capacitor, not with Rct | **fixed**: the classic `randles_classic_*` Rs + Cdl‖(Rct+W) was added. The old variant is kept and documented. |
| Unweighted CNLS: large low-frequency \|Z\| dominated the fit | **fixed**: modulus weighting by default (`weighting="unit"` is still available) |
| The same spectrum in kΩ fitted far worse than in Ω (54 % vs 0.8 % residual) | **fixed**: parameters are scaled by their start values; the fit no longer depends on units |
| Auto-fit ranked by χ², which always favours more parameters | **fixed**: AICc ranking. Within 2 units of the best, the simplest unpinned model is chosen. |
| "Reduced χ² < 5" was used as the quality test, which depends on units | **fixed**: RMS residual as a % of \|Z\|, plus a misfit warning above 5 %. The card and plot titles reflect warnings. |
| C and Y0 capped at 10 F | **fixed**: up to 1e5 |
| Interchangeable stages came back in random order | **fixed**: ordered by time constant |
| The KK test had no series C or L, so valid supercapacitor spectra failed | **fixed**: lin-KK series C and L, plus modulus weighting |
| KK pass/fail barely reacts to smooth drift (a 30 % drift leaves only about 2.5 % residual) | **fixed**: the lag-1 autocorrelation of the residuals is reported. Above 0.5 the result reads "PASSED, but with a systematic trend" and a drift warning is shown. On synthetic data this value was -0.15 to 0.11 for valid spectra and 0.66 to 0.91 with drift. Automatic element-count selection (μ criterion) was tried too, but it stopped too early on valid data, so it was not adopted. |
| DRT λ fixed at 1e-3 | **fixed**: optional real/imaginary cross-validation picks λ. The smoothest λ within 20 % of the best score is used. |
| Trasatti fits had no goodness of fit | **fixed**: R² is reported, with a warning below 0.95 |
| The docs described Dunn's method as voltage-resolved, but the app runs the peak-current form | **changed wording** |

## DSC

| Finding | Status |
|---|---|
| The heat-flow unit was assumed to be mW, so W/g data gave wrong enthalpies | **fixed**: unit selector guessed from the header (W, mW, µW, W/g, mW/mg). Normalised data is scaled by the sample mass. |
| A temperature X axis was plotted as "Time (s)" | **fixed** |
| The docs said ΔH_f defaults to 334 J/g, but the code uses 333.55 | **changed wording**: the docs give 333.55 and explain how it differs from the paper's 334 |
| Overlapping melting peaks are not separated | **fixed**: when the integration window holds several peaks, each is reported with its own area and ΔH. The split is a perpendicular drop at the valley between the maxima: simple and standard, but approximate when peaks overlap strongly (this is stated in the results). |
| Naming of the freezable-bound water fraction (W_fb) compared with the paper | **open**: the paper was not available in this session to check the wording |

## Code and data handling

| Finding | Status |
|---|---|
| A result from the previous file stayed exportable after loading a new file | **fixed**: every tab clears it on load |
| A fit still running when a new file loaded wrote its result over the new data | **fixed**: a data-generation guard drops stale results |
| Closing during an auto-fit destroyed a running QThread and aborted the process | **fixed**: quitting waits for workers |
| Busy button text stuck at "Running…" | **fixed** |
| European `;` CSV with decimal commas split on commas | **fixed**: delimiter and decimal sniffing; blank rows are dropped |
| Exporting into an existing workbook split the note and the table across two sheets | **fixed**: export notes also carry a timestamp |
| Appending to a recorded-results sheet with a note corrupted the header | **fixed** |
| The status bar kept another page's message | **fixed** |
| EIS/DRT result panels needed 840/740 px of height | **fixed**: 600 px |
| (found by the Windows build) The test run crashed at exit on Windows now and then, already before this review: tests left widgets for Python to destroy after the QApplication | **fixed**: every test now deletes its widgets while the application exists; background workers no longer sit in a reference cycle |

## Release

- Version 2.1.0. The Word guide was updated: version, the changed passages, and a
  What's-new section. Its screenshots are still those of 2.0.0.
- The Windows installer and portable zip are built by `.github/workflows/windows-build.yml`
  (tests, PyInstaller, self-test of the exe, Inno Setup) and downloadable from each run.

## Still open

- The naming of the freezable-bound water fraction (W_fb) has not been checked against
  the source paper, because the paper was not available.
