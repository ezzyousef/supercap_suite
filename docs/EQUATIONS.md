# Equations used in this app, and their sources

This file lists every formula implemented in `core/`, where it came from, and
the caveats that matter for getting a correct (not just a computed) number.
It exists so results from this app can be defended/checked against the
literature rather than trusted blindly.

I am not a peer reviewer of these source papers -- I extracted the equations
as printed and cross-checked the internal consistency of the energy-density
derivation against two independent sources (they agree). If you need this
for a publication, verify the printed equations against the original PDFs
yourself; OCR/extraction errors are possible even when I've tried to avoid
them.

**Consensus (Google-Scholar-style literature search) cross-checks performed:**
- GCD linear-vs-integral capacitance formula choice: searched and found
  consistent with the broader supercapacitor-testing literature (e.g.
  Helseth, *J. Energy Storage* 2021, "Comparison of methods for finding the
  capacitance of a supercapacitor"; Zhang et al., *J. Energy Storage* 2024)
  -- no contradictions found with the normal/integral distinction used here.
- Dunn's method / b-value: searched and found both are indeed the standard,
  widely-used metrics in the field (numerous 2020-2024 papers use them as
  implemented here), AND found a specific peer-reviewed critique of their
  limitations (Pervez & Stallard, *Small*, 2023) -- that critique is
  reflected as a caveat in the relevant sections below rather than silently
  omitted.
- Trasatti's method and ionic conductivity (sigma = L/(R*A)): consistent
  with how they're reported across the broader literature searched.

---

## 1. GCD (galvanostatic charge/discharge) capacitance

### 1a. Normal / linear form
```
C_s = (I * dt) / (m * dV)
```
Valid ONLY for a (near-)linear (triangular) discharge V(t) curve -- the
signature of an ideal or near-ideal EDLC. Source: this is "Eqn (9)" in
Bonet, Loupias, Béguin et al.-style integral-capacitance papers, and is
described in Zhang & Pan Zhao's *Advanced Energy Materials* reviews as
"the most widely used expression ... in the scientific literature" for
symmetric EDLCs (Zhang et al., *Adv. Energy Mater.* 2015, 5, 1401401,
eqn 4-9; equivalent form in the desktop-app-builder skill reference).

### 1b. Integral form (non-linear discharge)
```
C_s = (2 * I * ∫V dt) / (m * dV**2)
```
Required when the discharge curve is non-linear (pseudocapacitive,
battery-type, or asymmetric-hybrid materials with sloping/plateaued
discharge). Source: explicitly given as "eqn (1)" in a hydrogel-electrolyte
supercapacitor paper in this project's source PDFs (citing Mathis et al.),
stated there as superior for pseudocapacitive materials "because it
accurately reflects the complex charge storage mechanisms ... thereby
minimizing miscalculations." The same functional form (as specific
capacity, Q_s, without the /dV) appears as "Eq. (2)" in a MOF/PANI battery-
grade electrode paper in the source PDFs.

### How this app decides which one to use
`core/gcd_analysis.classify_discharge_linearity()` fits V = a*t + b to the
discharge segment and checks R². If R² >= threshold (default 0.98, user-
adjustable), the discharge is treated as linear and the normal formula is
used; otherwise the integral formula is used. **The 0.98 threshold is a
practical heuristic, not a value taken from any of the source papers** --
none of them specify a numeric linearity cutoff; they only describe
qualitatively "nearly perfect triangular shape" vs "non-linear discharge
profiles." Always check the plotted curve and the reported R² for
borderline cases (R² between ~0.9 and 0.98) rather than trusting the
automatic classification alone.

## 2. IR drop / ESR

```
ESR = IR_drop / I
```
This is a simple single-step convention. The source PDFs describe more
rigorous approaches (e.g. extrapolating the steady-state linear region of
the discharge back to t=0, "Advanced Energy Materials 2020, Zhao et al.");
this app implements only the simple two-point IR-drop estimate
(`estimate_ir_drop`) followed by ESR = IR_drop / I, and documents in-code
that some labs instead use IR_drop / (2I) for a full-cycle convention. This
is exactly the kind of convention choice the app cannot silently resolve
for you -- state which convention you used when reporting ESR.

## 3. Energy density / power density

```
E (Wh/kg) = C_s * dV**2 / 7.2
P (W/kg)  = E * 3600 / dt
```
Derived from E (J/g) = 0.5 * C_s * dV**2 (standard capacitor energy
formula), converted to Wh/kg. Cross-checked against two independent source
PDFs that both state numerically equivalent forms: "ED = ΔV²·Cs / 7.2" and
"PD = E·3600/Δt" (RSC hydrogel-electrolyte paper, eqns 2-3), and the
underlying 1/2·C·V² derivation in Zhang et al., *Adv. Energy Mater.* 2015,
eqns 26-28.

## 4. Two-electrode / three-electrode conversions

```
C_spec,electrode = 4 * C_spec,cell          (symmetric 2-electrode cell)
C_spec,cell(2e)   = C_spec,electrode(3e) / 4  (inverse estimate)
```
Source: Zhang et al., *Adv. Energy Mater.* 2015, 5, 1401401, eqns 10-13 --
derived for a SYMMETRIC two-electrode cell where both electrodes have
equal mass and equal individual capacitance. The paper explicitly shows
`C_Sa = 4 * C_Sb` (three-electrode single-electrode capacitance = 4x the
symmetric two-electrode cell capacitance) and states this "has been
validated experimentally by Béguin et al." This factor is NOT valid for
asymmetric/hybrid cells -- use the mass-balance and series-capacitance
functions instead for those.

```
m+ / m- = (C_spec,neg * dV_neg) / (C_spec,pos * dV_pos)      (mass balance)
1/C_cell = 1/C_pos + 1/C_neg                                  (series capacitance)
```
Source: integral-capacitance PCCP paper (10.1039/C4CP05124F), eqns 4-5,12,
and Zhang et al. 2015 eqns 14-18 for the general asymmetric case.

**Caveat repeated from the PCCP source paper**: these relationships assume
the charge stored by each electrode is proportional to its potential swing
and its own specific capacitance. The same paper explicitly warns that in
some real systems (e.g. dissimilar ion sizes causing unequal potential
splitting) "the application of eqn (9) [the simple factor-of-4 relation]
to this system would be meaningless and would lead to totally wrong
capacitance results" -- always check the individual electrode potential
profiles (via a 2-3 synchronous/three-electrode experiment) before applying
the symmetric-cell shortcut.

## 4a. Gravimetric / areal / volumetric capacitance normalization

Every GCD and CV capacitance formula above (normal, integral, and CV's
direct/rectangular and integral forms) computes the SAME underlying total
capacitance (Farads) regardless of what it's normalized by:

```
C_total = (I * dt) / dV                        (GCD normal)
C_total = (2 * I * ∫V dt) / dV**2               (GCD integral)
C_total = I / scan_rate                          (CV direct/rectangular)
C_total = ∮I dV / (2 * scan_rate * dV)           (CV integral)
```

Dividing `C_total` by active mass (g), electrode geometric area (cm2), or
electrode volume (cm3) gives the gravimetric (F/g), areal (F/cm2), or
volumetric (F/cm3) capacitance respectively -- all three are standard
ways supercapacitor capacitance is reported in the literature, and the
GCD/CV tabs (both manual entry and file-based/automated) let you pick
which one applies to your sample via a "Normalize by" selector. Energy
density (Section 3) follows the same pattern: the traditional Wh/kg
convention additionally converts g -> kg, which does NOT apply to an
areal/volumetric basis -- `core.gcd_analysis.energy_density_wh()` (Wh per
whatever basis, no g->kg factor) is used instead of
`energy_density_wh_per_kg()` for those cases; power density's W/kg
formula is dimensionally generic and reused as-is (labeled W/cm2 or
W/cm3 as appropriate).

## 5. CV (cyclic voltammetry) capacitance

```
C_s = (∮ I dV) / (2 * m * scan_rate * dV)        (integral form -- non-rectangular / pseudocapacitive CV)
Q_s = (∮ I dV) / (2 * m * scan_rate)              (specific capacity, C/g, battery-type)
C_s = I / (m * scan_rate)                          (direct form -- near-ideal rectangular EDLC CV)
```
Source: the integral form appears (in equivalent forms) in two independent
source PDFs -- "Journal of Energy Chemistry" review (eqn 2) and "Results
in Chemistry" review (eqn 12), and the specific-capacity form as eqn
(10)/(1)-(2) in a MOF/PANI battery-electrode paper and a Solid State
Ionics paper. Computed numerically here via trapezoidal integration of
I dV over one closed CV cycle.

The **direct form** (`C_s = I / (m * scan_rate)`) is derived from the
basic capacitor relation I = C * (dV/dt) = C * scan_rate for a linear
voltage ramp -- i.e. for an ideal capacitor, CV current is constant and
directly proportional to scan rate. This is standard capacitor physics
rather than a formula pinned to one specific paper's equation number; it
is only valid for a near-rectangular CV curve (flat current, no redox
humps) -- use the integral form for anything else. This directly answers
the "integral vs. direct/normal form" distinction requested for this app:
the direct form is the CV analog of the linear GCD formula, and the
integral form is the CV analog of the integral GCD formula, with the same
underlying reasoning (use direct/normal only when the curve is close to
the ideal shape; use integral otherwise). `core/cv_analysis.assess_cv_rectangularity`
provides a practical (not literature-sourced) heuristic score to help
judge which regime applies; always inspect the plotted curve too.

```
b = slope of log(peak current) vs log(scan rate)     (Dunn's method, power-law exponent)
```
b ≈ 1 indicates capacitive behavior; b ≈ 0.5 indicates diffusion-controlled
(battery-like) behavior. Source: "Results in Chemistry" review, eqn 11,
citing Dunn et al.; also eqn (15) "I = a*v^b" in Suganya et al., *J. Energy
Storage* 109 (2025) 115181.

## 5a. Dunn's method: capacitive vs. diffusion-controlled current split

```
I(V) = k1*v + k2*v^0.5                    (total current at potential V, across scan rates v)
I(V)/v^0.5 = k1*v^0.5 + k2                 (rearranged for linear fitting)
```
`k1*v` is the capacitive contribution, `k2*v^0.5` is the diffusion-
controlled (faradaic) contribution, at each potential point. Source:
eqns (16)-(17), Suganya et al., *J. Energy Storage* 109 (2025) 115181,
present verbatim in this project's source PDFs, citing Dunn's method.
`core/dunn_method.capacitive_diffusive_split` fits k1, k2 at each
potential point across a supplied scan-rate series (2+ scan rates, 3+
recommended), then integrates |i_cap| and |i_diff| over the potential
window to report a capacitive/diffusive charge percentage split.

**Important caveat**: a 2023 peer-reviewed critique (Pervez & Stallard,
*"Capacitive and Diffusive Contributions in Supercapacitors and Batteries:
A Critique of b-Value and the v-v^1/2 Model,"* Small, 2023, found via
Consensus search) documents that both the b-value metric and the Dunn
k1*v + k2*v^0.5 model have known flaws: sensitivity to the chosen
scan-rate range, electrode mass loading, and potential for
misinterpretation. This app implements the classic/most commonly reported
Dunn's method because that is what every source paper in this project
uses, but the resulting percentages should be reported as a widely-used,
not a definitively validated, decomposition.

## 5b. Trasatti's method: outer / inner / total capacitance

```
Q*(v) = k1 * v^-0.5 + Q*_outer               (extrapolate v -> infinity for outer capacitance)
1/Q*(v) = k * v^0.5 + 1/Q*_total              (extrapolate v -> 0 for total capacitance)
Q*_total = Q*_inner + Q*_outer
Q*_inner(%) = 100 * Q*_inner / Q*_total
Q*_outer(%) = 100 * Q*_outer / Q*_total
```
Source: eqns (18)-(22), Suganya et al., *J. Energy Storage* 109 (2025)
115181, present verbatim in this project's source PDFs. `Q*(v)` here is
the specific capacitance (F/g) measured at scan rate v via the standard CV
integral formula (not a literal charge in coulombs, despite the "Q*"
notation -- this matches how the source paper's own worked numbers are
reported, in F/g). `core/trasatti_method.trasatti_analysis` implements
this directly; needs 3+ scan rates spanning a wide range (e.g. at least
one order of magnitude) for the extrapolation to be meaningful.

The fit itself is dimensionally agnostic to whatever basis the input
capacitance column is in -- the Rate Study tab's capacitance table lets
you choose gravimetric (F/g) or areal (mF/cm², F/cm²) for the whole
table (see Section 4a), and the outer/total/inner results and plots are
labeled with whichever basis was selected.

## 6. EIS capacitance, ESR, and ionic conductivity

```
C = -1 / (2 * pi * f * Z'')
```
Standard low-frequency EIS capacitance extraction, evaluated at the lowest
measured frequency to approximate near-DC behavior. This is a well-known,
widely-used formula in the field; the source PDFs describe the underlying
impedance formalism (Z = Z_re + j*Z_im, phase angle relationships) but I
do not have one single canonical citation pinned to this exact rearranged
form -- treat it as a standard-but-not-individually-cited formula.

```
sigma = L / (R * A)
```
Ionic conductivity (S/cm) from a two-electrode ion-blocking-cell EIS
measurement, where L is electrolyte thickness (cm), R is the bulk/high-
frequency resistance (ohm, the real-axis Nyquist intercept), and A is
electrode contact area (cm²). Source: present verbatim (as eqn 4 / eqn 10
respectively) in two independent source PDFs in this project (RSC gel-
electrolyte paper; Chemical Engineering Journal gel-electrolyte paper),
both citing the same two-electrode ion-blocking-cell convention.

`core/eis_analysis.high_frequency_intercept_from_nyquist` estimates the
high-frequency real-axis intercept (used for both ESR and the ionic-
conductivity bulk resistance) by restricting the "closest to Z''=0" search
to the highest-frequency fraction of the spectrum. This matters: a
spectrum that traces a full closed semicircle (no low-frequency capacitive
tail) touches the real axis at BOTH ends (Rs at high frequency, Rs+Rct at
low frequency) -- searching the whole spectrum for the global minimum
|Z''| can silently pick the wrong (low-frequency) intercept. This was
caught and fixed during testing of this app using a synthetic Randles-
circuit dataset with a known true Rs.

## 6a. Equivalent circuit fitting

`core/circuit_library.py` implements a generic circuit-TREE engine (every
circuit is a nested `("elem", kind, prefix)` / `("series", [...])` /
`("parallel", [...])` expression) with ~50 preset circuits across 4
categories, all specifically supercapacitor-relevant (see "Library
scope: supercapacitor-only" below), rather than a fixed handful of
named models -- one evaluator
and one CNLS fitter (`core/eis_analysis.fit_equivalent_circuit`, via
`scipy.optimize.least_squares` on the stacked real+imaginary residuals)
works for all of them, which is what lets `auto_fit_equivalent_circuit`
try every circuit against a spectrum and report a ranked table instead of
one hand-picked model. Reported per fit: fitted parameters, approximate
1-sigma standard errors (linearized covariance estimate), reduced
chi-squared, and two independent kinds of explicit warning:

- **Bound-pinning**: a parameter pinned at its search bound (a strong
  sign the model doesn't actually need that element -- see the Warburg
  discussion below).
- **Resistance overestimation**: a fitted resistance (any "R"-kind
  parameter except `Rleak`, which is designed to be large) that's more
  than 20x the measured data's own real-axis span (`max(Z') -
  min(Z')`). This catches a DIFFERENT, more dangerous failure mode than
  bound-pinning: fitting a circuit with no Warburg/diffusion element to
  data whose low-frequency diffusion tail hasn't fully resolved within
  the measured frequency range converges to a genuine (non-boundary)
  local optimum where Rct is pushed far beyond the semicircle's actual
  diameter -- reproduced directly during a real user-reported "Rct is
  overestimated" investigation: Rct = 4447 Ω fitted against a true value
  of 50 Ω (89x), on a realistically truncated frequency sweep (stopping
  at 0.1 Hz rather than true DC), with the fitted value nowhere near any
  search-bound ceiling so the existing bound-pinning check alone did not
  catch it. A genuinely large, well-resolved Rct instead lands close to
  (not many multiples of) the data's real-axis span -- verified
  computationally: ratio ≈1.0 for a correct large-Rct fit vs. ≈32x for
  the reproduced failure case. If you see this warning, try a circuit
  with a Warburg element (the Supercapacitor category) or extend the
  measurement to lower frequency.

Nonlinear least squares can still converge to a local minimum;
single-circuit fits (not the full screening pass) additionally try a
few rescaled starting points (`multistart=True`) and keep the best,
which fixed confirmed local-minimum failures in several circuits during
self-consistency testing (fitting each circuit to its own noise-free
synthetic data and checking the true parameters are recovered).

Base element impedances (all with per-element sourcing in
`circuit_library.py`'s own module docstring):

```
R:   Z = R
C:   Z = 1 / (j*omega*C)
L:   Z = j*omega*L
Q:   Z = 1 / (Y0*(j*omega)^n)                          CPE, n=1 -> ideal capacitor
W:   Z = 1 / (Y0*sqrt(j*omega))                        semi-infinite Warburg
Wo:  Z = coth(B*sqrt(j*omega)) / (Y0*sqrt(j*omega))    bounded Warburg, blocking boundary
Ws:  Z = tanh(B*sqrt(j*omega)) / (Y0*sqrt(j*omega))    bounded Warburg, transmissive boundary
T:   de Levie porous-electrode transmission line (single resistance)
G:   Z = R / sqrt(1 + j*omega*tau)                     Gerischer element
```

### Named supercapacitor-specific circuits ("Supercapacitor (recommended)" category)

**Simplified Randles cell** -- `Z = Rs + (Rct || CPE)` -- one of the most
common supercapacitor EIS models (equivalent to this library's
`randles1_C_none`/`randles1_Q_none`). Sources: Gamry Instruments, "Common
Equivalent Circuit Models" (gamry.com) explicitly names this the
"Simplified Randles Cell" and the starting point for more complex models;
and Nguyen et al., "Modeling supercapacitors with the simplified Randles
circuit: Analyzing electrochemical behavior through cyclic voltammetry and
Galvanostatic charge-discharge," J. Energy Storage / ScienceDirect (2024),
reporting low RMSE fitting real supercapacitor data with exactly this
model.

**Simple leakage model** -- `Z = Rs + (C || R_EPR)` -- described as "the
simplest model" (a capacitance with a series ESR and a parallel leakage/
self-discharge resistance) in C. Shen, S. Xu, Y. Xie, M. Sanghadasa, X.
Wang, L. Lin, "A Review of On-Chip Micro Supercapacitors for Integrated
Self-Powering Systems," J. Microelectromech. Syst., vol. 26, pp. 949-965,
2017 (fig. 2a). Mathematically IDENTICAL to `randles1_C_none` already in
this library (a resistor in parallel with a capacitor, in series with
Rs) -- the "R_EPR" (leakage) vs. "Rct" (charge-transfer) naming is a
difference of PHYSICAL interpretation only, not of the fitted equation, so
no separate circuit entry was added for it (that would just be the same
fit under a second name).

**Bounded-Warburg full-spectrum model** -- `Z = Rs + (Rct || C or Q) +
Wo/Ws` (`supercap_C_Wo`, `supercap_Q_Ws`, etc.) -- the standard extended-
Randles topology for a supercapacitor's full Nyquist spectrum: a
resolvable charge-transfer semicircle in series with a BOUNDED Warburg
appended downstream (not nested inside the semicircle branch). The plain
semi-infinite Warburg "W" is deliberately not offered in this category: it
has a fixed 45-degree phase angle all the way to omega->0 and cannot
reproduce a supercapacitor's near-vertical low-frequency capacitive turn,
so fitting it against full-spectrum data typically drives it toward its
lower search bound (reported explicitly via the bound-pinning warning
above) rather than genuinely fitting. Source: Cruz-Manzo & Greenwood, J.
Electrochem. Soc., vol. 167, 2020, on the frequency transition from
diffusion-like to capacitive response in a blocked/bounded-diffusion
Warburg -- the same low-frequency-divergent behavior as this library's
"Wo" element.

**Two-branch (Zubieta-Bonert) model** -- `Z = Rs + [C1 || Rleak ||
(R2-C2 series)]` (`supercap_twobranch_CC`, `_QQ`, `_CQ`, `_QC`) -- a fast/
immediate branch (C1, the Helmholtz/EDL capacitance) and a slow/delayed
branch (R2 in series with C2, the diffuse-layer capacitance reached only
after charge redistributes through R2), both in parallel with a leakage
resistance Rleak. Source: L. Zubieta and R. Bonert, "Characterization of
double-layer capacitors for power electronics applications," IEEE Trans.
Ind. Appl., vol. 36, no. 1, pp. 199-205, 2000 -- the canonical "two-
branch" supercapacitor model (there, a time-domain model with a
voltage-dependent C1 for pulse-response prediction; this library uses the
linearized small-signal form appropriate for EIS/CNLS fitting).
Corroborated as a standard supercapacitor EIS-circuit entry (described as
exactly this 5-parameter, 2-capacitor/3-resistor structure) by the same
Shen et al. 2017 review cited above (fig. 2e). A leakage resistance is
physically expected to be large (kOhm-MOhm, self-discharge timescales of
hours-to-days) -- `circuit_library.initial_guess_and_bounds` seeds a
parameter literally named `Rleak` from a much larger scale than other
resistors for exactly this reason (confirmed necessary via
self-consistency testing with a physically realistic Rleak >> Rs/R2).

**BioLogic Application Note #34 full-spectrum model** -- `Z = L + Rs +
[C2 || (R2-M2)]` (`supercap_an34_C`, `supercap_an34_Q`, and their `_L`
variants) -- BioLogic's own worked example for fitting a REAL commercial
supercapacitor's full-spectrum EIS data. Source: BioLogic, EC-Lab
Application Note #34, "Supercapacitors Investigations Part II: Time
Constant" (2010, rev. 2019) -- fits a 22 F commercial supercapacitor,
explicitly presented as the circuit needed once a plain series R+C model
stops working above ~1 Hz (the Nyquist trace's phase shifts from
45 degrees toward 90 degrees there); reports R1=31.61 mOhm, L1=98.45 nH,
C2=15.59 mF, R2=4.23 mOhm, Rd2=37.89 mOhm, taud2=1.044 s as the fitted
result for their example cell. Two PARALLEL current paths after Rs+L: a
purely capacitive double-layer path (C2 alone, no series resistance) and
a resistive-then-diffusive Faradaic/charge-transfer path (R2 in series
with the restricted-diffusion element) -- the mirror image of this
library's other semicircle+Warburg entries, which put the bare RESISTOR
(not the bare capacitor) in its own branch. `test_circuit_library.py`
verifies this circuit recovers BioLogic's own reported values exactly
(not just a synthetic parameter draw).

**Cross-validation against EC-Lab's own element library:** EC-Lab's ZFit
module documents 13 element types (EC-Lab software Analysis and Data
Process manual, section 4.3.1.1.4). Directly comparing formulas: EC-Lab's
"M" (restricted linear diffusion, `Z = Rd*coth(sqrt(td*jw))/sqrt(td*jw)`)
is IDENTICAL to this library's "Wo"; EC-Lab's "Wd" (diffusion convection/
Nernst, `Z = Rd*tanh(sqrt(td*jw))/sqrt(td*jw)`) is identical to this
library's "Ws"; EC-Lab's "W", "G", "R", "C", "L", "Q" all match this
library's elements of the same name exactly. This is independent
confirmation (beyond the physical-reasoning and asymptotic-limit checks
already documented above) that this library's Warburg/Gerischer element
conventions are correct.

EC-Lab also documents six further element types that were found during
the same cross-check. All six are still fully implemented in
`core/circuit_library.py` (formulas verified via the same self-
consistency sweep -- fitting each new element/circuit to its own
noise-free synthetic data -- as every other element/circuit; all reduce
EXACTLY to an existing simpler element at their "neutral" exponent
value, checked numerically before finalizing), but only ONE of the six
(`Ma`) is currently used in a registered, user-facing circuit -- see
"Library scope: supercapacitor-only" below for why:
- `La` (modified inductor, `Z = L*(jw)^a`, a=1 -> plain `L`) -- represents
  an unusual/non-ideal inductive high-frequency loop.
- `Winf` (RDE/rotating-disk convective-diffusion element, analytical
  approximation, `Z = Rd*sqrt(g^2+td*jw)/(g+td*jw)`) -- mainly relevant to
  rotating-disk-electrode redox-couple systems rather than porous
  supercapacitor electrodes.
- `Ma` (modified restricted diffusion, `Z = R*coth((t*jw)^(a/2))/
  (t*jw)^(a/2)`, a=1 -> plain `Wo`) -- a CPE-style generalization of this
  library's "Wo" (fixed exponent 1/2 -> variable exponent a/2), directly
  relevant to real porous supercapacitor electrodes with a DISTRIBUTION of
  pore relaxation times rather than one sharp time constant. Used in the
  "Supercapacitor (recommended)" category as `supercap_C_Ma`/
  `supercap_Q_Ma` (and `_L` variants), alongside the existing Wo/Ws-based
  entries -- offering Ma lets a fit discover whether the fixed-exponent
  idealization is adequate for a given electrode, at the cost of one
  extra free parameter.
- `Mg` (Bisquert/anomalous diffusion, `Z = R*coth((t*jw)^(g/2))/
  (t*jw)^(1-g/2)`, g=1 -> same base form as Ma(a=1)/Wo, but the
  ASYMMETRIC exponents diverge from Ma for g!=1) -- originally developed
  for anomalous/fractal transport in mesoporous dye-sensitized-solar-cell
  films, not a supercapacitor-specific model.
- `Ga` (`Z = R/sqrt(1+(jwt)^a)`) and `Gb` (`Z = R/(1+jwt)^(a/2)`) -- two
  DIFFERENT generalizations of this library's Gerischer element "G"
  (both reduce to G at a=1, but diverge from each other and from G for
  a!=1) -- Gerischer-family elements describe mixed ionic/electronic
  conduction with a coupled chemical reaction (battery/SOFC insertion
  electrodes), not supercapacitors.

### Library scope: supercapacitor-only

The circuit library was pruned to remove every category that wasn't
individually sourced for supercapacitors specifically: the combinatorial
"Two time constants" / "Three time constants" categories (a systematic
sweep over cap/Warburg/inductor combinations, useful for generic EIS but
not individually justified for any one system), the "Gerischer (mixed
conduction)" category (battery/SOFC insertion electrodes), and the
"Miscellaneous" grab-bag (single-element diagnostic circuits with no
Rct term -- not physically representable as a supercapacitor electrode
at all). `La`, `Winf`, `Mg`, `Ga`, `Gb` remain fully implemented (see
above) since `Ma` and the underlying element-evaluation engine still
depend on the same code paths, and a user building a fully custom
circuit could still reach them -- they're simply no longer used by any
of the ~71 remaining registered, user-facing circuits.

Four further supercapacitor-specific families were added later, each
verified against its own noise-free synthetic data (same self-
consistency standard as every other entry):
- **Three-branch model** (`supercap_threebranch_{C,Q}[_L]`): the
  Zubieta-Bonert two-branch model (below) extended with a third, slower
  RC branch -- Buller, Karden, Kok & De Doncker, "Modeling the dynamic
  behaviour of supercapacitors using impedance spectroscopy," IEEE Trans.
  Ind. Appl. 38(6), 2002, fit exactly this style of multi-branch RC
  ladder to real supercapacitor EIS data. `Z = Rs + [C1 || Rleak ||
  (R2-C2) || (R3-C3)]`.
- **Charge-transfer + diffusion + leakage** (`supercap_{C,Q}_{Wo,Ws}_leak
  [_L]`): combines this library's existing semicircle+bounded-Warburg
  entries with a leakage/self-discharge resistance in parallel with the
  whole branch, since a real cell does both at once and EIS alone can't
  always tell which single-mechanism model fits better without trying
  both. `Z = Rs + [(Rct||cap)-Wo] || Rleak`.
- **Two-stage + bounded diffusion** (`supercap_twostage_{C,Q}_{Wo,Ws}
  [_L]`): two resolvable interfacial time constants (e.g. a composite
  electrode, or two distinct pore-size populations) followed by a
  bounded-Warburg tail -- reintroduces a two-time-constant shape as an
  explicitly supercapacitor-scoped entry (the old, removed "Two time
  constants" category had no Warburg tail at all). `Z = Rs + (Rct1||cap)
  + (Rct2||cap) + Wo`.

**Not implemented this pass:**
- A de Levie transmission line with an added downstream bounded-Warburg
  tail (`Z = Rs + TLM + Wo`) was built and tested, then DELIBERATELY
  DROPPED: self-consistency testing confirmed the model is mathematically
  valid (starting the optimizer exactly at the true parameters gives a
  perfect fit, cost=0), but this library's standard initial-guess
  strategy could not reliably find that minimum from a generic starting
  point (a concrete reproduction converged to Rs~0 with reduced
  chi-squared ~14). A transmission line already behaves increasingly
  capacitive-like toward low frequency on its own, and a bounded Warburg
  does too below its own characteristic time -- the same "two elements
  producing near-identical low-frequency shapes are too easily confused"
  failure mode already documented for the "Warburg + trailing CPE" case
  below.
- An "EDL capacitance + pseudocapacitance" combined model was investigated
  (captioned in the same Shen et al. 2017 review, fig. 2c) but the exact
  branch topology could not be confirmed from the primary source (IEEE
  Xplore blocked automated access; no accessible mirror had the actual
  circuit diagram) -- rather than guess at a plausible-looking topology,
  this was deliberately left out. Revisit if the primary paper's circuit
  diagram becomes accessible.
- A two-resistance transmission line (separate electronic resistance Re
  along the electrode matrix AND ionic resistance Ri along the pore
  electrolyte, vs. this library's current single-resistance `T` element)
  is described in the same review's transmission-line panel (fig. 2d) as
  a more complete de Levie model -- flagged as a possible future
  enhancement, not implemented (more parameters raises overfitting risk,
  and the added complexity wasn't clearly justified without the source
  paper's full derivation).
- An optional series inductance (attributed to cable inductance,
  producing a high-frequency inductive loop -- Metrohm/Autolab Application
  Note AN-EIS-004) is already available as the `with_l` toggle present on
  essentially every circuit family in this library (not a separate
  fifth-plus model per topology), so no additional work was needed here.

## 7. GCD/CV rate capability and retention

```
current_density (A/g) = I / m
retention (%) = 100 * C_i / C_1
```
Standard normalizations used throughout the rate-capability and cycling-
stability literature: current density is simply current divided by active
mass; retention expresses each capacitance value as a percentage of the
first value in a series (vs. increasing current density, or vs. cycle
number). `core/gcd_analysis.rate_capability_series` and
`capacitance_retention_percent` implement these directly, running
`capacitance_gcd_auto` (with its normal/integral auto-detection) across
each discharge segment in the series.

## 8. DSC water-type classification (free / freezable-bound / non-freezable-bound)

```
W_t   = m_w / m_d
W_f   = A_f / (334 * m_d)
W_nb  = W_t - W_f
W_fb  = W_f * (area_symmetric_peak / total_peak_area)
W_b   = W_nb + W_fb
W_free= W_f - W_fb
```
Source: Yousef et al., "Anti-freezing gel electrolyte...", *Chemical
Engineering Journal* 526 (2025) 171441, Section 2.4 "Water content
analysis", eqns 1-6, present in this project's source PDFs verbatim
(including the 334 J/g heat-of-fusion value used there). Note: 334 J/g is
the value used in that specific paper's equation set; other sources cite
values in the ~333.5-334 J/g range for the heat of fusion of bulk water --
verify which figure is appropriate for your reference method if precision
matters. The heat-of-fusion value is exposed as an adjustable parameter in
the app (default 334 J/g) rather than hard-coded, for exactly this reason.

## 9. DSC enthalpy from raw heat-flow data

```
dH (J/g) = peak_area_J / sample_mass_g
```
Standard mass-normalized DSC transition enthalpy. Peak area is obtained by
integrating heat flow (mW) over time (s) after subtracting a baseline
(this app implements a simple linear baseline between the user-selected
peak start/end points -- more sophisticated curved/sigmoidal baselines
exist in commercial DSC software but there is no single standard algorithm
to cite, so only the linear case is implemented here).

## 9a. Automated symmetric/total peak-area split (for Eq. 4 above)

Section 8's `area_symmetric_peak / total_peak_area` ratio previously
required a manually-measured or manually-entered pair of numbers. It is
now derived automatically from the detected peak's own shape:
`core.dsc_analysis.symmetric_and_total_peak_areas()` mirrors the
baseline-corrected peak about its own apex (peak time) and takes the
pointwise minimum of the peak and its mirror image as the "symmetric"
(bulk-like) component; the ratio of that component's integral to the full
peak's integral is the split used in Eq. 4. A perfectly symmetric peak
gives ratio = 1 (W_fb = W_f); a peak with a one-sided shoulder (a
population of water melting at a different temperature than the sharp/
bulk-like population) gives a smaller ratio.

**This is a general signal-symmetry heuristic, not a literature-sourced
formula** -- it was implemented so the full water-type pipeline (Eqs. 1-6)
can run end-to-end from just m_w/m_d without a separate symmetric/total
peak measurement, but it has not been verified against the specific
deconvolution procedure used in Yousef et al., *Chemical Engineering
Journal* 526 (2025) 171441. Cross-check a few samples by hand if matching
that paper's exact methodology matters for your results.

## 9b. Integration-accuracy self-check

`core.dsc_analysis.check_integration_accuracy()` is an automated sanity
check on a reported peak area (not a literature formula): it (1) compares
the normally-reported trapezoidal integration against Simpson's rule on
the same baseline-corrected window, and (2) nudges the peak start/end row
by up to 3 points in each direction (re-drawing the linear baseline each
time) and reports the resulting spread in area as a percentage. Large
values in either check (>2% method disagreement, >5% boundary
sensitivity) surface as a warning alongside the enthalpy -- neither
replaces visually checking the plotted peak + baseline overlay.

---

## What this app deliberately does NOT do

- It does not implement its own parser for EC-Lab's binary `.mpr` format
  from scratch. There is no public, verifiable specification (BioLogic has
  never published one), and hand-rolling a guess at the byte layout risks
  silently wrong numbers that look identical to correct ones. Instead,
  `.mpr` files are read through the third-party `galvani` package -- a
  maintained, widely-used reverse-engineered parser in the battery/
  electrochemistry Python community, a materially different risk profile
  from an in-house guess but still not an officially verified spec.
  Cross-check a few values against EC-Lab's own display, or re-export as
  `.mpt` (text) or Excel from EC-Lab, before trusting `.mpr`-derived
  numbers for a publication.
- It does not invent a citation for formulas that are standard-but-
  uncited in the source material (EIS capacitance, ESR/IR-drop convention,
  equivalent-circuit element impedances) -- see notes above.
- It does not silently pick a mass-normalization convention (single
  electrode vs. total cell mass) -- the GCD tab requires you to choose a
  cell configuration and states which mass basis is expected.
- It does not silently pick normal vs. integral GCD/CV formula without
  telling you which one was used and why (R²/rectangularity always shown
  or requested).
- It does not present the b-value or Dunn's-method capacitive/diffusive
  split as definitive -- both carry an explicit literature-critique caveat
  (Pervez & Stallard, *Small*, 2023) in the UI and in this document.
- It does not attempt multi-start/global optimization for equivalent-
  circuit fitting -- a single nonlinear-least-squares run from heuristic
  initial guesses can converge to a local minimum; always check the
  fit-overlay plot.
