"""Q1 exploratory: which mechanical control absorbs the raw makeup pattern? Not pre-registered."""
import pathlib
import pandas as pd
import q1_overturn_vs_lost as q1

ROOT = pathlib.Path(__file__).resolve().parent.parent
d, _ = q1.prep(20)
B = q1.BASE
specs = {
    "none": B,
    "+offshare": B + " + d_offshare",
    "+team_fouls": B + " + C(tf_chal_c) + C(tf_opp_c)",
    "+trouble": B + " + C(trouble_chal_c) + C(trouble_opp_c)",
    "+offshare+trouble": B + " + d_offshare + C(trouble_chal_c) + C(trouble_opp_c)",
    "all (primary)": B + q1.MECH,
}
rows = []
for name, rhs in specs.items():
    for y in ("d_net", "d_agg", "d_oth", "d_net_def"):
        r = q1.fit(d, y, rhs)
        rows.append({"controls": name, "y": y, "est": r["est"], "lo": r["lo"], "hi": r["hi"], "p": r["p"]})
t = pd.DataFrame(rows)
t.to_csv(ROOT / "results/q1/exploratory_decompose.csv", index=False)
print(t.pivot(index="controls", columns="y", values="est").loc[list(specs)].round(4))
print(t[t.y == "d_net"].round(4).to_string())
# Does team-foul count proxy the pre-window? correlation within arm
print(d.groupby("treat")[["tf_chal", "agg_pre"]].corr().round(3))
