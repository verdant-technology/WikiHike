"""Stage 2: cleaned pbp -> possession table and event table (all seasons).

Outputs (data/clean):
  possessions.parquet  one row per game-possession: period, start clock, late flag,
                       eligible fouls committed by home / visitor.
  events.parquet       one row per event. kind = 'challenge' (any outcome) or
                       'call' (an unchallenged challengeable call).
"""
import pathlib

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
CLEAN = ROOT / "data" / "clean"
WINDOW = 20  # possessions; used only for the contamination flag here


def possessions(p: pd.DataFrame) -> pd.DataFrame:
    g = p.groupby(["game_id", "poss"], sort=False)
    pos = g.agg(season=("season", "first"), period=("period", "first"),
                clock_s=("clock_s", "first"), late=("late", "first"),
                margin_home=("margin_home", "first"), off_side=("off_side", "first"))
    f = p[p.elig_foul]
    for s in ("h", "v"):
        pos[f"fouls_{s}"] = f[f.side == s].groupby(["game_id", "poss"]).size()
    return pos.fillna({"fouls_h": 0, "fouls_v": 0}).reset_index()


def challenges(p: pd.DataFrame) -> pd.DataFrame:
    ch = p[p.challenge].copy()
    # Challenger: a timeout row at the same game/period/clock just before the replay row.
    to = p[p.timeout][["game_id", "period", "clock_s", "row_ix", "side"]]
    m = ch[["game_id", "period", "clock_s", "row_ix"]].reset_index().merge(
        to, on=["game_id", "period", "clock_s"], suffixes=("", "_to"))
    m = m[(m.row_ix_to < m.row_ix) & (m.row_ix - m.row_ix_to <= 8)]
    m = m.sort_values("row_ix_to").groupby("index").side.last()
    ch["challenger"] = m
    # Reviewed action: person_id on replay rows holds its actionNumber.
    ref = p[["game_id", "action_number", "side", "action_type", "sub_type"]].dropna(subset=["action_number"])
    ref = ref[ref.action_type != "Instant Replay"].drop_duplicates(["game_id", "action_number"])
    ref = ref.rename(columns={"action_number": "ref_action", "side": "ref_side",
                              "action_type": "ref_type", "sub_type": "ref_sub"})
    ch["ref_action"] = pd.to_numeric(ch.person_id, errors="coerce").astype("Int64")
    ch = ch.reset_index().merge(ref, on=["game_id", "ref_action"], how="left").set_index("index")
    # If no timeout row, the call went against the challenger, so use the reviewed call's side.
    ch["challenger_src"] = np.where(ch.challenger.notna(), "timeout",
                                    np.where(ch.ref_side.notna(), "ref_call", "unknown"))
    ch["challenger"] = ch.challenger.fillna(ch.ref_side)
    ch["kind"] = "challenge"
    ch["aggrieved"] = ch.challenger
    ch["call_type"] = ch.ref_sub.where(ch.ref_sub.notna(), None)
    return ch


def calls(p: pd.DataFrame, ch: pd.DataFrame) -> pd.DataFrame:
    c = p[p.challengeable_call].copy()
    # Drop calls that were themselves reviewed, or share a stoppage with a challenge.
    reviewed = set(zip(ch.game_id, ch.ref_action.astype("float")))
    c = c[[(g, float(a)) not in reviewed for g, a in zip(c.game_id, c.action_number)]]
    stop = set(zip(ch.game_id, ch.period, ch.clock_s))
    c = c[[k not in stop for k in zip(c.game_id, c.period, c.clock_s)]]
    c["kind"] = "call"
    c["aggrieved"] = c.side
    c["call_type"] = c.sub_type
    return c


def main():
    pos_all, ev_all = [], []
    for s in range(2019, 2026):
        p = pd.read_parquet(CLEAN / f"pbp_{s}.parquet")
        pos_all.append(possessions(p))
        ch = challenges(p)
        ev = pd.concat([ch, calls(p, ch)], ignore_index=True)
        ev_all.append(ev[["season", "game_id", "row_ix", "poss", "period", "clock_s", "late",
                          "margin_home", "kind", "challenge_result", "challenger_src",
                          "aggrieved", "call_type"]])
    pos = pd.concat(pos_all, ignore_index=True)
    ev = pd.concat(ev_all, ignore_index=True)
    # Contamination flags: another challenge within +-WINDOW possessions in the same game.
    chp = ev[ev.kind == "challenge"][["game_id", "poss", "row_ix"]]
    j = ev[["game_id", "poss", "row_ix"]].reset_index().merge(chp, on="game_id", suffixes=("", "_c"))
    j = j[(j.row_ix != j.row_ix_c) & ((j.poss - j.poss_c).abs() <= WINDOW)]
    ev["challenge_nearby"] = ev.index.isin(j["index"])
    ev["game_has_challenge"] = ev.game_id.isin(chp.game_id)
    ev["challenge_seq"] = ev[ev.kind == "challenge"].groupby("game_id").row_ix.rank().astype("Int64")
    pos.to_parquet(CLEAN / "possessions.parquet", index=False)
    ev.to_parquet(CLEAN / "events.parquet", index=False)
    print("possessions", len(pos))
    print(ev.groupby(["season", "kind"]).size().unstack())
    c = ev[ev.kind == "challenge"]
    print(c.groupby("season").challenge_result.value_counts().unstack())
    print(c.challenger_src.value_counts())


if __name__ == "__main__":
    main()
