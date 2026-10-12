# Changelog

## 2.2.1

- **Cancel long fits:** a Cancel button appears while EIS auto-fit, batch fit, single fits, DRT/DCT and cycling stability run. Auto-fit stops after the current circuit, batch fit after the current file, and λ selection after the current candidate; the others discard their result.
- **Progress:** auto-fit shows "Auto-fit: 37/91 circuits (…)", batch fit shows the files done.

## 2.2.0

- **Figures in the lab's house style (Figure Studio's):** the "Review" palette and Figure Studio's Light/Dark colours, DejaVu Sans with bold axis titles and tick labels, an open frame, outward ticks, a horizontal grid only and a frameless legend — on screen and in every PNG/SVG/PDF export.
- **Accessibility (WCAG 2.2 AA), from a UX/accessibility review:**
  - Visible keyboard focus on buttons, inputs, check boxes, radio buttons and table items.
  - Input and check-box outlines that meet 3:1 contrast.
  - Accent-coloured text (selected tabs, link-style buttons) at 4.5:1 or better in both themes.
  - Readable section headings in the side bar.
  - Labels tied to their inputs (Alt+letter focuses the field; screen readers announce it).
- **Cycling stability runs in the background:** large cycling files no longer freeze the window; the button shows "Analyzing cycles…" until it finishes.
- **Bode plot:** the phase axis has its own right-hand frame and readable dark text ("Phase (degrees, dashed)") instead of light cyan.
- **Dark-theme plots** use the house dark background.
- **Normalisation inputs** (mass, area, volume) are labelled for screen readers and Alt+letter.
- **Undo is Ctrl+Z** (it was Ctrl+X, which means Cut everywhere else and silently undid a removal); Redo stays Ctrl+Y.
- **Keyboard:** visible focus on Export, Record, Formula & source and the section buttons; Tab leaves tables; the plot toolbar is reachable with Tab; every caption on every tab is tied to its input for screen readers and Alt+letter.
- While cycling stability runs, Open, Batch import and downsampling wait too.
- Legends and titles use the house sizes; the empty-plot placeholder has the house open frame; accent-coloured text uses the readable tint in dark mode.
- Switching theme twice no longer recolours the plot background.

## 2.1.0

See `docs/REVIEW_LOG.md` for every review finding and what was done.

- **GCD:**
  - the integral formula is corrected for windows that do not end at 0 V;
  - the IR drop is excluded from ΔV;
  - ESR uses ΔV_IR/2I after a current reversal;
  - no energy or power is given for three-electrode data.
- **Cycling:** coulombic efficiency is computed from charge when a current column exists; the retention baseline can average the first N cycles.
- **CV:** warns about stacked cycles. An ideal rectangle now scores 1 on the rectangularity check.
- **EIS:**
  - modulus-weighted fitting, which no longer depends on units;
  - AICc model ranking;
  - a misfit warning;
  - the classic Randles circuit;
  - the 10 F ceiling is lifted;
  - interchangeable stages are reported fastest first.
- **Kramers–Kronig:** series C and L (lin-KK), modulus weighting, and a flag for a systematic trend (drift).
- **DRT:** optional λ chosen by real/imaginary cross-validation.
- **DSC:** heat-flow unit selector; overlapping peaks split; temperature axis when X is temperature.
- **Reliability:**
  - stale results are cleared when a file loads;
  - fits on old data are discarded;
  - quitting is safe during a fit;
  - European CSV files are read correctly;
  - several export bugs are fixed.
- **Windows build** on GitHub Actions.
