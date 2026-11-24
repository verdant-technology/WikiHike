"""Stage 1: raw playbyplayv3 CSV -> cleaned per-season parquet with possessions.

Reads only from data/raw (verifying MANIFEST sha256). Writes data/clean/pbp_{season}.parquet.

Possession rule (simple, documented in ANALYSIS_PLAN.md):
  Each row that reveals which team has the ball sets `off_side`:
    shots, free throws, turnovers -> actor's side
    rebounds (player or team)     -> rebounder's side
    offensive / charge fouls      -> fouler's side
    other common fouls, defensive goaltending, kicked ball -> the other side
  Rows that reveal nothing inherit the last known value. A new possession
  starts when off_side changes or a period starts.
"""
import hashlib, json, pathlib, re, tarfile

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW, CLEAN = ROOT / "data" / "raw", ROOT / "data" / "clean"

# Fouls counted as outcomes ("eligible"): ordinary judgment calls on the floor.
ELIGIBLE_FOULS = {"Shooting", "Personal", "Loose Ball", "Offensive", "Offensive Charge"}
OFFENSIVE_FOULS = {"Offensive", "Offensive Charge"}
DEFENSIVE_FOULS = {"Shooting", "Personal", "Personal Take", "Transition Take", "Clear Path",
                   "Flagrant Type 1", "Flagrant Type 2", "Away From Play"}
# Challengeable non-foul calls used as control events.
OOB_TURNOVERS = {"Out of Bounds - Bad Pass Turnover", "Out of Bounds Lost Ball Turnover",
                 "Step Out of Bounds Turnover"}
GOALTEND = {"Offensive Goaltending"}           # turnover subtype
DEF_VIOLATIONS = {"Defensive Goaltending", "Kicked Ball"}  # violation subtypes

CLOCK_RE = re.compile(r"PT(\d+)M([\d.]+)S")


def clock_seconds(s: pd.Series) -> pd.Series:
    m = s.str.extract(CLOCK_RE)
    return m[0].astype(float) * 60 + m[1].astype(float)


def verify(season: int) -> pathlib.Path:
    manifest = {m["season"]: m for m in json.loads((RAW / "MANIFEST.json").read_text())}
    path = RAW / manifest[season]["file"]
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest[season]["sha256"]:
        raise RuntimeError(f"checksum mismatch for {path}")
    return path


def load(season: int) -> pd.DataFrame:
    with tarfile.open(verify(season)) as tf:
        member = next(m for m in tf.getmembers() if m.name.endswith(".csv"))
        d = pd.read_csv(tf.extractfile(member), dtype=str, keep_default_na=False)
    d["row_ix"] = np.arange(len(d))  # API order = chronological order
    return d


def clean(season: int) -> pd.DataFrame:
    d = load(season)
    out = pd.DataFrame({
        "season": season,
        "game_id": d.gameId.str.zfill(10),
        "row_ix": d.row_ix,
        "action_number": pd.to_numeric(d.actionNumber, errors="coerce").astype("Int64"),
        "period": pd.to_numeric(d.period, errors="coerce").astype("Int64"),
        "clock_s": clock_seconds(d.clock),
        "side": d.location.replace("", pd.NA),
        "team_id": d.teamId,
        "person_id": d.personId,
        "action_type": d.actionType.str.strip(),
        "sub_type": d.subType.str.strip(),
        "description": d.description,
    })
    for col in ("scoreHome", "scoreAway"):
        v = pd.to_numeric(d[col].replace("", np.nan), errors="coerce")
        out[col] = v.groupby(out.game_id).ffill().fillna(0)
    out["margin_home"] = out.scoreHome - out.scoreAway

    at, st, side = out.action_type, out.sub_type, out.side
    other = side.map({"h": "v", "v": "h"})
    is_foul = at.eq("Foul")
    off = pd.Series(pd.NA, index=out.index, dtype="object")
    actor = at.isin(["Made Shot", "Missed Shot", "Free Throw", "Turnover", "Rebound"])
    off[actor] = side[actor]
    m = is_foul & st.isin(OFFENSIVE_FOULS); off[m] = side[m]
    m = is_foul & st.isin(DEFENSIVE_FOULS); off[m] = other[m]
    m = at.eq("Violation") & st.isin(DEF_VIOLATIONS); off[m] = other[m]

    out["off_side"] = off.groupby([out.game_id, out.period]).ffill().bfill()
    new = (out.off_side != out.groupby("game_id").off_side.shift()) | \
          (out.period != out.groupby("game_id").period.shift())
    out["poss"] = new.groupby(out.game_id).cumsum().astype(int)

    # Outcome and event flags.
    out["elig_foul"] = is_foul & st.isin(ELIGIBLE_FOULS)
    out["challengeable_call"] = out.elig_foul | \
        (at.eq("Turnover") & st.isin(OOB_TURNOVERS | GOALTEND)) | \
        (at.eq("Violation") & st.eq("Defensive Goaltending"))
    out["challenge"] = at.eq("Instant Replay") & st.str.startswith("Coach Challenge")
    out["challenge_result"] = np.select(
        [out.challenge & st.str.contains("Overturn"), out.challenge & st.str.contains("Support"),
         out.challenge & st.str.contains("Stands")], ["overturn", "support", "stands"], None)
    out["challenge_timeout"] = at.eq("Timeout") & st.eq("Coach Challenge")
    out["timeout"] = at.eq("Timeout")
    # Late-game exclusion zone: last 2:00 of the 4th and all of OT.
    out["late"] = (out.period >= 5) | ((out.period == 4) & (out.clock_s <= 120))
    return out


if __name__ == "__main__":
    CLEAN.mkdir(parents=True, exist_ok=True)
    for s in range(2019, 2026):
        c = clean(s)
        c.to_parquet(CLEAN / f"pbp_{s}.parquet", index=False)
        npos = c.groupby("game_id").poss.max()
        print(s, "games", c.game_id.nunique(), "rows", len(c),
              "poss/game (both teams, incl. OT) mean", round(npos.mean(), 1),
              "challenges", int(c.challenge.sum()), "elig fouls/game", round(c.elig_foul.sum() / c.game_id.nunique(), 1))
