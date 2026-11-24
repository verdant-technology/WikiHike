"""Q0: Does foul-calling change more after a coach's challenge than after an unchallenged call?

Pre-registered in ANALYSIS_PLAN.md (Q0). Run with --mde-only to compute power
from the control group alone, without looking at the treatment contrast.
"""
import argparse, json, pathlib

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

ROOT = pathlib.Path(__file__).resolve().parent.parent
CLEAN, RES = ROOT / "data" / "clean", ROOT / "results" / "q0"
BIN = 5
MIN_EXPOSURE = 10


def windows(ev: pd.DataFrame, pos: pd.DataFrame, w: int) -> pd.DataFrame:
    """Per event: fouls and exposure in pre/post windows and per 5-possession bin.

    Fouls are split by which team committed them, relative to the event's aggrieved
    team (the challenger, or the team the unchallenged call went against).
    """
    games = pd.Index(pos.game_id.unique())
    maxp = int(pos.poss.max()) + w + 2
    # Dense [game, possession] grids; NaN = not observed (late-game, or outside the game).
    fh_grid = np.full((len(games), maxp), np.nan)
    fv_grid = np.full((len(games), maxp), np.nan)
    ok = pos[~pos.late]
    gi = games.get_indexer(ok.game_id)
    fh_grid[gi, ok.poss.values] = ok.fouls_h.values
    fv_grid[gi, ok.poss.values] = ok.fouls_v.values
    offs = np.arange(-w, w + 1)
    offs = offs[offs != 0]
    eg = games.get_indexer(ev.game_id)[:, None]
    ep = np.clip(ev.poss.values.astype(int)[:, None] + offs, 0, maxp - 1)
    valid = (ev.poss.values.astype(int)[:, None] + offs) >= 1
    fh = np.where(valid, fh_grid[eg, ep], np.nan)
    fv = np.where(valid, fv_grid[eg, ep], np.nan)
    agg = ev.aggrieved.astype(object).to_numpy()[:, None]
    f_agg = np.where(agg == "h", fh, np.where(agg == "v", fv, np.nan))
    f_oth = np.where(agg == "h", fv, np.where(agg == "v", fh, np.nan))
    tot = fh + fv
    out = pd.DataFrame(index=ev.index)
    for name, sel in (("pre", offs < 0), ("post", offs > 0)):
        out[f"n_{name}"] = np.isfinite(tot[:, sel]).sum(1)
        for lab, arr in (("all", tot), ("agg", f_agg), ("oth", f_oth)):
            out[f"{lab}_{name}"] = np.nansum(arr[:, sel], 1) / out[f"n_{name}"].replace(0, np.nan)
    for b0 in range(-w, w, BIN):
        sel = (offs >= b0) & (offs < b0 + BIN) if b0 < 0 else (offs > b0) & (offs <= b0 + BIN)
        n = np.isfinite(tot[:, sel]).sum(1)
        lab = f"b{b0}" if b0 < 0 else f"b{b0 + 1}"
        out[f"bin_{lab}"] = np.nansum(tot[:, sel], 1) / np.where(n > 0, n, np.nan)
    return out


def prep(w: int) -> pd.DataFrame:
    ev = pd.read_parquet(CLEAN / "events.parquet")
    pos = pd.read_parquet(CLEAN / "possessions.parquet")
    ev = ev[~ev.late].reset_index(drop=True)
    d = pd.concat([ev, windows(ev, pos, w)], axis=1)
    d = d[(d.n_pre >= MIN_EXPOSURE) & (d.n_post >= MIN_EXPOSURE)]
    d["treat"] = (d.kind == "challenge").astype(int)
    d["clock_bin"] = (d.clock_s // 180).clip(upper=3).astype(int)
    d["state"] = d.period.astype(str) + "_" + d.clock_bin.astype(str)
    agg_margin = np.where(d.aggrieved == "h", d.margin_home, -d.margin_home)
    d["margin_bin"] = pd.cut(agg_margin, [-99, -20, -10, -5, 5, 10, 20, 99]).astype(str)
    for lab in ("all", "agg", "oth"):
        d[f"d_{lab}"] = d[f"{lab}_post"] - d[f"{lab}_pre"]
    return d


def sample(d: pd.DataFrame, spec: str) -> pd.DataFrame:
    ctrl = d.kind == "call"
    tr = d.kind == "challenge"
    if spec == "primary":
        keep = tr | (ctrl & ~d.challenge_nearby)
    elif spec == "ctrl_no_challenge_games":
        keep = tr | (ctrl & ~d.game_has_challenge)
    elif spec == "first_challenge_only":
        keep = (tr & (d.challenge_seq == 1)) | (ctrl & ~d.challenge_nearby)
    elif spec == "ctrl_fouls_only":
        keep = tr | (ctrl & ~d.challenge_nearby & ~d.call_type.str.contains("Turnover|Goaltending", na=False))
    elif spec in ("overturn", "support", "stands"):
        keep = (tr & (d.challenge_result == spec)) | (ctrl & ~d.challenge_nearby)
    else:
        raise ValueError(spec)
    return d[keep]


FORMULA = "{y} ~ treat + C(state) + C(margin_bin) + C(season)"


def fit(d: pd.DataFrame, y: str) -> dict:
    dd = d.dropna(subset=[y, "margin_bin"])
    m = smf.ols(FORMULA.format(y=y), data=dd).fit(
        cov_type="cluster", cov_kwds={"groups": pd.factorize(dd.game_id)[0]})
    ci = m.conf_int().loc["treat"]
    return {"y": y, "est": m.params["treat"], "se": m.bse["treat"], "lo": ci[0], "hi": ci[1],
            "p": m.pvalues["treat"], "n_treat": int(dd.treat.sum()), "n_ctrl": int((1 - dd.treat).sum()),
            "ctrl_pre_mean": dd.loc[dd.treat == 0, y.replace("d_", "") + "_pre"].mean()
            if y.startswith("d_") else np.nan}


def mde(d: pd.DataFrame) -> dict:
    c = sample(d, "primary")
    ctrl = c[c.treat == 0]
    nt = int(c.treat.sum())
    res = {}
    for y in ("d_all", "d_agg", "d_oth"):
        # Cluster-robust SE inflation estimated from control-only placebo: random 'treat' labels
        # assigned at the treated rate, refit, repeat. Uses no treated outcomes.
        rng = np.random.default_rng(0)
        ses = []
        for _ in range(20):
            p = ctrl.copy()
            p["treat"] = (rng.random(len(p)) < nt / len(c)).astype(int)
            ses.append(fit(p, y)["se"])
        se = float(np.mean(ses))
        base = ctrl[y.replace("d_", "") + "_pre"].mean()
        res[y] = {"placebo_se": se, "mde_80pct_power": 2.8 * se, "ctrl_pre_rate": base,
                  "mde_pct_of_base": 100 * 2.8 * se / base, "n_treat": nt, "n_ctrl": len(ctrl)}
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mde-only", action="store_true")
    a = ap.parse_args()
    RES.mkdir(parents=True, exist_ok=True)
    d = prep(20)
    if a.mde_only:
        r = mde(d)
        (RES / "mde.json").write_text(json.dumps(r, indent=2))
        print(json.dumps(r, indent=2))
        return
    rows = []
    specs = ["primary", "ctrl_no_challenge_games", "first_challenge_only", "ctrl_fouls_only",
             "overturn", "support", "stands"]
    for spec in specs:
        for y in ("d_all", "d_agg", "d_oth"):
            rows.append({"window": 20, "spec": spec, **fit(sample(d, spec), y)})
    for w in (10, 40):
        dw = prep(w)
        rows.append({"window": w, "spec": "primary", **fit(sample(dw, "primary"), "d_all")})
    tab = pd.DataFrame(rows)
    tab.to_csv(RES / "estimates.csv", index=False)
    # Event study: per-bin rate minus own pre-window mean, treat coefficient per bin.
    p = sample(d, "primary")
    es = []
    for col in [c for c in p.columns if c.startswith("bin_")]:
        p = p.assign(_y=p[col] - p.all_pre)
        r = fit(p, "_y")
        es.append({"bin": col[4:], **r})
    pd.DataFrame(es).to_csv(RES / "event_study.csv", index=False)
    # Descriptives
    desc = p.groupby("kind")[["all_pre", "all_post", "agg_pre", "agg_post", "oth_pre", "oth_post",
                               "n_pre", "n_post"]].mean()
    desc.to_csv(RES / "descriptives.csv")
    pd.set_option("display.width", 200)
    print(desc.round(4))
    print(tab.round(4).to_string())
    print(pd.DataFrame(es)[["bin", "est", "se", "lo", "hi"]].round(4).to_string())


if __name__ == "__main__":
    main()
