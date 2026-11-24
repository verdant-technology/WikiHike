"""Q0 exploratory: is the post-challenge dip a timeout/stoppage effect?

Every challenge comes with a long stoppage and usually a timeout row. Compare challenges
with unchallenged calls followed by a timeout at the same stoppage. Not pre-registered.
"""
import pathlib
import numpy as np
import pandas as pd
import q0_challenge_vs_call as q

ROOT = pathlib.Path(__file__).resolve().parent.parent
to = []
for s in range(2019, 2026):
    p = pd.read_parquet(ROOT / "data/clean" / f"pbp_{s}.parquet",
                        columns=["game_id", "period", "clock_s", "timeout", "challenge_timeout", "row_ix"])
    to.append(p[p.timeout & ~p.challenge_timeout][["game_id", "period", "clock_s"]].drop_duplicates())
to = pd.concat(to)
to["to_here"] = True
d = q.prep(20)
d = d.merge(to, on=["game_id", "period", "clock_s"], how="left")
d["to_here"] = d.to_here.fillna(False).astype(bool)
base = d[(d.kind == "challenge") | ((d.kind == "call") & ~d.challenge_nearby)]
ctrl_to = base[(base.kind == "challenge") | base.to_here]
print("control calls with a timeout at the same stoppage:", int(((ctrl_to.kind == "call")).sum()))
rows = []
for name, s in (("ctrl=calls+timeout", ctrl_to),):
    for y in ("d_all", "d_agg", "d_oth"):
        rows.append({"spec": name, **q.fit(s, y)})
    es = []
    for col in [c for c in s.columns if c.startswith("bin_")]:
        es.append({"bin": col[4:], **q.fit(s.assign(_y=s[col] - s.all_pre), "_y")})
    print(pd.DataFrame(es)[["bin", "est", "se", "lo", "hi"]].round(4).to_string())
# Also: timeout-vs-no-timeout among control calls alone (is there a timeout dip at all?)
c = base[base.kind == "call"].assign(treat=lambda x: x.to_here.astype(int))
for y in ("d_all",):
    rows.append({"spec": "within calls: timeout vs none", **q.fit(c, y)})
tab = pd.DataFrame(rows)
tab.to_csv(ROOT / "results/q0/exploratory_timeout.csv", index=False)
print(tab.round(4).to_string())
