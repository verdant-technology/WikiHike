# Q0 findings: challenges vs. unchallenged calls

Design and rules: `ANALYSIS_PLAN.md`, section Q0. Numbers: `estimates.csv`,
`event_study.csv`, `exploratory_timeout.csv`.

## Pre-registered result

Over the 20 possessions after a challenge, foul rate changes by **-0.0050 fouls per
possession** relative to the change after an unchallenged call (95% CI -0.0087 to -0.0013,
p = 0.008). That is 2.7% of the baseline rate of 0.183, or about 0.1 foul over 20
possessions. It sits right at the pre-computed minimum detectable effect.

- Holds across control choices (games with no challenge, fouls-only controls) and
  windows (±10: -0.0060; ±40: -0.0039). Weaker with first challenge only (-0.0037, p = 0.09).
- Pre-trends are flat: all four pre bins are within ±0.003 and none significant.
- The effect is almost all in possessions +1 to +5 (-0.013, about 7% of base). Bins after
  that are near zero. If real, it is short-lived.
- Split by team: the drop is in fouls by the non-challenging team (-0.0044); the
  challenging team is flat (-0.0010).

## Exploratory: it is probably the stoppage, not the challenge

Unchallenged calls followed by a timeout show a larger post-event dip (-0.0090 vs. calls
with no timeout). Against that comparison group the challenge effect turns slightly
*positive* (+0.0046, p = 0.055). The timeout comparison has unstable pre-trends, so it does
not give a clean estimate, but it removes the case for a challenge-specific drop. The best
current reading: play right after any long stoppage has fewer fouls, and challenges are
long stoppages.

## Descriptive split by result (pre-registered as descriptive only)

| Result | n | Fouls on challenger | Fouls on opponent |
|---|---|---|---|
| Overturn | 3,406 | +0.0039 | **-0.0090** |
| Support | 972 | -0.0054 | +0.0028 |
| Stands | 1,166 | **-0.0117** | +0.0031 |

The team that wins the review gets fewer favorable calls afterward, and the team that
loses gets more. That looks like makeup calls (the spec's H2). Because it compares
challenges with challenges, the stoppage confound cancels. But two mechanical
explanations fit the same pattern and must be ruled out first:

1. **Foul trouble.** An overturn often removes a foul from a challenger's player, who can
   then play more aggressively. A lost challenge leaves the foul in place.
2. **Who has the ball next.** An overturn often flips possession. Defenders commit most
   fouls, so the first few possessions' offense/defense split shifts by team.

## Limitations

- 26% of challenges are in the last 2:00 or OT and are excluded.
- Bonus status and player foul counts are not controlled in Q0.
- Challenge counts are not yet validated against official.nba.com totals.
