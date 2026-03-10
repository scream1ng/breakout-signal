"""
rsm.py — RS Momentum calculation
  f_calc_final_rating(score)  : raw ratio -> 1-99 IBD-style rating
  calc_rsm_series(s, b)       : rolling RSM for every bar, no look-ahead
"""

import numpy as np


def f_calc_final_rating(score: float) -> float:
    score = float(score)
    if score >= 195.93: return 99.0
    if score <= 24.86:  return 1.0
    if score >= 117.11: up, dn, rUp, rDn, w = 195.93, 117.11, 98, 90, 0.33
    elif score >= 99.04: up, dn, rUp, rDn, w = 117.11, 99.04, 89, 70, 2.1
    elif score >= 91.66: up, dn, rUp, rDn, w = 99.04,  91.66, 69, 50, 0
    elif score >= 80.96: up, dn, rUp, rDn, w = 91.66,  80.96, 49, 30, 0
    elif score >= 53.64: up, dn, rUp, rDn, w = 80.96,  53.64, 29, 10, 0
    else:                up, dn, rUp, rDn, w = 53.64,  24.86,  9,  2, 0
    sum_val = score + (score - dn) * w
    if sum_val > (up - 1): sum_val = up - 1
    k1 = dn / rDn
    k2 = (up - 1) / rUp
    k3 = (k1 - k2) / (up - 1 - dn)
    return float(np.clip(score / (k1 - k3 * (score - dn)), rDn, rUp))


def calc_rsm_series(s_arr: np.ndarray, b_arr: np.ndarray) -> np.ndarray:
    """Rolling RS Momentum at every bar. No look-ahead bias — uses only past 21 bars."""
    n   = len(s_arr)
    rsm = np.full(n, np.nan)
    for i in range(22, n):
        s_now = s_arr[i];  s_22 = s_arr[i - 21]
        b_now = b_arr[i];  b_22 = b_arr[i - 21]
        if 0 in (s_22, b_22, b_now) or any(np.isnan([s_now, s_22, b_now, b_22])):
            continue
        rsm[i] = f_calc_final_rating((s_now / s_22) / (b_now / b_22) * 100)
    return rsm