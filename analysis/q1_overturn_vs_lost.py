"""Q1: After a challenge, does the winning team get fewer favorable calls (makeup)?

Treated = overturned challenges; control = lost challenges (support + stands).
Pre-registered in ANALYSIS_PLAN.md (Q1). --mde-only computes power from controls only.
"""
import argparse, json, pathlib

import numpy as np
import pandas as pd

import q0_challenge_vs_call as q0

ROOT = pathlib.Path(__file__).resolve().parent.parent
CLEAN, RES = ROOT / "data" / "clean", ROOT / "results" / "q1"
TROUBLE = {1: 2, 2: 3, 3: 4, 4: 5}  # fouls at or above which a player is "in foul trouble"
NON_TEAM = {"Offensive", "Offensive Charge"}  # offensive fouls do not count as team fouls


def foul_state(ch: pd.DataFrame) -> pd.DataFrame:
    """Team fouls in period and players in foul trouble, per team, just after the review."""
    out = []
    for s in sorted(ch.season.unique()):
        p = pd.read_parquet(CLEAN / f"pbp_{s}.parquet",
                            columns=["game_id", "row_ix", "period", "side", "person_id", "action_type", "sub_type"])
        f = p[(p.action_type == "Foul") & ~p.sub_type.str.contains("Technical|Double|Defense 3", na=False)
              & p.side.notna()]
        for r in ch[ch.season == s].itertuples():
            g = f[(f.game_id == r.game_id) & (f.row_ix < r.row_ix)]
            row = {"idx": r.Index}
            for lab, sd in (("chal", r.aggrieved), ("opp", {"h": "v", "v": "h"}[r.aggrieved])):
                t = g[g.side == sd]
                row[f"tf_{lab}"] = int(((t.period == r.period) & ~t.sub_type.isin(NON_TEAM)).sum())
                pf = t.groupby("person_id").size()
                row[f"trouble_{lab}"] = int((pf >= TROUBLE.get(int(r.period), 6)).sum())
            out.append(row)
    return pd.DataFrame(out).set_index("idx")


def offense_share(ev: pd.DataFrame, pos: pd.DataFrame, w: int) -> pd.DataFrame:
    """Share of observed pre/post possessions with the challenger on offense, plus
    defense-only foul rates for each team (immune to possession order)."""
    games = pd.Index(pos.game_id.unique())
    maxp = int(pos.poss.max()) + w + 2
    ok = pos[~pos.late]
    gi = games.get_indexer(ok.game_id)
    off_h = np.full((len(games), maxp), np.nan); off_h[gi, ok.poss.values] = (ok.off_side == "h").astype(float)
    fh = np.full((len(games), maxp), np.nan); fh[gi, ok.poss.values] = ok.fouls_h.values
    fv = np.full((len(games), maxp), np.nan); fv[gi, ok.poss.values] = ok.fouls_v.values
    offs = np.arange(-w, w + 1); offs = offs[offs != 0]
    eg = games.get_indexer(ev.game_id)[:, None]
    raw = ev.poss.values.astype(int)[:, None] + offs
    ep = np.clip(raw, 0, maxp - 1)
    oh = np.where(raw >= 1, off_h[eg, ep], np.nan)
    chal_h = (ev.aggrieved.astype(object).to_numpy() == "h")[:, None]
    chal_off = np.where(np.isnan(oh), np.nan, np.where(chal_h, oh, 1 - oh))
    f_chal = np.where(chal_h, fh[eg, ep], fv[eg, ep])
    f_opp = np.where(chal_h, fv[eg, ep], fh[eg, ep])
    out = pd.DataFrame(index=ev.index)
    for name, sel in (("pre", offs < 0), ("post", offs > 0)):
        co = chal_off[:, sel]
        out[f"offshare_{name}"] = np.nanmean(co, 1)
        cd = co == 0  # challenger defending
        od = co == 1  # opponent defending
        out[f"chal_def_{name}"] = np.nansum(np.where(cd, f_chal[:, sel], 0), 1) / np.where(cd.sum(1) > 0, cd.sum(1), np.nan)
        out[f"opp_def_{name}"] = np.nansum(np.where(od, f_opp[:, sel], 0), 1) / np.where(od.sum(1) > 0, od.sum(1), np.nan)
    out["d_offshare"] = out.offshare_post - out.offshare_pre
    out["d_net_def"] = (out.chal_def_post - out.opp_def_post) - (out.chal_def_pre - out.opp_def_pre)
    return out


def prep(w: int, fs: pd.DataFrame | None = None) -> pd.DataFrame:
    d = q0.prep(w)
    d = d[(d.kind == "challenge") & d.aggrieved.notna()].copy()
    pos = pd.read_parquet(CLEAN / "possessions.parquet")
    d = d.join(offense_share(d, pos, w))
    d["treat"] = (d.challenge_result == "overturn").astype(int)
    d["d_net"] = d.d_agg - d.d_oth  # change in (fouls on challenger - fouls on opponent)
    if fs is None:
        fs = foul_state(d)
    d = d.join(fs)
    for c in ("tf_chal", "tf_opp"):
        d[c + "_c"] = d[c].clip(upper=6)
    for c in ("trouble_chal", "trouble_opp"):
        d[c + "_c"] = d[c].clip(upper=3)
    return d, fs


BASE = "C(state) + C(margin_bin) + C(season)"
MECH = " + d_offshare + C(tf_chal_c) + C(tf_opp_c) + C(trouble_chal_c) + C(trouble_opp_c)"


def fit(d, y, rhs):
    q0.FORMULA = "{y} ~ treat + " + rhs
    return q0.fit(d, y)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mde-only", action="store_true")
    a = ap.parse_args()
    RES.mkdir(parents=True, exist_ok=True)
    d, fs = prep(20)
    if a.mde_only:
        ctrl = d[d.treat == 0]
        rate = d.treat.mean()
        res = {}
        for y in ("d_net", "d_agg", "d_oth", "d_net_def"):
            rng = np.random.default_rng(0)
            ses = [fit(ctrl.assign(treat=(rng.random(len(ctrl)) < rate).astype(int)), y, BASE + MECH)["se"]
                   for _ in range(50)]
            # Placebo SE uses only the control group; rescale to the real treated/control split.
            n0, n1 = len(ctrl), int(d.treat.sum())
            nt_p = rate * n0
            scale = np.sqrt((1 / n1 + 1 / n0) / (1 / nt_p + 1 / (n0 - nt_p)))
            se = float(np.mean(ses)) * scale
            res[y] = {"se": se, "mde_80pct_power": 2.8 * se, "n_treat": n1, "n_ctrl": n0}
        res["per_team_base_rate"] = float(d.agg_pre.mean())
        (RES / "mde.json").write_text(json.dumps(res, indent=2))
        print(json.dumps(res, indent=2))
        return
    rows = []
    specs = {
        "primary": (d, BASE + MECH),
        "no_mech_controls": (d, BASE),
        "ctrl_support_only": (d[(d.treat == 1) | (d.challenge_result == "support")], BASE + MECH),
        "ctrl_stands_only": (d[(d.treat == 1) | (d.challenge_result == "stands")], BASE + MECH),
        "first_challenge_only": (d[d.challenge_seq == 1], BASE + MECH),
        "timeout_identified": (d[d.challenger_src == "timeout"], BASE + MECH),
    }
    for name, (dd, rhs) in specs.items():
        for y in ("d_net", "d_agg", "d_oth"):
            rows.append({"window": 20, "spec": name, **fit(dd, y, rhs)})
    rows.append({"window": 20, "spec": "defense_only_rates", **fit(d, "d_net_def", BASE + MECH)})
    for w in (10, 40):
        dw, _ = prep(w, fs)
        rows.append({"window": w, "spec": "primary", **fit(dw, "d_net", BASE + MECH)})
    tab = pd.DataFrame(rows)
    tab.to_csv(RES / "estimates.csv", index=False)
    # Balance: mechanical covariates by arm.
    bal = d.groupby("treat")[["d_offshare", "tf_chal", "tf_opp", "trouble_chal", "trouble_opp",
                              "agg_pre", "oth_pre", "agg_post", "oth_post"]].mean()
    bal.to_csv(RES / "balance.csv")
    pd.set_option("display.width", 220)
    print(bal.round(4))
    print(tab.drop(columns=["ctrl_pre_mean"]).round(4).to_string())


if __name__ == "__main__":
    main()
