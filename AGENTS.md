# AGENTS.md

How work happens in this repo. Read `ARCHITECTURE.md` first; it holds the v1 decisions and,
more usefully, the alternatives that were rejected and why. This file is about process and
the principles those decisions came from.

---

## Repo map

Monorepo. The API, the client, and the schema move together.

```
ARCHITECTURE.md     v1 architecture. Decisions, rejected alternatives, deferred items.
AGENTS.md           This file.
api/                Deno Deploy REST API. TypeScript.
android/            Native Kotlin client. Gradle.
db/migrations/      Numbered, forward-only SQL. The schema's source of truth.
docs/               Design specs and research writeups.
```

**Why a monorepo.** The sync protocol is hand-rolled and the CRDT deltas have to agree on
both ends. A schema change, the endpoint that serves it, and the client code that consumes
it belong in one commit. The cost is two toolchains in one CI config and a heavy Android
build; we pay it to make client/server version skew impossible rather than merely managed.

**Consequence:** CI must be able to run `api/` checks without building `android/`, and vice
versa. Path-filtered jobs, not one monolithic pipeline.

---

## Organizational philosophy

**Record the decision with its rejected alternatives.** `ARCHITECTURE.md` is the model. A
decision without its discarded options is not a decision, it is a preference that has lost
its reasoning. When you make a call that closes off a path, write down the path you closed
and why. Six months from now the "why not" is the part nobody can reconstruct.

**Defer features. Do not defer the schema shape they need.** Trail merge and dedup are
deferred; revision history is built on day one because retrofitting it later is painful.
Apply the same test to anything new: if deferring the feature is cheap but the schema
change is expensive, build the schema now and leave the feature alone.

**Predictable cost per hiker is a requirement.** It is why Auth0 was rejected on per-MAU
pricing and why the sync guardrails exist. Any proposal that makes cost scale on something
other than actual user activity needs an explicit argument.

**Low ops burden is a hard constraint, not a preference.** Neon and Deno Deploy were both
chosen to avoid becoming an ops team. Proposals that add a service to operate carry the
burden of proof, and "it's only one more container" is not that proof. This is the reason
SuperTokens lost despite being the best fit on every other axis.

**Deferred is not forgotten.** The deferred list in `ARCHITECTURE.md` is a real list.
Add to it deliberately. When something comes off it, say so there.

---

## Architectural philosophy

**The server is deliberately dumb; the client does the geospatial work.** The server does
geohash prefix lookups and ships GeoJSON. The phone constructs spatial relationships,
renders, and snaps live position to a trail, because the phone has the full geometry
anyway. Resist the pull to move spatial logic serverside. Every time you do, you are
buying per-request compute on a platform that bills per request, to compute something the
client already can.

**Two problems get two solutions.** Hikes are personal, append-only, single-author, and
sync is "push what the server doesn't have." Trail revisions are shared, mutable, and need
CRDTs and a conflict UI. Do not unify them for elegance's sake. The split is the design.

**Don't buy a product for a problem you don't have.** PowerSync, ElectricSQL, CouchDB, and
four IAM platforms were all surveyed and all rejected because the problem collapsed before
the product was needed. Check whether the problem is still hard before reaching for the
thing that solves it.

**Storage format and query strategy are separate choices.** PostGIS geometry columns are
fine for storing paths. We are not querying against them. Conflating "how it's stored" with
"how it's found" is what made the original spatial design more complex than it needed to be.

### Non-negotiables

These are correctness constraints, not style. Violating them produces bugs that look like
data problems.

- **Geohash proximity queries must include the 8 neighbor cells.** Two points 10 metres
  apart on opposite sides of a cell boundary share no prefix. A naive prefix match silently
  misses trailheads near any boundary. Query the target cell plus its neighbors, always.
  Cell dimensions also vary with latitude, so precision is a tuned parameter, not a constant
  you pick once and forget.
- **Migrations are forward-only and numbered.** No editing an applied migration. The fix for
  a bad migration is another migration.
- **No background poll loop.** Sync fires on app foreground, reconnect, hike upload, and
  pull-to-refresh. Nothing else.
- **Sync calls are batched and push deltas only.** Never one request per changed record.
  Never re-pull a whole trail on reconnect.
- **Every write carries an `author_id`.** Reads are public, writes are not. Attribution is
  the only thing moderation tooling will have to work with when it eventually exists.
- **Never silently overwrite a path edit.** When a trail moved underneath an offline editor,
  that is a conflict UI, not a last-writer-wins resolution the user never sees.
- **Long-running work does not live in the API process.** Deno Deploy is stateless and
  edge-distributed per request. Large GPX/GeoJSON imports are fast or they are offloaded.

---

## Testing philosophy

**Tests are runnable, verifiable documentation.** That is their primary job. A test that
demonstrates how a thing is meant to be used, and fails when that stops being true, has
earned its place. A test that exists to raise a coverage number has not.

**Test orthodoxy never justifies worse production code.** If a testing approach demands that
production code be contorted — interfaces that exist only for mocks, dependency injection
threaded through call sites that have no other reason to be parameterized, indirection whose
only reader is a test — the testing approach is wrong. Change the test, not the design.

**Tests live as close to the code as the toolchain allows.**

- **Deno (`api/`):** `foo.ts` and `foo.test.ts` in the same directory. This is Deno's own
  convention, so it costs nothing.
- **Kotlin (`android/`):** Gradle's `src/main` / `src/test` split fights this. Mirror the
  package path exactly so the test file sits at the same coordinates in the parallel tree.
  Reconfiguring Gradle source sets for true collocation is possible but cuts against every
  tool in the Android ecosystem; not worth it. **This is a compromise, and it is the one
  place the collocation rule is not honored literally.**

**Write the test first when it clarifies the design, after when it documents the result.**
For geohash neighbor math, sync reconciliation, and CRDT merge behavior, writing the test
first is genuinely the faster path, because the failing case tells you what the interface
should be. For an HTTP handler whose shape you are still discovering, writing it first is
ceremony. Use judgment. Nobody is checking the order.

**Every bug gets a failing test before it gets a fix.** This is the one hard rule. A bug
that was worth fixing was worth reproducing, and the reproduction is the documentation of
why the fix looks the way it does.

### Data access: real Postgres, Neon branch per run

Tests that touch the database run against actual Postgres on a Neon branch created for the
run and dropped after. Not mocks, not an in-memory shim.

**Why.** Geohash index behavior, constraint violations, FK cascades, and the exact semantics
of a partial index are the bugs worth catching, and they are precisely the class that a
mocked repository cannot see. Branching is cheap and fast enough to make this practical, and
it is arguably the Neon feature that justifies choosing Neon.

**Cost accepted.** These tests need network and a Neon token. They are slower than unit
tests and they do not run on a plane. Keep the pure-logic suite (geohash math, CRDT merge,
GeoJSON parsing) free of database dependencies so there is always a fast suite that runs
anywhere, and let the database suite be the slower, more valuable one.

**Never point a test run at a shared branch.** Each run gets its own, or it does not run.

---

## Decided since the handoff

`ARCHITECTURE.md` lists these as open. They are not anymore. That document is the author's
prose and has not been edited; these are recorded here instead.

- **Orphan hikes: allowed.** A hike may have zero rows in `hike_trail`. Recording an unmapped
  route does not force trail creation first. Promote-to-trail is a later UI and API action
  and needs no migration, because the bridge table already makes the state expressible.
  Read paths must handle a trail-less hike; assume nothing.
- **Monorepo.** See repo map above.
- **Test data access against real Postgres on a per-run Neon branch.** See above.

---

## Working agreements

**Commits.** Explain why, not what. The diff already says what. A commit that closes off an
alternative should say which one.

**Migrations.** One migration per logical change. Name them `NNNN_short_description.sql`.
Every migration that adds a constraint to an existing table needs a note about what happens
to rows that already violate it.

**The wire contract.** The API defines it. `android/` consumes it. When they disagree, the
API is right and the client is broken. Keeping them honest is currently manual; if that
starts costing real time, generating the Kotlin types from the API's definitions is the fix,
not a hand-maintained second copy.

**Before adding a dependency,** check it against low ops burden and predictable cost. A
dependency that bills per user, requires a service to operate, or does not run on Deno
Deploy needs an argument, not just a benchmark.

**When you hit a real fork in the road, stop and surface it.** Frame it as a tradeoff with
the options and what each one costs. Do not pick silently and do not pick by defaulting.
