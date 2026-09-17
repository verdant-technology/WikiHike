# ASR: initial schema

Reviews `schema.plan.md` and `migrations/0001_initial_schema.sql`.

Open blockers: **none.** All five found against the plan were fixed before the migration was
written. Findings are kept because they are the reason the migration looks the way it does.

---

## Plan review — blockers (all resolved)

**B1. The FK between `trail` and `trail_revision` is circular and cannot be satisfied.**
`trail.current_revision_id` points at a revision; `trail_revision.trail_id` points back at
the trail. Neither row can be inserted first. The plan did not notice this at all.
*Resolved:* the constraint is `DEFERRABLE INITIALLY DEFERRED`, so both rows insert in one
transaction and the check happens at commit. Because clients mint UUIDs, the trail can be
written with `current_revision_id` already populated, which lets the column stay `NOT NULL`
— a trail with no revision is not a state that should exist even transiently across commits.

**B2. `current_revision_id` can point at a different trail's revision.**
A plain `REFERENCES trail_revision(id)` enforces that the revision exists, not that it
belongs to this trail. Silent data corruption, and exactly the class of bug a mocked data
layer never sees. *Resolved:* `UNIQUE (id, trail_id)` on `trail_revision`, and the pointer
is a composite FK on `(current_revision_id, id)`. Same fix applied to `parent_revision_id`,
which had the same hole.

**B3. Prefix matching does not use an index the way the plan assumed.**
"Query by exact match on a shorter prefix" skipped over where the shorter prefix comes from.
`WHERE substr(geohash,1,5) = $1` is unindexed without an expression index, and the obvious
alternative, `LIKE 'abc%'`, only uses a btree index under a `C` collation or a
`text_pattern_ops` index — a trap that works in dev and silently seq-scans in production.
*Resolved:* stored generated columns at precisions 5 and 6, each plainly indexed, queried
with `=` / `IN`. No collation subtlety, no op-class to remember. Two precisions because
`AGENTS.md` calls precision a tuned parameter, and this makes retuning an endpoint change
rather than a migration.

**B4. `PRIMARY KEY (hike_id, trail_id)` makes out-and-backs unrepresentable.**
The plan's bridge sketch implied it. An out-and-back, a figure-eight, or any loop that
re-enters a connector trail covers the same trail twice, and `ordinal` exists precisely to
express that. *Resolved:* the key is `(hike_id, ordinal)`. A trail may repeat within a hike.

**B5. `started_at` is device time and cannot be trusted for ordering.**
It comes from a phone that has been offline for eight hours and may have a wrong clock; a
client can set it to anything. If server-side ordering or pagination keys off it, a bad
clock reorders other people's data. *Resolved:* `created_at` defaults to `now()` on the
server and is kept distinct from the device-reported window. **Ordering and pagination use
`created_at`. `started_at` is display data.** This is a rule about query code, not schema,
so the schema cannot enforce it — see S5.

## Plan review — should-fix (open, carried)

**S1. `account` carries no credential material.** Deliberate; WebAuthn credentials belong
with the auth plan. Flagged so the next person does not read the gap as an oversight.

**S2. `ordinal` is not constrained to be contiguous or zero-based.** `(0,1,5)` is legal.
Enforcing contiguity needs a trigger or a deferred constraint and buys little. Sort by it,
do not count with it.

**S3. `description` is unbounded.** A vandalism vector in a system whose moderation tooling
is deferred. A length cap is a one-line migration whenever that stops being theoretical.

**S4. Finding orphan hikes is an anti-join.** `NOT EXISTS` against `hike_trail`. Fine at
this data size, and the direct consequence of choosing the plain orphan option over the
status-column one. Revisit if promote-to-trail tooling makes it a hot query.

**S5. B5's fix is a convention, not a constraint.** Nothing stops a future query ordering by
`started_at`. The honest mitigation is that it is written down here and in the migration
comments. A check constraint bounding `started_at` against `created_at` was considered and
rejected: legitimate uploads of old GPX files have arbitrarily old start times.

## Plan review — noted

**N1. `uuidv7()` is built in from Postgres 18.** On an earlier Neon version the server-side
default is unavailable. Low impact, because clients mint IDs anyway and the default only
serves server-created rows. Confirm Neon's version before relying on it.

**N2. `geography` over `geometry` is a real choice.** Spherical math, correct distances
without picking a projection, fewer available functions. Right for a global trail database;
worth knowing if a needed function turns out to be geometry-only.

**N3. `ON DELETE RESTRICT` on `hike_trail.trail_id`** means a trail with recorded hikes
cannot be deleted. Intentional. Deleting a trail should be a wiki action with a policy, not
a cascade.

## Diff review

Reviewed `0001_initial_schema.sql` against the plan. No blockers. The migration adds the
geohash alphabet `CHECK` (base32 excluding `a`, `i`, `l`, `o`), which the plan did not
specify and which turns a malformed geohash into a write failure instead of a trail that
can never be found by proximity search.

**Not verified:** this has not been executed against a real Postgres. Per `AGENTS.md` the
schema's first test is a per-run Neon branch, and until that exists the migration is
reviewed, not proven.
