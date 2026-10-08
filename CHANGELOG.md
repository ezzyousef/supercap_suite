# Changelog

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
