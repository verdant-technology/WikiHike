# Q1 findings: makeup calls after an overturn

Design and decision rule: `ANALYSIS_PLAN.md`, section Q1. Numbers: `estimates.csv`,
`balance.csv`, `exploratory_decompose.csv`.

## Pre-registered result: not supported, but the primary spec is flawed

Primary `d_net` = -0.0030 fouls/possession (95% CI -0.0097 to +0.0036, p = 0.37).
Under the decision rule, makeup is not supported.

## Raw pattern

Pre-window rates are balanced across arms. Post-window rates cross over:

| Fouls per possession | Lost: pre | Lost: post | Overturn: pre | Overturn: post |
|---|---|---|---|---|
| On challenger | 0.100 | 0.093 | 0.095 | 0.103 |
| On opponent | 0.104 | 0.109 | 0.100 | 0.094 |

Without mechanical controls, `d_net` = +0.024 (CI +0.017 to +0.032), about 25% of a
team's base rate.

## Exploratory: one control erases it, and that control is suspect

| Controls added | d_net | 95% CI |
|---|---|---|
| none | +0.024 | +0.017 to +0.032 |
| possession share | +0.024 | +0.017 to +0.032 |
| players in foul trouble | +0.020 | +0.012 to +0.027 |
| possession + foul trouble | +0.020 | +0.012 to +0.027 |
| team fouls in period | -0.002 | -0.009 to +0.004 |
| all (primary) | -0.003 | -0.010 to +0.004 |

Possession order and foul trouble explain little. Team fouls explain everything, but:

- Challenger team fouls differ by 0.78 between arms (2.94 lost vs. 2.16 overturned). That
  gap is the reviewed foul itself: it stays on the books when the challenge is lost and is
  deleted when it is overturned. It is not a difference in how the game was going.
- Team fouls correlate 0.53 with the pre-window foul rate, so the model learns a strong
  negative slope (more fouls before, fewer after) from pre-window variation. That slope
  is then applied to the 0.78 gap, which has nothing to do with the pre-window.
  This is a bad control, and the primary spec was wrong to include it in this form.

## Candidate mechanical story still open

A lost challenge leaves the challenger one team foul closer to the penalty. Teams in the
penalty may defend more cautiously. That could lower challenger fouls after a loss. It
does not explain the opponent side (fewer opponent fouls after an overturn).

## Proposed fix (Q1b, to pre-register)

- Replace "team fouls after review" with team fouls **before** the reviewed call
  (identical in both arms by construction).
- Add possession-level **penalty status** for each team, to capture the bonus channel
  directly.
