"""Acquire real NASA POWER data for the four seed cases (2001–2024) and run the trend family.
Then export source snapshots (real responses) for offline demos. Usage: python -m scripts.prewarm"""
import sys
import time

from app import db, power, services
from app.cases import all_cases

db.init_db()
services.seed_graph()
for c in all_cases():
    place = services._place_from_case(c["id"])
    t0 = time.time()
    try:
        b = services.run_trends(place, c["variables"], "2001-01", "2024-12", "system",
                                on_event=lambda t, l, p, d=None: print("   ", t, l, d if d is not None else ""))
        for r in b["results"]:
            if r["mode"] == "inferential":
                print(f"  {c['id']} {r['variable']}: {r['slope_per_decade']:+.4f} {r['units']}/dec "
                      f"CI[{r['ci95_per_decade'][0]:+.4f},{r['ci95_per_decade'][1]:+.4f}] p={r['p_value']:.4g} q={r['q_value']:.4g}")
            else:
                print(f"  {c['id']} {r['variable']}: descriptive — {r['limitation']}")
    except Exception as e:  # report and continue
        print("FAILED", c["id"], e, file=sys.stderr)
    print(f"== {c['id']} {time.time() - t0:.1f}s")
print("snapshots exported:", power.export_snapshots())
