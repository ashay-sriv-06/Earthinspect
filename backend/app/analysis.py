"""Deterministic numerical analysis, independent of any LLM.

Trend model (monthly): y_t = b0 + b1 * years_elapsed_t + sum_m gamma_m * month_m + e_t
  - OLS point estimate; HAC (Newey-West, Bartlett kernel) covariance via statsmodels
    `fit(cov_type="HAC", cov_kwds={"maxlags": 12})`; sensitivity reported at maxlags=24.
  - Product rule (not a universal scientific threshold): inferential path needs >= 120 consecutive
    valid monthly observations covering the full requested window without gaps.
  - Missing months are never zero-filled, interpolated or compressed.
"""
from __future__ import annotations

import hashlib
import math

import numpy as np
import statsmodels.api as sm
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.stattools import durbin_watson

from . import db
from .config import ASSOC_METHOD_VERSION, TREND_METHOD_VERSION
from .errors import ApiError

MIN_INFERENTIAL_MONTHS = 120
HAC_LAGS = 12
HAC_SENSITIVITY_LAGS = 24


def _month_index(date: str) -> int:
    y, m = date.split("-")
    return int(y) * 12 + int(m) - 1


def _idx_to_date(i: int) -> str:
    return f"{i // 12}-{i % 12 + 1:02d}"


def window_rows(rows: list[dict], start: str, end: str) -> list[dict]:
    """Rows on the full calendar between start and end inclusive; absent months become value=None."""
    a, b = _month_index(start), _month_index(end)
    if a > b:
        raise ApiError("invalid_period", "Analysis start must be before end.")
    by = {r["date"]: r.get("value") for r in rows}
    return [{"date": _idx_to_date(i), "value": by.get(_idx_to_date(i))} for i in range(a, b + 1)]


def longest_contiguous(win: list[dict]) -> tuple[str, str, int] | None:
    best = None
    run_start = None
    for i, r in enumerate(win + [{"value": None}]):
        if r["value"] is not None and run_start is None:
            run_start = i
        elif r["value"] is None and run_start is not None:
            n = i - run_start
            if not best or n > best[2]:
                best = (win[run_start]["date"], win[i - 1]["date"], n)
            run_start = None
    return best


def _design(win: list[dict]):
    i0 = _month_index(win[0]["date"])
    t = np.array([(_month_index(r["date"]) - i0) / 12.0 for r in win])
    months = np.array([int(r["date"][5:7]) for r in win])
    dummies = np.column_stack([(months == m).astype(float) for m in range(2, 13)])
    X = np.column_stack([np.ones(len(win)), t, dummies])
    return X, t, months


def climatology(win: list[dict], baseline: tuple[str, str]) -> dict[int, float]:
    a, b = _month_index(baseline[0]), _month_index(baseline[1])
    acc: dict[int, list[float]] = {m: [] for m in range(1, 13)}
    for r in win:
        i = _month_index(r["date"])
        if a <= i <= b and r["value"] is not None:
            acc[int(r["date"][5:7])].append(r["value"])
    return {m: (float(np.mean(v)) if v else None) for m, v in acc.items()}


def trend(rows: list[dict], start: str, end: str, units: str, variable: str,
          baseline: tuple[str, str] | None = None) -> dict:
    win = window_rows(rows, start, end)
    n_total = len(win)
    valid = [r for r in win if r["value"] is not None]
    gaps = n_total - len(valid)
    if baseline is None:
        # Declared default: first 20 years of the window (or the whole window if shorter)
        b_end = _idx_to_date(min(_month_index(start) + 240 - 1, _month_index(end)))
        baseline = (start, b_end)
    clim = climatology(win, baseline)
    anomalies = []
    for r in win:
        c = clim.get(int(r["date"][5:7]))
        anomalies.append({
            "date": r["date"],
            "value": r["value"],
            "anomaly": None if (r["value"] is None or c is None) else round(r["value"] - c, 4),
        })

    base = {
        "variable": variable,
        "units": units,
        "period": {"start": start, "end": end},
        "n_months_requested": n_total,
        "n_valid": len(valid),
        "n_missing": gaps,
        "coverage": round(len(valid) / n_total, 4) if n_total else 0,
        "baseline": {"start": baseline[0], "end": baseline[1], "definition": "calendar-month means over baseline"},
        "series": anomalies,
        "method": {
            "version": TREND_METHOD_VERSION,
            "model": "OLS: value ~ intercept + years_elapsed + 11 calendar-month indicators",
            "uncertainty": f"HAC (Newey–West, Bartlett kernel) covariance, maxlags={HAC_LAGS}; sensitivity at maxlags={HAC_SENSITIVITY_LAGS}",
            "implementation": "statsmodels OLS.fit(cov_type='HAC', cov_kwds={'maxlags': L})",
            "rule": f"Inference requires >= {MIN_INFERENTIAL_MONTHS} consecutive valid months spanning the full window (product rule).",
            "assumptions": [
                "Linear trend in the mean after removing a fixed seasonal cycle.",
                "Residual autocorrelation/heteroskedasticity handled approximately by HAC; not a test of model adequacy.",
                "Exploratory: the CI describes uncertainty about the fitted linear slope, not a prediction interval for future events.",
            ],
        },
    }

    if gaps > 0 or len(valid) < MIN_INFERENTIAL_MONTHS:
        lc = longest_contiguous(win)
        reason = (
            f"The window has {gaps} missing month(s); significance testing is not run on gapped series."
            if gaps
            else f"Only {len(valid)} valid months; the inferential path requires {MIN_INFERENTIAL_MONTHS}."
        )
        base.update({
            "mode": "descriptive",
            "limitation": reason,
            "suggested_interval": (
                {"start": lc[0], "end": lc[1], "months": lc[2]} if lc and lc[2] >= MIN_INFERENTIAL_MONTHS else None
            ),
            "descriptive": {
                "mean": round(float(np.mean([r["value"] for r in valid])), 4) if valid else None,
                "min": round(float(np.min([r["value"] for r in valid])), 4) if valid else None,
                "max": round(float(np.max([r["value"] for r in valid])), 4) if valid else None,
            },
        })
        return base

    y = np.array([r["value"] for r in win], dtype=float)
    X, t, _ = _design(win)
    fit = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": HAC_LAGS})
    fit24 = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": HAC_SENSITIVITY_LAGS})
    slope = float(fit.params[1])
    ci = fit.conf_int(alpha=0.05)[1]
    se = float(fit.bse[1])
    p = float(fit.pvalues[1])
    resid = fit.resid
    lag1 = float(np.corrcoef(resid[:-1], resid[1:])[0, 1])

    anom_vals = np.array([a["anomaly"] for a in anomalies], dtype=float)
    tm = float(np.mean(t))
    line = slope * (t - tm) + float(np.nanmean(anom_vals))

    sig = p < 0.05
    direction = "increase" if slope > 0 else "decrease"
    if sig:
        statement = (
            f"Statistically detectable linear {direction} under this method: {slope * 10:+.3f} {units} per decade "
            f"(95% CI {ci[0] * 10:+.3f} to {ci[1] * 10:+.3f})."
        )
    else:
        statement = (
            f"No statistically detectable linear trend under this method (estimate {slope * 10:+.3f} {units} per decade, "
            f"95% CI {ci[0] * 10:+.3f} to {ci[1] * 10:+.3f}). This is not evidence of no change."
        )
    base.update({
        "mode": "inferential",
        "slope_per_decade": round(slope * 10, 5),
        "ci95_per_decade": [round(float(ci[0]) * 10, 5), round(float(ci[1]) * 10, 5)],
        "se_per_decade": round(se * 10, 5),
        "p_value": p,
        "significant_at_0_05": sig,
        "statement": statement,
        "trend_line": [{"date": r["date"], "value": round(float(v), 4)} for r, v in zip(win, line)],
        "sensitivity": {
            "maxlags": HAC_SENSITIVITY_LAGS,
            "ci95_per_decade": [round(float(fit24.conf_int()[1][0]) * 10, 5), round(float(fit24.conf_int()[1][1]) * 10, 5)],
            "p_value": float(fit24.pvalues[1]),
        },
        "diagnostics": {
            "n": int(fit.nobs),
            "r_squared": round(float(fit.rsquared), 4),
            "durbin_watson": round(float(durbin_watson(resid)), 4),
            "residual_lag1_autocorr": round(lag1, 4),
        },
    })
    return base


def bh_adjust(results: list[dict]) -> list[dict]:
    """Benjamini–Hochberg across the full prespecified family; descriptive members keep q=None."""
    idx = [i for i, r in enumerate(results) if r.get("mode") == "inferential"]
    if idx:
        ps = [results[i]["p_value"] for i in idx]
        _, q, _, _ = multipletests(ps, alpha=0.05, method="fdr_bh")
        for i, qv in zip(idx, q):
            results[i]["q_value"] = float(qv)
            results[i]["family"] = {
                "size": len(results),
                "tested": len(idx),
                "adjustment": "Benjamini–Hochberg FDR",
                "members": [r["variable"] for r in results],
            }
    for r in results:
        r.setdefault("q_value", None)
    return results


def _residuals(win: list[dict]) -> dict[str, float]:
    """Residuals after removing a linear trend + calendar-month effects (fit on valid months only)."""
    valid = [r for r in win if r["value"] is not None]
    if len(valid) < 24:
        return {}
    X, _, _ = _design_with_origin(valid, win[0]["date"])
    y = np.array([r["value"] for r in valid])
    fit = sm.OLS(y, X).fit()
    return {r["date"]: float(e) for r, e in zip(valid, fit.resid)}


def _design_with_origin(rows: list[dict], origin: str):
    i0 = _month_index(origin)
    t = np.array([(_month_index(r["date"]) - i0) / 12.0 for r in rows])
    months = np.array([int(r["date"][5:7]) for r in rows])
    dummies = np.column_stack([(months == m).astype(float) for m in range(2, 13)])
    return np.column_stack([np.ones(len(rows)), t, dummies]), t, months


def _corr(a: list[float], b: list[float]):
    if len(a) < 3:
        return None
    r = np.corrcoef(a, b)[0, 1]
    return None if math.isnan(r) else round(float(r), 4)


def associate(x_rows, y_rows, start, end, x_var, y_var, max_lag: int = 3) -> dict:
    wx, wy = window_rows(x_rows, start, end), window_rows(y_rows, start, end)
    pairs = [(a["value"], b["value"]) for a, b in zip(wx, wy) if a["value"] is not None and b["value"] is not None]
    rx, ry = _residuals(wx), _residuals(wy)
    dates = [r["date"] for r in wx]
    res_pairs = [(rx[d], ry[d]) for d in dates if d in rx and d in ry]
    lagged = []
    for lag in range(0, max_lag + 1):
        xs, ys = [], []
        for i, d in enumerate(dates):
            if i + lag < len(dates):
                d2 = dates[i + lag]
                if d in rx and d2 in ry:
                    xs.append(rx[d])
                    ys.append(ry[d2])
        lagged.append({"lag_months": lag, "residual_r": _corr(xs, ys), "n": len(xs)})
    return {
        "x": x_var,
        "y": y_var,
        "period": {"start": start, "end": end},
        "overlap_months": len(pairs),
        "missing_months": len(dates) - len(pairs),
        "raw_pearson_r": _corr([p[0] for p in pairs], [p[1] for p in pairs]),
        "residual_pearson_r": _corr([p[0] for p in res_pairs], [p[1] for p in res_pairs]),
        "lagged_residual_r": lagged,
        "method": {
            "version": ASSOC_METHOD_VERSION,
            "notes": [
                "Descriptive only: no significance claim (autocorrelated series inflate naive tests).",
                "Residuals remove each variable's own linear trend and calendar-month means.",
                "Both variables come from the same MERRA-2-derived POWER product; they are not independent lines of evidence.",
                "A lagged association is a hypothesis, not causality or a validated forecast.",
            ],
        },
    }


def analysis_cache_key(kind: str, artifact_ids: list[str], params: dict) -> str:
    material = {"kind": kind, "artifacts": sorted(artifact_ids), "params": params,
                "method": TREND_METHOD_VERSION if kind == "trend" else ASSOC_METHOD_VERSION}
    return hashlib.sha256(db.dumps(material).encode()).hexdigest()[:24]
