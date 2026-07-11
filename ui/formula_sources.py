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

RATE_CAPABILITY = """
<code>current_density (A/g) = I / m</code><br>
<code>retention (%) = 100 &times; C_i / C_1</code><br>
Standard normalizations from the rate-capability/cycling-stability
literature. Each discharge segment is analyzed with the same normal/
integral auto-detection as the main GCD tab.
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
<code>W_f = A_f / (334 &times; m_d)</code> (freezable water, Eq.2)<br>
<code>W_nb = W_t &minus; W_f</code> (non-freezable bound water, Eq.3)<br>
<code>W_fb = W_f &times; (area_symmetric / area_total)</code> (freezable bound water, Eq.4)<br>
<code>W_b = W_nb + W_fb</code> (total bound water, Eq.5)<br>
<code>W_free = W_f &minus; W_fb</code> (free water, Eq.6)<br>
Source: Yousef et al., "Anti-freezing gel electrolyte...", <i>Chemical
Engineering Journal</i> 526 (2025) 171441, Section 2.4, eqns 1-6. 334 J/g
is the heat of fusion of water used in that paper's equation set
(literature range: ~333.5-334 J/g) -- adjustable in this tab if your
reference method uses a different value.
"""
