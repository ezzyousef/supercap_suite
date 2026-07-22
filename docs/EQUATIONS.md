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
  discussion below). One specific case gets DIFFERENT phrasing: a CPE
  exponent `n` pinned at its upper bound (1.0) is not an arbitrary
  numerical ceiling like any other pinned bound -- it's the exact,
  physically well-defined point where a CPE mathematically IS a plain
  capacitor (`Z = 1/(Y0*(jw)^n)` at n=1 reduces exactly to `Z = 1/(jw*Y0)`,
  verified in `test_cpe_reduces_to_ideal_capacitor_when_n_equals_one`).
  Reported directly: the generic "artificial ceiling ... treat with
  caution" wording read as an alarming error even for an essentially
  perfect fit (reduced chi-squared ~1e-17), when the actual situation is
  just that this branch behaves ideally and, if a plain-capacitor sibling
  of the circuit exists in the library, it would fit equally well with
  one fewer parameter. This case is now phrased as a finding ("this
  branch's CPE has settled at n=1, i.e. it behaves as an IDEAL capacitor
  here") rather than a caution, and deliberately does NOT contain the
  substring "pinned at" -- `auto_fit_equivalent_circuit`'s tie-break
  (below) uses that substring to detect genuinely concerning pinned
  bounds, and an n=1 CPE is not one of them.
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

**Auto-detect's pinned-vs-unpinned tie-break**: `auto_fit_equivalent_circuit`'s
initial screening pass (all candidates, `max_nfev=60`, no multistart) is
deliberately fast and therefore noisy -- reliable enough to rank clearly
different circuits, but not to fairly compare two NEAR-DEGENERATE ones
(e.g. two circuits differing only by a redundant CPE-vs-plain-element
choice, which can fit EQUALLY well since a CPE with n=1 is mathematically
identical to a plain capacitor). Reproduced directly: with only a
same-cap-kind two-stage circuit registered, auto-detect could surface a
fit with a CPE exponent pinned at its bound; after the mixed-kind
sibling was added specifically to avoid that (see the two-stage circuit
family above), the fast screening pass could STILL pick the pinned
variant, because its own screening-only chi-squared happened to edge out
the unpinned sibling's screening-only chi-squared even though a properly
converged fit of the unpinned sibling is at least as good. Auto-detect
now re-fits a short list (capped at 8) of the best-screening candidates
with full multistart BEFORE the final comparison, then prefers a
candidate with no bound-pinning warning as long as it's within 5% of the
best refit reduced chi-squared -- so a redundant, pinned circuit is only
ever reported when no equally-good unpinned alternative exists among the
candidates tried.

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
of the ~79 remaining registered, user-facing circuits.

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
- **Two-stage + bounded diffusion** (`supercap_twostage_{c1}{c2}_{Wo,Ws}
  [_L]`, c1/c2 independently C or Q): two resolvable interfacial time
  constants (e.g. a composite electrode, or two distinct pore-size
  populations) followed by a bounded-Warburg tail -- reintroduces a
  two-time-constant shape as an explicitly supercapacitor-scoped entry
  (the old, removed "Two time constants" category had no Warburg tail at
  all). `Z = Rs + (Rct1||cap1) + (Rct2||cap2) + Wo`. The two stages'
  capacitor kind was originally forced to match (both C or both Q); this
  was changed to let each stage vary independently (matching the H2
  two-branch family's `{c1}{c2}` pattern) after a real fitting result
  showed `supercap_twostage_Q_Ws_L`'s `Rct1_cap_n` pinned at its upper
  search bound (1.0) -- the fit was trying to say "this stage is an ideal
  capacitor, not a CPE" but the QQ-only preset had no plain-C option for
  just that one stage. `supercap_twostage_CQ_Ws_L` (stage 1 ideal
  capacitor, stage 2 genuine CPE) resolves that specific case with one
  fewer free parameter.

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

## 6b. Kramers-Kronig validity test

```
Z(omega) = R_inf + sum_k[ R_k / (1 + j*omega*tau_k) ]      (Voigt-chain measurement model)
```
A generic causal/linear/stable circuit -- a chain of parallel RC ("Voigt")
elements with time constants `tau_k` FIXED on a log grid spanning the
measured frequency range (not fitted), which makes the whole fit LINEAR in
`R_inf` and every `R_k` (ordinary least squares, no nonlinear optimizer, no
initial guess). Because this model can already reproduce ANY KK-compliant
spectrum arbitrarily well given enough elements, a large residual between
this fit and the actual data means the MEASUREMENT itself is not
Kramers-Kronig-consistent (instrument drift/non-stationarity during the
scan, nonlinearity, or artifacts) -- not that the wrong equivalent circuit
was picked. Source: B.A. Boukamp, "A Linear Kronig-Kramers Transform Test
for Immittance Data," *J. Electrochem. Soc.* 142(6), 1885-1894 (1995) --
the standard "linear KK test" implemented in this exact form in commercial
tools (NOVA/Metrohm Autolab, ZView/RelaxIS) and open-source packages
(`pyimpspec`, `impedance.py`).

`core/eis_analysis.kramers_kronig_test()` implements Boukamp's original
fixed-element-count version, not the later automatic mu-criterion element-
count selection of Schönleber, Klotz & Ivers-Tiffée, "A Method for
Improving the Robustness of linear Kramers-Kronig Validity Tests,"
*Electrochimica Acta* 131, 20-27 (2014) -- that method adaptively picks the
number of Voigt elements to avoid both under- and over-fitting; this app
defaults to a fixed fraction of the number of data points instead, which is
simpler to implement and verify but can occasionally under- or over-fit at
the extremes (very few points, or a very noisy spectrum). The reported
pass/fail threshold (max residual <= 5% of |Z| at any point) is a
practical interpretation threshold, **not a value from Boukamp's paper** --
commonly-cited informal guidance treats <1% as excellent, ~1-5% as typical
for a real (not ultra-clean) cell, and consistently >5% (especially with a
systematic, not random-looking, trend vs. frequency) as a sign the
measurement should be re-checked. Running the test plots Re(Z)/Im(Z)
residual (% of |Z|) vs. frequency directly, not just the single max/mean
number, since that random-vs-systematic distinction is the actual signal
this test is meant to surface and isn't visible from the numbers alone.
Uses the same inductive-loop-cropped data (Section 6, "Inductive loop
removal") as every other calculation in the EIS tab.

## 6c. Bode plot

```
|Z|   = sqrt(Z'^2 + Z''^2)
phase = atan2(Z'', Z')                (degrees)
```
Standard textbook impedance-magnitude/phase definitions -- the alternative
EIS view to the Nyquist plot that every commercial EIS tool offers
alongside it (NOVA, ZView, EC-Lab, Gamry Echem Analyst), since a Nyquist
plot's Z'/-Z'' axes can visually compress or hide frequency-dependent
behavior (e.g. a phase transition) that's obvious once |Z| and phase are
plotted directly against log(frequency). The EIS tab's "Show as Bode
plot" checkbox re-plots the SAME loaded (and, if enabled, inductive-loop-
cropped) Z data this way instead of as a Nyquist plot -- no new
measurement or fit, purely a different view of the same numbers, drawn
with a secondary (twin) y-axis for phase alongside the primary log|Z|
axis.

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

### 7a. Ragone plot

The GCD rate-study tool's "Show as Ragone plot" checkbox re-axes the same
per-current-density energy/power density values already computed by
`rate_capability_series` (Section 3's formulas) as log(power density) vs.
log(energy density) instead of capacitance vs. current density -- the
standard way a supercapacitor's rate performance is compared across
materials/devices in the literature (e.g. Ragone, "Review of Battery
Systems for Electrically Powered Vehicles," SAE 1968; and, specific to
EC-Lab's own equivalent tool, BioLogic's "Constant Power Discharge"
application notes). No new formula -- purely a different plot of values
already reported in the rate-capability table.

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

## 10. DRT (Distribution of Relaxation Times)

```
Z(f) = R_inf + integral[ gamma(ln tau) / (1 + j*2*pi*f*tau) dlntau ]
```
A non-parametric alternative/complement to equivalent-circuit fitting
(Section 6a): instead of assuming one circuit topology up front, DRT
deconvolves a continuous distribution gamma(ln tau) of relaxation-time
"weights" directly from the measured spectrum. Every parallel RC-like
element in an equivalent circuit shows up as one peak in gamma(ln tau) at
tau = R*C -- informally, a DRT plot is "what an equivalent-circuit fit
would look like without committing to a specific circuit first."

`core/drt_analysis.compute_drt()` discretizes gamma(ln tau) with
piecewise-linear ("hat") basis functions, one centered at each measured
frequency's tau_n = 1/(2*pi*f_n), and solves the resulting Tikhonov-
regularized least-squares problem via non-negative least squares
(`scipy.optimize.nnls`) -- both R_inf and every gamma weight are
constrained non-negative, which is physically required for gamma and
happens to also hold for R_inf, so this enforces the non-negativity
DRTtools implements via a general bounded quadratic program using only
a standard-library-adjacent solver. Source: T.H. Wan, M. Saccoccio, C.
Chen, F. Ciucci, "Influence of the Discretization Methods on the
Distribution of Relaxation Times Deconvolution: Implementing Radial
Basis Functions with DRTtools," *Electrochimica Acta* 184 (2015)
483-499 -- the paper behind DRTtools, the standard open-source reference
implementation in this field (this app implements the paper's PWL case,
not its RBF extension; the paper's own abstract states the two give
"comparable" results at a normal, complete data-collection range, which
is the intended use case here). The design-matrix integrals (the paper's
eq. 30-33) are evaluated by numerical quadrature (`scipy.integrate.quad`)
rather than a closed form, and regularization uses a discrete SECOND-
difference penalty on gamma (a standard, commonly-offered alternative
regularization order to the paper's first-derivative penalty, chosen
here because it avoids needing the closed-form derivative of the PWL
basis function).

**Collocation grid extension (edge-artifact fix)**: basis functions
compactly supported ONLY within [tau_min, tau_max] (the plain choice)
force gamma to exactly zero at those edges. If the true underlying
process's relaxation extends beyond what was actually measured -- very
common for a supercapacitor's near-vertical low-frequency capacitive
tail, which implies relaxation times longer than the measurement
covered -- the deconvolution has nowhere to put that "missing" weight
except a sharp, physically implausible spike jammed into the very last
edge collocation point (reproduced from a real reported case: a ~17%
model residual and a spike at the largest tau shown). `compute_drt()`
extends the collocation grid a few points past each measured boundary,
at the same log-spacing as the measured grid (`n_extra = max(5, N/5)`
points per side) -- the same idea Wan et al. 2015 sec. 2.1 highlight as
an advantage of RBF discretization's naturally infinite support, applied
here to PWL via extra collocation points instead of switching basis
families. This does not "fix" the underlying physical limitation (a
bounded DRT model still cannot represent a truly diverging low-frequency
impedance -- see the frequency-region caveat below), but it lets that
mass spread out naturally across the extended grid instead of being
clipped into one artificial spike, which both reduces the residual
substantially and makes the still-real underlying issue visually
identifiable (a gradually rising tail) rather than a misleading sharp
artifact. `DRTResult.within_measured_range` (a bool array matching
`tau_s`/`gamma`) flags which collocation points are data-constrained vs.
extrapolated; peaks in the extrapolated region are marked
`DRTPeak.within_measured_range=False` and labeled "EXTRAPOLATED" in the
DRT tab's results text, and shaded on the plot. If gamma is still rising
at the largest computed tau even after this extension, `compute_drt()`
adds an explicit warning (`DRTResult.warnings`) rather than let it pass
as an unremarkable-looking rising tail -- see the frequency-region
caveat below for why this specifically happens with blocking-electrode
systems.

**Self-consistency verification**: no closed-form DRT exists for most
circuits, but one does for a single ZARC element (a resistor in parallel
with a CPE) -- `core.drt_analysis.analytical_zarc_drt()` implements the
standard ZARC/Cole-Cole DRT closed form reproduced across the DRT
literature (e.g. Schichlein et al., *J. Appl. Electrochem.* 32 (2002)
875; Boukamp, "Fourier Transform Distribution Function of Relaxation
Times," *Solid State Ionics*). This project's own reference PDF (Py,
Maradesa & Ciucci, *Electrochimica Acta* 479 (2024) 143741, eq. 10)
states an equivalent result, but its printed equation could not be
reliably transcribed from the extracted PDF text (the source's two-
column layout interleaved characters from adjacent columns across the
equation during OCR/text extraction) -- rather than risk shipping a
garbled formula, it was independently verified by forward-integration
(numerically computing `integral[gamma(ln tau)/(1+j*2*pi*f*tau)
dlntau]` and confirming it reproduces the true ZARC impedance to 5
decimal places across a wide frequency range; see
`tests/test_drt_analysis.py`). `compute_drt()` itself is verified the
same way this app verifies every other fitting routine: fit a synthetic
ZARC spectrum with a known Rs/Rct/tau_zarc/phi and confirm R_inf, the
peak position, and the peak "area" (integral of gamma d(ln tau) over a
resolved peak, which should equal Rct -- a standard DRT property) are
all recovered within a few percent.

**Regularization parameter lambda** is a practical default (1e-3),
exposed as an adjustable field in the DRT tab, NOT automatically
optimized against the loaded data -- the source paper notes optimal-
lambda selection (e.g. via re-im cross-validation) is itself a
nontrivial, actively-discussed choice; always check whether a peak
survives across a reasonable lambda range before trusting it.

**Frequency-region peak interpretation** (`core.drt_analysis.
classify_region()` / `FREQUENCY_REGIONS`): every detected peak is
automatically labeled with a practical, literature-informed
interpretation -- high frequency (short tau) typically maps to
charge-transfer/interfacial kinetics and double-layer charging, mid
frequency to distributed/combined charge-transfer + double-layer or
contact/grain-boundary effects (broader peaks = more distributed
process), and low frequency to diffusion/mass-transport-limited
response. These are ORDER-OF-MAGNITUDE bands from the DRT peak-
interpretation literature, **not universal physical constants** -- no
single tau cutoff is correct for every electrode/electrolyte system;
always cross-check a labeled peak against the specific chemistry and
the raw Nyquist/Bode shape. Source: C. Plank et al., "A review of the
distribution of relaxation times method for the analysis of impedance
spectra," *J. Power Sources* 594 (2024) 233845 ("Interpretation of
peaks" section). The low-frequency band's caveat about an artificial
increasing series of peaks mimicking a CPE is specific to
BLOCKING-electrode systems (i.e. exactly supercapacitors and
batteries): B. Py, A. Maradesa, F. Ciucci, *Electrochimica Acta* 479
(2024) 143741, documents that the classical DRT model's impedance is
mathematically forced to a FINITE value as f->0, which cannot
represent a real blocking electrode's diverging low-frequency
impedance -- this is exactly why that paper introduces the distribution
of capacitive times (DCT), implemented as a second method (Section 10a)
for exactly this case.

## 10a. DCT (Distribution of Capacitive Times)

```
Y(f) = j*2*pi*f*C0 + G0 + integral[ gamma_DCT(ln tau) / (1 + j*2*pi*f*tau) dlntau ]
```
The ADMITTANCE-domain counterpart to DRT, added specifically for the
blocking-electrode low-frequency limitation documented above. DRT's model
impedance is mathematically forced to a FINITE value as f->0 -- unable to
represent a real blocking electrode's diverging low-frequency impedance
(the near-vertical Nyquist tail), which shows up as gamma piling into an
ever-increasing series of peaks toward the largest computed relaxation
time rather than resolving one genuine feature. DCT fits the admittance
Y(f) = 1/Z(f) instead, whose model tends to a FINITE value (not a
divergence) as f->0 for exactly this case -- a real blocking electrode's
Y simply approaches zero there, which G0 and the DCT weights can
represent directly.

`core.drt_analysis.compute_dct()` reuses the exact same piecewise-linear
discretization, collocation-grid extension, Tikhonov regularization, and
non-negative-least-squares machinery as `compute_drt()` (see Section 10
above for the full discretization discussion -- it applies identically
here), just fit against Y instead of Z, with an added free parameter C0
(the instantaneous/high-frequency capacitance, the DCT counterpart to
DRT's R_inf) alongside G0 (the zero-frequency conductance). Source:
B. Py, A. Maradesa, F. Ciucci, *Electrochimica Acta* 479 (2024) 143741,
eq. 2-3 for the admittance model.

**Self-consistency verification**: the YARC element (eq. 21 in the
source paper) -- the admittance-domain analog of a ZARC, `Y(f) = G_inf +
Gct/(1+(j*2*pi*f*tau_YARC)^phi)` -- has a DCT closed form that the source
paper states is IDENTICAL in functional form to the ZARC's DRT closed
form (Section 10 above), with Gct substituted for Rct. `compute_dct()`
is verified against this directly: forward-compute Y_YARC(f) from known
G_inf/Gct/tau_YARC/phi, convert to Z=1/Y (matching what a real
measurement provides), run `compute_dct()`, and confirm G0, the peak
position, and the peak "area" all recover the true YARC parameters (see
`tests/test_drt_analysis.py`).

**DCT is not a guaranteed fix for every blocking-electrode spectrum.**
It fits well when the underlying admittance genuinely has a Maxwell-type
structure (a parallel combination of resistor-capacitor-pairs-in-series
branches, per the source paper's own circuit-mapping discussion) -- the
YARC case above is exactly this. A spectrum built as a pure SERIES
combination (e.g. Rs + a ZARC + a series capacitor -- a Voigt-type
topology, exactly what DRT itself is suited for) is not automatically
well-represented by DCT's admittance model either, even though it also
technically has a diverging low-frequency impedance. This was found
directly while validating the fix: DCT gave a ~76% residual on such a
spectrum, confirmed as a genuine topology mismatch (not a numerical bug)
via the same self-consistency standard used everywhere else in this
app -- `tests/test_drt_analysis.py` documents this case explicitly so a
future change doesn't "fix" it by silently forcing a small residual
regardless of whether the data supports it. **Always check the reported
residual for BOTH methods** before trusting either one; a large residual
on both is itself useful information (the raw Nyquist/Bode shape or the
Kramers-Kronig test, Section 6b, may be more informative for that
spectrum than either decomposition).

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
