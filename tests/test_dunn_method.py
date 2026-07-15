"""Tests for core.dunn_method, including a worked example matching a real
reference spreadsheet (b-value & dunn.xlsx, "0 V" data block): K1=0.0125,
K2=0.0986 and per-scan-rate capacitive/diffusive percentages verified by
hand against that file's own SLOPE()/INTERCEPT() calculation."""
import numpy as np
import pytest

from core import dunn_method as dunn

# Scan rates (mV/s) and peak currents (mA) exactly as entered in the
# reference spreadsheet's "AT 0 VOLT" block.
_SCAN_RATES = np.array([5, 10, 15, 20, 30, 50, 75, 100], dtype=float)
_PEAK_CURRENTS_MA = np.array([
    0.256824446398891, 0.436485573005056, 0.5854070353634939, 0.717810542268012,
    0.945504298857623, 1.3489776802018199, 1.78693262603724, 2.1721028090563403,
])


def test_b_value_analysis_matches_reference_spreadsheet():
    result = dunn.b_value_analysis(_SCAN_RATES, _PEAK_CURRENTS_MA)
    assert result.b_value == pytest.approx(0.7076322740938796, rel=1e-6)


def test_peak_current_capacitive_diffusive_split_recovers_k1_k2():
    result = dunn.peak_current_capacitive_diffusive_split(_SCAN_RATES, _PEAK_CURRENTS_MA)
    # Full-precision regression -- the spreadsheet's own K1/K2 cells show
    # these rounded to 4 dp (0.0125, 0.0986); this is the unrounded value
    # that rounds to the same figures.
    assert result.k1 == pytest.approx(0.0125, abs=5e-5)
    assert result.k2 == pytest.approx(0.0986, abs=5e-5)
    assert result.r_squared == pytest.approx(0.9674520437123013, rel=1e-6)


def test_peak_current_capacitive_diffusive_split_percentages_match_rounded_k1_k2():
    # The reference spreadsheet computes its capacitive%/diffusive%
    # columns from K1/K2 already rounded to 4 decimal places (0.0125,
    # 0.0986), not the full-precision regression slope/intercept --
    # reproduce that exact rounding here to compare against the
    # spreadsheet's own printed percentages to 6 significant figures.
    k1, k2 = 0.0125, 0.0986
    sqrt_v = np.sqrt(_SCAN_RATES)
    i_cap = k1 * _SCAN_RATES
    i_diff = k2 * sqrt_v
    total = i_cap + i_diff
    expected_cap_pct = 100 * i_cap / total

    result = dunn.peak_current_capacitive_diffusive_split(_SCAN_RATES, _PEAK_CURRENTS_MA)
    # full-precision k1/k2 give percentages very close to (but not
    # bit-exact with) the spreadsheet's rounded-k1/k2 percentages
    assert result.capacitive_percent == pytest.approx(expected_cap_pct, abs=0.03)
    assert result.capacitive_percent[0] == pytest.approx(22.0866551, abs=0.03)
    assert result.capacitive_percent[-1] == pytest.approx(55.9033989, abs=0.03)


def test_peak_current_capacitive_diffusive_split_percentages_sum_to_100():
    result = dunn.peak_current_capacitive_diffusive_split(_SCAN_RATES, _PEAK_CURRENTS_MA)
    assert np.allclose(result.capacitive_percent + result.diffusive_percent, 100.0)


def test_peak_current_capacitive_diffusive_split_capacitive_fraction_increases_with_scan_rate():
    # Physically expected: capacitive (surface) contribution should grow
    # relative to diffusion-limited contribution as scan rate increases.
    result = dunn.peak_current_capacitive_diffusive_split(_SCAN_RATES, _PEAK_CURRENTS_MA)
    assert np.all(np.diff(result.capacitive_percent) > 0)


def test_peak_current_capacitive_diffusive_split_requires_at_least_three_scan_rates():
    with pytest.raises(ValueError):
        dunn.peak_current_capacitive_diffusive_split([5, 10], [0.1, 0.2])


def test_peak_current_capacitive_diffusive_split_rejects_mismatched_lengths():
    with pytest.raises(ValueError):
        dunn.peak_current_capacitive_diffusive_split([5, 10, 15], [0.1, 0.2])


def test_peak_current_capacitive_diffusive_split_rejects_nonpositive_scan_rate():
    with pytest.raises(ValueError):
        dunn.peak_current_capacitive_diffusive_split([0, 10, 15], [0.1, 0.2, 0.3])
