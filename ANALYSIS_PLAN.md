# Analysis Plan

Pre-registration for the NBA coach's-challenge study. Each question's section is
fixed and committed before its outcome comparison runs. Later additions go under
**Exploratory**, labeled as such.

## Data (all questions)

- **Source:** stats.nba.com `playbyplayv3`, regular seasons 2019-20 to 2025-26, via the
  public mirror `shufinskiy/nba_data` (stats.nba.com blocks this cloud environment).
  Archives are cached in `data/raw` with sha256 in `data/raw/MANIFEST.json`.
- **Pipeline:** `pipeline/s00_fetch.py` (raw) -> `s10_clean.py` (per-season clean parquet,
  possessions) -> `s20_events.py` (possession and event tables) -> `analysis/`.
- **Possessions:** offensive team inferred row by row (shots, FTs, turnovers, rebounds ->
  actor's team; offensive fouls -> fouler; defensive fouls, defensive goaltending, kicked
  ball -> other team), carried forward; a possession starts when the offensive team or
  period changes. Check: ~100 possessions per team per game, matching league pace.
- **Challenges:** `Instant Replay` rows with subtype `Coach Challenge {Overturn Ruling |
  Support Ruling | Ruling Stands}`. 7,479 total. On these rows `personId` holds the
  `actionNumber` of the reviewed call. Overturned calls are usually deleted from the feed.
- **Challenger:** the team of the timeout row at the same clock just before the replay
  row (95%); else the team the reviewed call went against (2%); else unknown (3%).
- **Eligible fouls (outcome):** subtypes Shooting, Personal, Loose Ball, Offensive,
  Offensive Charge. Excluded: takes, flagrants, technicals, away-from-play, clear path,
  double fouls, defensive 3 seconds.
- **Late-game zone:** last 2:00 of the 4th and all OT. Excluded as events and as exposure.

## Q0. Is foul-calling different after a challenge than after an unchallenged call?

**Question.** Does the before-to-after change in foul rate around a coach's challenge
(any outcome) differ from the change around an ordinary unchallenged call?

**Events.**
- Treated: every coach's challenge outside the late-game zone (5,544 after exposure filter).
- Control: every unchallenged challengeable call outside the late-game zone: eligible fouls,
  out-of-bounds turnovers, offensive and defensive goaltending. Calls that were the
  reviewed action, or share a game/period/clock stoppage with a challenge, are removed.
- Primary control sample drops calls with a challenge within ±20 possessions, so a
  challenge effect cannot leak into the control group.

**Windows.** Possessions -20..-1 (pre) and +1..+20 (post) relative to the event
possession. The event possession itself is excluded (it holds the call and its free
throws). Possessions in the late-game zone are dropped. Events need at least 10 observed
possessions on each side.

**Outcomes (fouls per possession).**
1. `d_all` (**primary**): eligible fouls by both teams, post rate minus pre rate.
2. `d_agg`: fouls committed by the aggrieved team (challenger, or the team the
   unchallenged call went against).
3. `d_oth`: fouls committed by the other team.

**Model.** Event-level OLS:
`d ~ treat + period x clock-bucket (3 min) + aggrieved-team margin bucket + season`,
standard errors clustered by game. The game-state controls matter: challenges cluster
late, and foul rates rise late in games, so each challenge is compared with unchallenged
calls at the same point in a game. Estimand: coefficient on `treat`.

**Event study.** Same model per 5-possession bin, outcome = bin rate minus the event's
own pre-window mean. Pre bins test for diverging trends before the event.

**Robustness (pre-specified).**
- Controls only from games with no challenge.
- First challenge per game only.
- Controls restricted to fouls (no turnovers or goaltending).
- Windows of ±10 and ±40.
- Treated split by result: overturn, support, stands. Descriptive; no claim depends on
  one of these cells reaching significance.

**Power (computed from controls only, before the contrast was run).** A placebo
assignment of "treatment" at the treated rate inside the control group gives the
cluster-robust SE. Minimum detectable effect at 80% power, 5% two-sided (2.8 x SE):

| Outcome | Control pre rate | MDE (fouls/poss) | MDE (% of base) |
|---|---|---|---|
| d_all | 0.183 | 0.0049 | 2.7% |
| d_agg | 0.089 | 0.0035 | 3.9% |
| d_oth | 0.094 | 0.0036 | 3.8% |

For scale: 0.005 fouls/possession is about 0.1 foul over the 20-possession window.

**Interpretation rules.**
- Primary claim rests on `d_all`, 20-possession window, primary sample.
- A nonzero `treat` means the period around a challenge differs from the period around
  an ordinary call. It does not by itself separate "refs react to the challenge" from
  "challenged calls happen in unusual stretches of play." The pre-trend bins speak to that.

**Known limitations.**
- Challenged call type is unknown for most overturns, so the control mix of call types
  is not matched to the treated mix. The fouls-only control spec bounds this.
- Bonus status and individual foul trouble are not controlled in Q0.
- 26% of challenges fall in the late-game zone and are not studied here.
- Challenge counts are not yet validated against official.nba.com (blocked from here).

## Q1. Do refs make up for an overturn? (spec H2)

**Disclosure.** The Q0 descriptive split by result (already seen) motivated this test. Q1
fixes the controls, outcome, and decision rule before running the contrast, but it is not
blind to that pattern.

**Question.** After a challenge is overturned, does the challenger's net foul burden
(fouls on challenger minus fouls on opponent) rise relative to after a lost challenge?

**Events.** Coach's challenges outside the late-game zone with the challenger identified
(timeout row or reviewed call). Treated: overturn (3,288). Control: lost, support and
stands pooled (2,129). Same windows, exposure filter and possession rules as Q0.

**Outcomes.**
1. `d_net` (**primary**): change, post minus pre, in (challenger fouls - opponent fouls)
   per possession. Makeup predicts a positive coefficient.
2. `d_agg`, `d_oth`: the two components.
3. `d_net_def` (robustness): same, but each team's rate is computed only over its own
   defensive possessions. Immune to who has the ball when.

**Model.** Event-level OLS, SEs clustered by game:
`d ~ treat + period x clock-bucket + challenger margin bucket + season`
`+ d_offshare + team fouls in period (each team, capped at 6)`
`+ players in foul trouble (each team, capped at 3)`.
- `d_offshare`: change in the share of possessions with the challenger on offense.
- Team fouls and foul trouble are measured from the feed just after the review. Foul
  trouble: at least 2 fouls in Q1, 3 in Q2, 4 in Q3, 5 in Q4.
- **These controls are partly caused by the treatment** (an overturn can remove a foul).
  That is intended: the estimand is the effect *not* running through foul counts or
  possession order, which is what separates makeup behavior from mechanics.

**Robustness (pre-specified).** No mechanical controls (shows what they absorb); support-only
and stands-only controls; first challenge per game only; timeout-identified challengers
only; defense-only rates; windows ±10 and ±40.

**Power (from lost challenges only, placebo labels, rescaled to the real split).**

| Outcome | MDE (fouls/poss, 80% power) |
|---|---|
| d_net | 0.0093 (~10% of the 0.097 per-team base) |
| d_agg | 0.0064 |
| d_oth | 0.0068 |
| d_net_def | 0.0172 |

**Decision rule.** Makeup is supported if the primary `d_net` coefficient is positive with
a 95% CI excluding zero, and `d_net_def` has the same sign. If the primary holds but
`d_net_def` does not, report it as unresolved between makeup and possession mechanics.

**Not addressed here.** Which player the overturned call involved (subject-level foul
trouble) is unknown for most overturns; team-level foul-trouble counts are a proxy.

## Exploratory

### Q0-X1. Stoppage/timeout confound (added after Q0 results; not pre-registered)

Q0's dip is concentrated in the first 5 possessions after the event. Every challenge
brings a long stoppage and usually a timeout. Check: compare challenges with unchallenged
calls that have a non-challenge timeout at the same stoppage (`analysis/q0x_timeout_check.py`).
Also compare, within unchallenged calls, those followed by a timeout vs not.
Caveat: timeout-followed calls are not a clean control. Their pre-window bins oscillate
(media timeouts fall at fixed clock points), so read this as a diagnostic, not an estimate.
