# Equation regression report

Selected formulas from `docs/EQUATIONS.md`, checked against synthetic data generated from known physics. Tests: `tests/test_oracle_equations.py` (24 tests). Run: `py -3 -m pytest -q tests/test_oracle_equations.py`. Last run 2026-11-15: **24 passed**.

Two kinds of check are mixed below and marked: **recovery** (the app returns a parameter the data was built from, computed without calling the app) and **consistency** (two app functions, or one function under a unit change, agree). An independent read-only review by Codex (2026-11-15) found that an earlier version of two tests was not independent and that this page claimed more coverage than it had; both were corrected.

Each row is also a worked example: the inputs, the value physics says is right, and the value the app returned.

| § | Quantity | Synthetic data (known truth) | Expected | App result |
|---|---|---|---|---|
| 1a | GCD capacitance, linear | Ideal 2 F capacitor + 0.5 Ω series resistor, ±0.1 A, 10 mg, sampled every 10 ms | 200 F/g | 200.0 F/g, method "normal" |
| 1a | Excluded IR step | same cell; current reverses, so the step is 2·I·R | 0.100 V | 0.100 V |
| 1a | Areal, volumetric | same total capacitance ÷ 1.5 cm² or 0.02 cm³ | C/area, C/volume | equal to 12 digits |
| 1b | GCD capacitance, integral | V(t) = V_min + 1 V·√(1 − t/T), T = 100 s, I = 50 mA; ∫(V − V_min)dt = ⅔·ΔV·T | 6.667 F | within 0.1 %, **identical for V_min = 0, −0.2 and +0.4 V** |
| 1b | Integral and linear forms, linear curve (recovery) | the RC cell above, segment after the IR step taken from the generator | 2 F | both 2 F (1e-6) |
| 2 | ESR, current reversal (ΔV/2I) | the RC cell above | 0.5 Ω | 0.500 Ω |
| 2 | ESR, from rest (ΔV/I) | step I·R from a cell at rest | 0.5 Ω | 0.5 Ω |
| 3 | Energy density | ½·C·ΔV² in J/g → Wh/kg, C = 200 F/g, ΔV = 1 V | 27.78 Wh/kg | 27.78 Wh/kg |
| 3 | Energy per area/volume basis | same, no g→kg factor | J/3600 per basis | equal |
| 3 | Energy actually delivered | ∫ I·V dt of the simulated 2 F cell, 1 V → 0 V | 27.78 Wh/kg | within 0.1 % |
| 3 | Power density | E·3600/Δt | from the SI chain | equal |
| 4 | Symmetric cell → electrode | two identical 1 F, 5 mg electrodes in series | electrode = 4 × cell | equal |
| 4 | Series capacitance | 3 F and 6 F in series | 2 F | 2 F |
| 4 | Mass balance | charge equality C₊·m₊·ΔV₊ = C₋·m₋·ΔV₋ | equal charge | equal |
| 5 | CV, integral form | 2 F capacitor, triangular sweep −0.2…0.8 V at 50 mV/s | 2 F | 1.999 F |
| 5 | CV, direct form | I = C·v | 2 F | 2 F |
| 5 | Specific capacity | ∮I dV / (2·m·v) = C·ΔV/m | 200 C/g | within 0.2 % |
| 5 | CV with series R | R = 0.05 Ω (τ = 0.1 s), 20 s half period | 2 F·(1 − 2τ/T½) | within 1 % |
| 5 | Two stacked cycles | the same sweep twice | 4 F (why the app warns about stacked cycles) | 4 F; `count_cycles` = 2 |
| 5 | b-value | I = a·v^0.72 at 5 scan rates | 0.72 | 0.72 |
| 5a | Dunn split | I = 0.0125·v + 0.0986·√v | k₁, k₂ | equal to 1e-9 |
| 5b | Trasatti outer | C(v) = 80 + 3/√v | 80 F/g | 80 F/g |
| 5b | Trasatti total | 1/C(v) = 0.02·√v + 1/250 | 250 F/g | 250 F/g |
| 6 | EIS capacitance | ideal 2 F capacitor at 10 mHz | 2 F (200 F/g at 10 mg) | equal |
| 6 | Ionic conductivity | σ = L/(R·A): 0.1 cm, 2 cm², 5 Ω | 0.01 S/cm | 0.01 S/cm |
| 6a | Circuit fit | exact spectrum of Rs + (Rct ‖ C), Rs = 1 Ω, Rct = 10 Ω, C = 1 mF, 100 kHz…10 mHz | 1, 10, 0.001 | 1.0, 10.0, 0.001 |
| 6b | Kramers–Kronig, valid data | the same spectrum | passes, no trend | passes, residual 0.0 %, no trend |
| 6b | Kramers–Kronig, 30 % drift | the spectrum scaled by 1 → 1.3 across the sweep | flagged | **residual test still passes (1.25 %)**; flagged by `systematic_trend` (autocorrelation 0.87). Known and documented in `REVIEW_LOG.md` |
| 10 | DRT of one RC element | Rs = 1 Ω, Rct = 10 Ω, τ = R·C = 10 ms | peak at 10 ms, area 10 Ω, R∞ 1 Ω | peak 9.96 ms, area 10.03 Ω, R∞ 0.986 Ω |
| 9 | DSC peak area | Gaussian heat-flow peak of exactly 0.5 J, σ = 20 s, 0.1 s sampling | 0.5 J | 0.5 J (1e-6) |
| 9 | Enthalpy | 0.5 J / 10 mg | 50 J/g | 50 J/g |
| 9 | Heat-flow units | the same curve as W and as W/g with the mass | identical mW | identical |
| 9 | Sloping baseline | peak + (0.3 mW + 0.001 mW/s · t), baseline given | 0.5 J | 0.5 J |
| 8 | Water classification (recovery) | 0.40 g water, 0.10 g dry, 0.30 g freezable of which 0.10 g below 0 °C | W_t = 4, W_f = 3, W_nb = 1, W_fb = 1, W_free = 2, W_b = 2 | all equal |

## What this does not cover

- No oracle yet for: Bode magnitude/phase (§6c), rate capability and retention (§7), the Ragone plot (§7a), the automated symmetric/total peak split (§9a), the integration-accuracy self-check (§9b) and DCT (§10a). Several of these have ordinary unit tests in the existing suite.

- Real instrument exports: none were supplied, so every test uses synthetic data. Results on real, noisy data still depend on segment choice, baseline choice and the linearity threshold, all of which the app shows to the user.
- Overlapping DSC peaks and the DCT variant of DRT have their own tests in the existing suite, not oracle tests here.
- The literature sources of the equations were not re-checked in this round (see `EQUATIONS.md` for its own caveats).
