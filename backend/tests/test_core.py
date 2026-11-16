"""Deterministic tests: numerical correctness, calendar handling, conversions, cache keys, isolation.
Synthetic data here is a TEST FIXTURE ONLY and is never stored as environmental evidence."""
import calendar
import math
import os
import tempfile

os.environ.setdefault("EARTHINSPECT_DATA_DIR", tempfile.mkdtemp(prefix="ei-test-"))

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from app import analysis as an  # noqa: E402
from app import power  # noqa: E402
from app.errors import ApiError  # noqa: E402
from app.geometry import canonical  # noqa: E402


def synth(start_year=2001, years=24, slope_per_year=0.03, amp=8.0, noise=0.4, seed=1, gaps=()):
    rng = np.random.default_rng(seed)
    rows = []
    for k in range(years * 12):
        y, m = start_year + k // 12, k % 12 + 1
        v = 10 + slope_per_year * (k / 12) + amp * math.sin(2 * math.pi * (m - 1) / 12) + rng.normal(0, noise)
        d = f"{y}-{m:02d}"
        rows.append({"date": d, "value": None if d in gaps else round(v, 4)})
    return rows


def test_recovers_known_trend_with_seasonality():
    r = an.trend(synth(), "2001-01", "2024-12", "C", "T2M")
    assert r["mode"] == "inferential"
    assert abs(r["slope_per_decade"] - 0.3) < 0.06
    lo, hi = r["ci95_per_decade"]
    assert lo < 0.3 < hi
    assert r["p_value"] < 0.001
    assert r["n_valid"] == 288


def test_null_trend_not_forced_significant():
    r = an.trend(synth(slope_per_year=0.0, seed=7), "2001-01", "2024-12", "C", "T2M")
    assert r["mode"] == "inferential"
    assert r["ci95_per_decade"][0] < 0 < r["ci95_per_decade"][1] or r["p_value"] >= 0.01


def test_gaps_block_inference_and_are_not_compressed():
    rows = synth(gaps={"2010-06"})
    r = an.trend(rows, "2001-01", "2024-12", "C", "T2M")
    assert r["mode"] == "descriptive"
    assert r["n_missing"] == 1
    assert len(r["series"]) == 288  # calendar preserved
    assert r["suggested_interval"]["start"] == "2010-07"  # longest contiguous run >= 120


def test_short_series_rejected_for_inference():
    r = an.trend(synth(), "2015-01", "2020-12", "C", "T2M")
    assert r["mode"] == "descriptive" and "120" in r["limitation"]


def test_missing_rows_kept_on_calendar():
    rows = [x for x in synth() if x["date"] != "2005-03"]  # absent month
    win = an.window_rows(rows, "2005-01", "2005-05")
    assert [w["date"] for w in win] == ["2005-01", "2005-02", "2005-03", "2005-04", "2005-05"]
    assert win[2]["value"] is None


def test_bh_adjustment_family():
    res = [an.trend(synth(seed=s, slope_per_year=sl), "2001-01", "2024-12", "u", f"V{s}") for s, sl in ((1, 0.05), (2, 0.0), (3, 0.0))]
    res = an.bh_adjust(res)
    assert all(r["q_value"] >= r["p_value"] for r in res)
    assert res[0]["family"]["size"] == 3


def test_normalize_excludes_annual_and_fill_and_converts_precip():
    spec = {"variable": "PRECTOTCORR", "start_year": 2020, "end_year": 2020}
    vals = {f"2020{m:02d}": 2.0 for m in range(1, 13)}
    vals["202013"] = 99.0
    vals["202004"] = -999.0
    raw = {"type": "FeatureCollection", "header": {"fill_value": -999.0, "sources": ["MERRA2"]},
           "parameters": {"PRECTOTCORR": {"units": "mm/day", "longname": "Precipitation Corrected"}},
           "features": [{"geometry": {"coordinates": [10.0, 50.0]}, "properties": {"parameter": {"PRECTOTCORR": vals}}},
                        {"geometry": {"coordinates": [10.625, 50.0]}, "properties": {"parameter": {"PRECTOTCORR": vals}}}]}
    n = power.normalize(raw, spec)
    assert len(n["rows"]) == 12
    assert n["rows"][3]["value"] is None  # fill value -> missing, never zero
    feb = n["rows"][1]
    assert feb["monthly_total_mm"] == pytest.approx(2.0 * calendar.monthrange(2020, 2)[1])  # leap year: 29 days
    assert feb["days_in_month"] == 29
    assert n["support"]["kind"] == "area_weighted_grid_mean"
    assert n["support"]["cell_size_deg"]["lon"] == pytest.approx(0.625)


def test_cache_keys_distinguish_inputs():
    g = {"type": "bbox", "west": 11.5, "south": 54.7, "east": 13.5, "north": 56.7}
    a = power.request_spec("T2M", g, 2001, 2024)["cache_key"]
    assert a == power.request_spec("T2M", dict(g), 2001, 2024)["cache_key"]
    assert a != power.request_spec("T2M", {**g, "west": 11.4}, 2001, 2024)["cache_key"]
    assert a != power.request_spec("T2M", g, 2002, 2024)["cache_key"]
    assert a != power.request_spec("PRECTOTCORR", g, 2001, 2024)["cache_key"]


def test_analysis_cache_key_tracks_method_version(monkeypatch):
    k1 = an.analysis_cache_key("trend_batch", ["a", "b"], {"start": "2001-01"})
    assert k1 == an.analysis_cache_key("trend_batch", ["b", "a"], {"start": "2001-01"})
    assert k1 != an.analysis_cache_key("trend_batch", ["a", "b"], {"start": "2002-01"})
    monkeypatch.setattr(an, "TREND_METHOD_VERSION", "trend-test-9.9")
    assert k1 != an.analysis_cache_key("trend_batch", ["a", "b"], {"start": "2001-01"})  # method change invalidates


def test_bh_controls_significance_wording():
    res = [an.trend(synth(seed=s, slope_per_year=sl), "2001-01", "2024-12", "u", f"V{s}") for s, sl in ((1, 0.05), (2, 0.0), (3, 0.0), (4, 0.0))]
    res = an.bh_adjust(res)
    for r in res:
        assert r["significant_bh"] == (r["q_value"] < 0.05)
        if r["significant_at_0_05"] and not r["significant_bh"]:
            assert "not after Benjamini" in r["statement"]


def test_geometry_validation():
    with pytest.raises(ApiError) as e:
        canonical({"type": "bbox", "west": 170, "south": 0, "east": -170, "north": 5})
    assert e.value.code == "antimeridian_unsupported"
    with pytest.raises(ApiError):
        canonical({"type": "polygon"})
    with pytest.raises(ApiError):
        power.request_spec("T2M", {"type": "bbox", "west": 0, "south": 0, "east": 1, "north": 1}, 2001, 2024)


def test_residual_association_removes_shared_trend():
    a = synth(seed=1, slope_per_year=0.1)
    b = synth(seed=2, slope_per_year=0.1)
    res = an.associate(a, b, "2001-01", "2024-12", "A", "B")
    assert res["raw_pearson_r"] > 0.9  # shared seasonality inflates raw correlation
    assert abs(res["residual_pearson_r"]) < 0.2  # independent noise once trend+season removed
