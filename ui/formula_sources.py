"""Formula/citation text shown by the "ⓘ Formula & source" buttons.

Every string here is a condensed version of the corresponding section in
docs/EQUATIONS.md -- the one-click traceability this app's design brief
requires ("every result must show its source"). Keep these in sync with
docs/EQUATIONS.md if a formula or citation changes there.
"""

GCD_CAPACITANCE = """
<b>Normal (linear) form</b> -- used when the discharge curve is (near-)linear:<br>
<code>C_s = (I &times; &Delta;t) / (m &times; &Delta;V)</code><br>
Source: standard EDLC capacitance expression, Zhang et al.,
<i>Adv. Energy Mater.</i> 2015, 5, 1401401, eqns 4-9.<br><br>
<b>Integral form</b> -- used when the discharge curve is non-linear
(pseudocapacitive / battery-type):<br>
<code>C_s = (2 &times; I &times; &int;V dt) / (m &times; &Delta;V&sup2;)</code><br>
Source: hydrogel-electrolyte supercapacitor paper (citing Mathis et al.),
stated as required "because it accurately reflects the complex charge
storage mechanisms ... thereby minimizing miscalculations."<br><br>
<b>Which one was used</b>: decided by fitting V=a&middot;t+b to the
discharge segment and checking R&sup2; against your threshold (default
0.98) -- shown in the results above. The 0.98 cutoff is a practical
heuristic, not a literature constant.
"""

GCD_ESR = """
<code>ESR = IR_drop / I</code><br>
A simple two-point IR-drop estimate, not a fitted steady-state
extrapolation. Some labs instead use IR_drop / (2I) for a full-cycle
convention -- state which convention you used when reporting ESR.
"""

GCD_ENERGY_POWER = """
<code>E (Wh/kg) = C_s &times; &Delta;V&sup2; / 7.2</code><br>
<code>P (W/kg) = E &times; 3600 / &Delta;t</code><br>
Derived from E (J/g) = 0.5 &times; C_s &times; &Delta;V&sup2;. Cross-checked
against two independent source papers reporting numerically equivalent
forms, and the underlying derivation in Zhang et al., <i>Adv. Energy
Mater.</i> 2015, eqns 26-28.
"""

TWO_THREE_ELECTRODE = """
<code>C_spec,electrode = 4 &times; C_spec,cell</code> (symmetric 2-electrode cell)<br>
<code>C_spec,cell(2e) = C_spec,electrode(3e) / 4</code> (inverse estimate)<br>
Source: Zhang et al., <i>Adv. Energy Mater.</i> 2015, 5, 1401401, eqns
10-13 -- valid ONLY for a symmetric cell with equal mass and equal
capacitance on both electrodes. <b>Not valid for asymmetric/hybrid
cells.</b> The source paper warns this factor "would be meaningless and
would lead to totally wrong capacitance results" if applied to a system
with unequal potential splitting between electrodes.
"""

CV_CAPACITANCE = """
<b>Direct/rectangular form</b> -- near-ideal EDLC CV curve:<br>
<code>C_s = I / (m &times; &nu;)</code><br>
Derived from I = C&middot;(dV/dt) = C&middot;&nu; for a linear voltage ramp
-- standard capacitor physics, valid only for a near-rectangular curve.<br><br>
<b>Integral form</b> -- non-rectangular / pseudocapacitive curve:<br>
<code>C_s = (&oint;I dV) / (2 &times; m &times; &nu; &times; &Delta;V)</code><br>
Source: <i>Journal of Energy Chemistry</i> review (eqn 2) and <i>Results
in Chemistry</i> review (eqn 12). Computed here via trapezoidal
integration of I&middot;dV over one closed CV cycle.<br><br>
<b>Specific capacity</b> (battery-type, C/g, no /&Delta;V term):<br>
<code>Q_s = (&oint;I dV) / (2 &times; m &times; &nu;)</code>
"""

CV_PEAK_SEPARATION = """
<code>&Delta;Ep = E_pa &minus; E_pc</code><br>
Anodic peak potential minus cathodic peak potential, from the single
largest current maximum/minimum in the cycle. Redox-reversibility
indicator: a fully reversible one-electron couple gives &Delta;Ep &asymp;
59 mV (room temperature), independent of scan rate (standard Randles-
Sevcik/Nicholson electrochemistry). A larger or scan-rate-dependent
&Delta;Ep indicates quasi-reversible or irreversible electron-transfer
kinetics -- this app reports the numbers only; the reversibility judgment
is a domain interpretation left to you. Not meaningful for a curve with
no resolvable redox peaks (e.g. an ideal EDLC).
"""

RANDLES_SEVCIK = """
<code>I_p = 0.4463 &times; n &times; F &times; A &times; C &times;
&radic;(n &times; F &times; v &times; D / (R &times; T))</code><br>
Source: standard Randles-Sevcik equation (Bard &amp; Faulkner eqn 6.2.19),
verified against an independent source before implementing. Fit as the
slope of peak current vs. &radic;(scan rate) across 3+ scan rates,
rearranged for D. This temperature-EXPLICIT form is used (not the common
298 K-only simplified constant, 2.69&times;10&#8309;) so your entered
temperature is actually honored. Valid only for a REVERSIBLE electron
transfer at a diffusion-limited redox peak -- not applicable to an ideal
EDLC (no faradaic peak) or to quasi-reversible/irreversible kinetics.
"""

BVALUE = """
<code>b = slope of log(peak current) vs log(scan rate)</code><br>
b &asymp; 1 &rarr; capacitive; b &asymp; 0.5 &rarr; diffusion-controlled
(battery-like). Source: <i>Results in Chemistry</i> review eqn 11 (citing
Dunn et al.); Suganya et al., <i>J. Energy Storage</i> 109 (2025) 115181,
eqn 15.<br><br>
<b>Caveat</b>: Pervez &amp; Stallard, <i>Small</i>, 2023 document known
flaws in this metric -- sensitivity to scan-rate range and electrode mass
loading. Treat results as indicative, not a definitive mechanistic proof.
"""

DUNN_CAPACITIVE_DIFFUSIVE = """
<code>i(v) = k1&middot;v + k2&middot;v&#8304;&#8901;&#8309;</code> (Dunn's method)<br>
<code>i(v)/v&#8304;&#8901;&#8309; = k1&middot;v&#8304;&#8901;&#8309; + k2</code>
-- linear fit of i/v&#8304;&#8901;&#8309; vs. v&#8304;&#8901;&#8309;
across all scan rates at once (ONE k1, k2 pair from the whole peak-
current-vs-scan-rate series), giving the capacitive (k1&middot;v) and
diffusive (k2&middot;v&#8304;&#8901;&#8309;) contribution to each scan
rate's current as a percentage of the model's own reconstructed total.
Source: Suganya et al., <i>J. Energy Storage</i> 109 (2025) 115181, eqns
16-17, citing Dunn's method. This is the simpler "peak current only"
variant (a single k1/k2 fit across scan rates) -- not the full-CV-curve
variant (k1(V)/k2(V) fit separately at every potential point across a
whole voltammogram), which needs complete CV curves at every scan rate
rather than just a peak-current table.<br><br>
<b>Caveat</b>: Pervez &amp; Stallard, <i>Small</i>, 2023 document known
flaws in this model -- sensitivity to scan-rate range and electrode mass
loading, and note the capacitive/diffusive split is model-dependent, not
a direct measurement. Treat results as indicative, not definitive.
"""

TRASATTI = """
<code>Q*(v) = k1&middot;v&#8315;&#8304;&#8901;&#8309; + Q*_outer</code>
(extrapolate v &rarr; &infin;)<br>
<code>1/Q*(v) = k&middot;v&#8304;&#8901;&#8309; + 1/Q*_total</code>
(extrapolate v &rarr; 0)<br>
<code>Q*_inner = Q*_total &minus; Q*_outer</code><br>
Source: Suganya et al., <i>J. Energy Storage</i> 109 (2025) 115181, eqns
18-22. Needs 3+ scan rates spanning at least one order of magnitude for a
meaningful extrapolation.
"""

EIS_CAPACITANCE = """
<code>C = &minus;1 / (2&pi;f&middot;Z'')</code><br>
Standard low-frequency EIS capacitance extraction, evaluated at the
lowest measured frequency to approximate near-DC behavior. Well-known in
the field, but this app does not have one single canonical citation
pinned to this exact rearranged form -- treat it as standard-but-not-
individually-cited.
"""

IONIC_CONDUCTIVITY = """
<code>&sigma; = L / (R &times; A)</code><br>
Two-electrode ion-blocking-cell convention: L = electrolyte thickness
(cm), R = bulk/high-frequency resistance (real-axis Nyquist intercept,
&Omega;), A = electrode contact area (cm&sup2;). Source: present verbatim
in two independent source papers (RSC gel-electrolyte paper; <i>Chemical
Engineering Journal</i> gel-electrolyte paper).
"""

EIS_CIRCUIT_FIT = """
<code>Z_CPE = 1 / (Q&middot;(j&omega;)&#8319;)</code> (n=1 &rarr; ideal capacitor)<br>
<code>Z_Warburg = W / &radic;(j&omega;)</code><br>
<b>Randles</b>: Z = Rs + (Rct &#8741; Z_CPE) &nbsp; [4 params]<br>
<b>Randles+Warburg</b>: Z = Rs + ((Rct + Z_Warburg) &#8741; Z_CPE) &nbsp; [5 params]<br>
Standard textbook equivalent-circuit impedance formulas, fit via
<code>scipy.optimize.least_squares</code> on stacked real+imaginary
residuals. Nonlinear least squares can converge to a local minimum on
noisy/sparse spectra -- always inspect the fit-overlay plot, not just
reduced &chi;&sup2;.
"""

DRT_ANALYSIS = """
<code>Z(f) = R_inf + &int; &gamma;(ln&tau;) / (1 + j2&pi;f&tau;) dln&tau;</code><br>
Distribution of Relaxation Times: a non-parametric alternative to
equivalent-circuit fitting -- deconvolves a continuous distribution
&gamma;(ln&tau;) directly from the spectrum instead of assuming one
circuit topology up front; every parallel RC-like process shows up as
one peak. Discretized with piecewise-linear basis functions and solved
via Tikhonov-regularized non-negative least squares. Source: T.H. Wan,
M. Saccoccio, C. Chen, F. Ciucci, <i>Electrochimica Acta</i> 184 (2015)
483-499 (the paper behind DRTtools, the standard open-source reference
implementation). Peak frequency-region interpretations draw on C. Plank
et al., <i>J. Power Sources</i> 594 (2024) 233845, and note a specific
caveat for blocking-electrode systems (supercapacitors, batteries) from
B. Py, A. Maradesa, F. Ciucci, <i>Electrochimica Acta</i> 479 (2024)
143741. The regularization strength &lambda; is a practical default, not
automatically optimized against this data -- try a few values.
"""

DCT_ANALYSIS = """
<code>Y(f) = j2&pi;fC0 + G0 + &int; &gamma;(ln&tau;) / (1 + j2&pi;f&tau;) dln&tau;</code><br>
Distribution of Capacitive Times: the ADMITTANCE-domain counterpart to
DRT, purpose-built for BLOCKING-electrode systems (supercapacitors,
batteries). DRT's model impedance is mathematically forced to a FINITE
value as f&rarr;0, which cannot represent a real blocking electrode's
diverging low-frequency impedance (the near-vertical Nyquist tail); DCT
fits the admittance Y(f)=1/Z(f) instead, whose model tends to a finite
value as f&rarr;0 for exactly this case. Uses the same piecewise-linear/
extended-grid/Tikhonov/NNLS machinery as DRT, applied to Y instead of Z,
with an added free parameter C0 (the instantaneous/high-frequency
capacitance) alongside G0 (the DCT counterpart to DRT's R_inf). Source:
B. Py, A. Maradesa, F. Ciucci, <i>Electrochimica Acta</i> 479 (2024)
143741, eq. 2-3. DCT is NOT a guaranteed fix for every blocking-electrode
spectrum -- it fits well when the underlying admittance has a Maxwell-
type (parallel-branches) structure, verified here against the YARC
element's closed-form admittance, but not every real spectrum does.
Always check the reported residual before trusting either DRT or DCT.
"""

KRAMERS_KRONIG = """
<code>Z(&omega;) = R_inf + &sum;_k [ R_k / (1 + j&omega;&tau;_k) ]</code><br>
Linear Kramers-Kronig validity test: a generic Voigt-element chain with
&tau;_k fixed on a log grid (so the fit is ordinary least squares, no
nonlinear optimizer), used to check whether a spectrum is even physically
fittable by ANY causal/linear/stable circuit before trusting a specific
one. Source: B.A. Boukamp, <i>J. Electrochem. Soc.</i> 142(6), 1885-1894
(1995) -- the standard "linear KK test", also used in NOVA, ZView/RelaxIS.
The pass/fail residual threshold (5%) is a practical heuristic, not from
the source paper -- always also check whether the residual-vs-frequency
pattern looks random or systematic.
"""

RATE_CAPABILITY = """
<code>current_density (A/g) = I / m</code><br>
<code>retention (%) = 100 &times; C_i / C_1</code><br>
Standard normalizations from the rate-capability/cycling-stability
literature. Each discharge segment is analyzed with the same normal/
integral auto-detection as the main GCD tab.
"""

CYCLING_STABILITY = """
<code>retention (%) = 100 &times; C_i / C_1</code> -- each cycle's
capacitance as a percentage of the FIRST successfully-analyzed cycle in
the series. Standard normalization used throughout the cycling-stability
literature.<br><br>
<code>CE (%) = 100 &times; discharge_time / charge_time</code><br>
Coulombic efficiency, in its simplified time-ratio form -- valid ONLY
when the charge and discharge current MAGNITUDES are equal (the standard
constant-current cycling protocol this tab assumes, using one entered
current value for both legs). If your protocol uses different charge/
discharge currents, this simplified form is not applicable; the
literature-standard full form is
<code>CE (%) = 100 &times; Q_discharge / Q_charge</code> (charge
extracted &divide; charge injected, from integrating current over each
leg individually), which needs per-leg current data this tab does not
currently take as input.<br><br>
Cycles are auto-segmented from one continuous multi-cycle trace using the
same shape-based charge/discharge detector as the main GCD tab's
"Auto-detect charge/discharge segments" feature (peaks/troughs in V(t),
not a literature-sourced algorithm -- always check the plotted trace).
"""

DSC_ENTHALPY = """
<code>&Delta;H (J/g) = peak_area (J) / sample_mass (g)</code><br>
Standard mass-normalized DSC transition enthalpy. Peak area is the
integral of heat flow (mW) over time (s) after subtracting a linear
baseline between the user-selected peak start/end points -- curved/
sigmoidal baselines are not implemented (no single standard algorithm to
cite for them).
"""

DSC_WATER_TYPE = """
<code>W_t = m_w / m_d</code> (total water content, Eq.1)<br>
<code>W_f = A_f / (333.55 &times; m_d)</code> (freezable water, Eq.2)<br>
<code>W_nb = W_t &minus; W_f</code> (non-freezable bound water, Eq.3)<br>
<code>W_fb = W_f &times; (area_symmetric / area_total)</code> (freezable bound water, Eq.4)<br>
<code>W_b = W_nb + W_fb</code> (total bound water, Eq.5)<br>
<code>W_free = W_f &minus; W_fb</code> (free water, Eq.6)<br>
Source: Yousef et al., "Anti-freezing gel electrolyte...", <i>Chemical
Engineering Journal</i> 526 (2025) 171441, Section 2.4, eqns 1-6.
333.55 J/g (the "Pure water Enthalpy" reference value in the validated
reference spreadsheet, "Calculations of water (version 1).xlsx") is the
default heat of fusion of water used here (literature range: ~333.5-334
J/g) -- adjustable in this tab if your reference method uses a different
value.<br><br>
Each water population can also be expressed as a percentage of TOTAL
water content (W_t): freezable, non-freezable-bound, freezable-bound,
and free water -- exactly matching that reference spreadsheet's
"Freezable water %" / "Non-Freezable bound water" / "Freezable bound
water %" / "Free water %" columns, verified to 5-6 significant figures
against 3 real sample rows.
"""

DSC_SYMMETRIC_TOTAL_SPLIT = """
Automated symmetric/total peak-area split (for Eq. 4's
area_symmetric / area_total ratio, so it doesn't require a separately
measured or manually-entered value):<br>
The baseline-corrected peak is mirrored about its own apex (peak time);
the pointwise minimum of the peak and its mirror image is the
"symmetric" (bulk-like) component, and its integral divided by the full
peak's integral gives the split. A perfectly symmetric peak has
symmetric_area = total_area (ratio 1, W_fb = W_f); a peak with a broader
one-sided shoulder (physically: water melting at a different temperature
than the sharp/bulk-like population) has a smaller ratio.<br>
<b>Caveat:</b> this is a general signal-symmetry heuristic implemented so
the full water-type pipeline can run without manual peak-area entry --
it is <i>not</i> verified against the specific deconvolution procedure in
Yousef et al., <i>Chemical Engineering Journal</i> 526 (2025) 171441.
Cross-check a few samples by hand if you need to match that paper's exact
methodology.
"""

DSC_INTEGRATION_ACCURACY = """
Integration-accuracy self-check (not a literature formula -- an automated
sanity check on the reported peak area):<br>
<b>Method comparison:</b> the same baseline-corrected window is
re-integrated with Simpson's rule and compared to the trapezoidal result
normally reported; a large disagreement usually means the peak region is
coarsely or unevenly sampled.<br>
<b>Boundary sensitivity:</b> the start/end row is nudged by up to 3
points in each direction (redrawing the linear baseline each time), and
the resulting spread in area is reported as a percentage -- a peak whose
area swings widely for a small change in where "start"/"end" was clicked
has a poorly-anchored baseline (the flanking region isn't flat), and its
absolute area should be treated as approximate.<br>
Neither check replaces looking at the plotted peak + baseline overlay
before trusting a reported enthalpy.
"""
