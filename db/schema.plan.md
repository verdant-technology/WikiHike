# Plan: initial schema

Migration `0001_initial_schema.sql`. Direct translation of the `ARCHITECTURE.md` data model
plus the decisions recorded in `AGENTS.md`.

Reviewed in `schema.asr.md`. **Read that before the migration; it changed this plan in five
places.**

## Scope

Four tables from `ARCHITECTURE.md` (`trail`, `trail_revision`, `hike`, `hike_trail`) plus
one the handoff does not list and the non-negotiables require: an `account` table, because
`trail_revision.author_id` and `hike.recorded_by` need a referent and "every write carries
an `author_id`" is not enforceable without one.

Out of scope: WebAuthn credential storage (belongs with the auth plan), CRDT delta storage
(blocked on the server-merges-vs-client-merges fork in
`docs/crdt-library-evaluation.md`), moderation, merge/dedup.

## Decisions this plan makes

**Geometry: PostGIS `geography` columns, not `jsonb` GeoJSON.**
The fork is real. `jsonb` means the read path is a straight column read with no conversion,
which is cheaper on a platform that bills per request, and it needs no extension. PostGIS
costs an extension dependency and an `ST_AsGeoJSON` call per read.

Choosing PostGIS anyway, for two reasons. Write-time validation is worth real money in a
wiki where anyone can edit, and `jsonb` will happily store a malformed LineString forever.
And spatial validation of hike-to-trail tagging is deferred, not abandoned — storing typed
geometry means un-deferring it needs no data migration, which is the "defer the feature, not
the schema shape it needs" rule applied exactly. We are still not querying against these
columns; storage format and query strategy stay separate choices.

**IDs: client-minted UUIDv7.**
This is forced by offline-first, and it is the decision most likely to be got wrong by
defaulting. A client that records a hike on a ridge with no signal must mint that hike's ID
before the server has ever heard of it, so server-side sequences are unusable for anything
a client creates. UUIDv7 over UUIDv4 because it is time-ordered, which keeps index locality
and stops the primary key from scattering writes across the btree.

**`source`: `text` with a `CHECK`, not a Postgres `enum`.**
Same information, and adding a value later is a one-line migration instead of an
`ALTER TYPE`.

**Timestamps: `timestamptz`, everywhere, no exceptions.**

## Table sketch

```
account            id, display_name, created_at
trail              id, name, trailhead_point, trailhead_geohash,
                   current_revision_id, created_at
trail_revision     id, trail_id, path, description,
                   author_id, parent_revision_id, created_at
hike               id, path, recorded_by, started_at, ended_at, source, created_at
hike_trail         hike_id, trail_id, ordinal
```

`hike` has no `trail_id`. The bridge is the only link, and zero rows in it is an orphan
hike, which is legal. That is the whole implementation of the orphan decision.

## Proximity index

Store the full precision-12 geohash. Query by exact match on a shorter prefix rather than
`LIKE`, and include the 8 neighbour cells per the non-negotiable.

## Open

Migration runner. Files stay plain `.sql` so the choice stays open.
