# WikiHike (working title) — Architecture Handoff

**Status:** v1 architecture decided. No code written yet.
**Date of decisions:** September 2026

---

## What the product is

A mobile app for hiking. Three things it does:

1. **Live hiking GPS.** Open-data topo maps, your position on the trail, works without cell service.
2. **Hike recording and upload.** Record a hike as you walk it, or upload a past recording.
3. **A wiki-style open trail database.** Anyone with an account can log a new trail or edit an existing trail's path and description. GeoJSON is the interchange format.

Android first (native Kotlin). iOS is a later maybe, not a v1 constraint.

---

## The stack, in one list

| Layer | Choice |
|---|---|
| Client | Native Kotlin (Android) |
| API | Deno Deploy, REST |
| Database | Neon (managed Postgres) |
| Spatial indexing | Geohash string column, not PostGIS query engine |
| Offline sync | Hand-rolled, CRDT-backed |
| Map tiles | Proxied third-party topo tiles for v1, self-hosted later |
| Auth | Passkeys primary, Wikimedia OAuth secondary |

---

## Decisions and why

### Native Kotlin over cross-platform

Background GPS tracking is the product, not a feature. Cross-platform frameworks get leaky exactly there. React Native's background location story for multi-hour backgrounded hikes is the weakest link in that ecosystem. Flutter with native location modules was a live option, but if you're writing native location code anyway, the cross-platform saving shrinks.

**Tradeoff accepted:** iOS means a second codebase later. Worth it for control over background location and battery behavior.

### REST over GraphQL

Spatial and bounding-box style queries fit purpose-built REST endpoints more naturally than they fit GraphQL. No strong need for flexible nested fetching.

### Deno Deploy for the API

Chosen after ruling out self-hosting the whole stack. The driving concern was not wanting to become an ops team if demand grows. Deno Deploy autoscales with zero server management and bills per request.

**Tradeoff accepted:** You don't control the runtime, region behavior, or scaling internals. Also, it's stateless and edge-distributed per request, so **long-running import jobs (large GPX/GeoJSON uploads) cannot live inside the API process.** They need to be fast or offloaded.

**Cost consequence:** billing is per request, so a chatty client costs real money. See "Sync traffic guardrails" below.

### Neon (managed Postgres) over self-hosted

Self-hosted Postgres on a VPS was considered and rejected. Same reasoning as above: backups, failover, updates, and scaling become your job. There was no specific requirement to have hands on the database itself.

Long-term cost was the main worry. The counter-argument accepted: hike and trail data is small. GeoJSON paths plus metadata for even a large national trail database is megabytes to low gigabytes. **The cost that actually scales with usage is map tile bandwidth, not this database.**

**Lock-in risk judged low:** it's ordinary Postgres, `pg_dump` gets you out.

### Geohash, not heavy PostGIS querying

This was a late simplification and it's an important one.

Original assumption: index trail path geometries and run spatial queries against them. Revised: **the indexed thing is the trailhead point, a single coordinate per trail.** Path geometry is stored and shipped to the client, but it is not what the database queries against.

That reduces "trails near me" to a geohash string prefix match. Nearby points share geohash prefixes, so proximity search becomes cheap text indexing.

**The division of labor:**
- **Server** does cheap geohash lookups, decides which trails are nearby, ships their GeoJSON.
- **Client** does the real geospatial work: constructing spatial relationships, rendering, snapping live position to a trail. The phone has the full geometry anyway.

**Consequence:** PostGIS is optional. It's fine for storing path geometry as a typed column, but you are not leaning on its query engine. Plain lat/long columns plus a geohash index would also work.

---

## Data model

```
trail
  id, name, trailhead_point, trailhead_geohash,
  current_revision_id, created_at

trail_revision
  id, trail_id, path (geometry), description,
  author_id, created_at, parent_revision_id

hike
  id, path (geometry), recorded_by,
  started_at, ended_at, source (recorded | uploaded)

hike_trail  (bridge)
  hike_id, trail_id, order
```

### Why revisions, not overwrites

Trails are append-only revision logs, same shape as MediaWiki. An edit creates a new `trail_revision` and moves `trail.current_revision_id`. Old revisions stay for history and rollback.

Merge and dedup of overlapping user-submitted trails is **explicitly deferred.** Anyone can log a new trail even if it duplicates an existing one. But the revision structure is exactly what merge logic will need later, and retrofitting revision history onto an overwrite schema is painful. So it's built correctly on day one even though the feature it enables is deferred.

### Why hikes and trails are separate tables

Posting a hike does **not** propose an edit to the trail. A hike is a GPS recording that references a trail. Editing a trail's canonical path or description is a separate wiki action. Two tables, FK relationship, no mutation of the trail by recording a hike.

### Multi-trail hikes

`hike_trail` is a many-to-many bridge with an `order` column, so a hike can be shown as "covered Trail A, then B, then C." Useful for thru-hikes and loop combinations. Cheap to keep, annoying to add later.

### No spatial validation on tagging

**The user tags which trails a hike covered. There is no path-matching algorithm in v1.** The user knows what trail they're on. Multiple trails means multiple tags.

This is a deliberate gap, not an oversight: nothing verifies that a hike's recorded path actually touches the trail it's tagged with. Data quality depends on user honesty. Revisit if it becomes a problem.

### Open question, unresolved

**Can a hike exist with no trail?** If someone records an unmapped route, is it forced to create a trail first, or can it be an orphan hike promoted to a trail later?

Leaning toward allowing orphans, since it matches how people actually hike. That requires `hike.trail_id` to be nullable (or zero rows in the bridge table) plus a "promote this hike to a new trail" UI action. **Not decided.**

---

## Offline sync

Local-first, optimistic. The app works fully offline and reconciles on reconnect.

### Why hand-rolled instead of a sync product

PowerSync and ElectricSQL were both considered. Both sit on Postgres, give the client a local SQLite database, and handle sync with conflict hooks. PowerSync is the more mature for mobile.

Rejected because the server side turned out simple enough not to need them. Once the spatial complexity collapsed into a geohash column, what's left is ordinary relational rows. Adding a managed sync service means a paid dependency, an opaque internal, and sync-rule configuration, for a problem that's now tractable directly.

### Why not CouchDB / PouchDB

This was seriously considered, since Couch-style replication is purpose-built for offline-first documents.

Rejected for two reasons:

1. **Conflict resolution doesn't actually solve the hard part.** Couch gives you document-level "here are two conflicting revisions, you resolve them." For a shared trail path edited by multiple people, you still write the merge logic yourself. Same problem, different wrapper.
2. **It means abandoning Postgres.** Couch-style databases have no geometry types and no efficient proximity queries. You'd likely end up running Postgres alongside it for the query side, and then you're syncing two databases to each other.

Also: managed Couch (Cloudant is the main option) is a niche enterprise-priced market. Managed Postgres is a commodity with real competition. Cheaper, almost certainly.

### The two tables sync differently

This split is the core insight. Don't force one strategy onto both.

**Hikes: trivial.** Personal, append-only, single author. No conflict is possible. Sync is "push whatever isn't on the server yet." No CRDT needed at all.

**Trail revisions: the hard case.** Shared and mutable, so two people editing the same trail offline is a real scenario. This is where CRDTs earn their keep:
- Description maps naturally to a text CRDT.
- Path is better modeled as a last-writer-wins register or add-only proposal per revision, **not** a character-by-character merge. A path edit is "propose a new version," not fine-grained text collaboration.
- Where a trail changed underneath an offline editor, surface it as a real choice in a conflict UI. Do not silently overwrite someone's path edit.

Library candidates: Automerge or Yjs. Not evaluated in detail yet.

### Sync traffic guardrails

Deno Deploy bills per request, so sync chattiness is a direct cost. Build these in from the start:

- **Batch sync calls.** Not one request per changed field or record.
- **Sync on explicit triggers:** app foreground, reconnect, hike upload, pull-to-refresh. **No background poll loop.**
- **Push deltas only,** never re-pull a whole trail's data on reconnect. CRDT deltas are naturally small; keep them that way.

Goal: cost proportional to actual user activity, which matches the platform's pricing shape.

---

## Map tiles

Open topo data: OpenStreetMap-derived, plus elevation data (SRTM or similar) for contours.

**Phasing decision: proxy a third-party provider for v1, self-host later.**

- **v1:** proxy something like OpenTopoMap or Thunderforest. Simplest possible integration, just tile URLs. Subject to their rate limits, uptime, pricing tiers, and attribution requirements.
- **Later:** self-host generated tiles (Tileserver GL, Tilemaker). Real upfront work, but marginal cost per user becomes bandwidth and storage you control.
- **Pragmatic middle path for the self-hosted phase:** generate tiles only for regions users actually hike, pre-baked or on demand. Avoids solving "host the entire planet's map data."

Rationale for phasing: don't invest in tile infrastructure before the app is validated. Usage patterns will tell you which regions matter.

**Offline tile caching is mandatory, not optional.** Cell service disappears exactly when the map is needed. This is a storage and cache-invalidation design problem in its own right, and it is not yet designed.

**This is the real long-term cost center.** Tile bandwidth, not the database.

---

## Auth

**Passkeys primary. Wikimedia OAuth secondary.**

### Why accounts at all

Reads are public. **Writes are gated by an account** so every revision has an `author_id`. Moderation tooling is deferred along with merge/dedup, but without attribution you have nothing to moderate with later. Anonymous editing was rejected on that basis. OSM's model: account to edit, no account to view.

### Why not Auth0

Per-MAU pricing. Ruled out on prior professional experience, not theory. **The explicit goal is a predictable dollar amount per hiker**, and per-MAU billing is the opposite of that.

### Why not SuperTokens

It was the most promising candidate. Genuinely open-core, self-hostable free at any scale, no per-MAU ceiling, and its core can create its tables inside your existing application Postgres, so it would have lived inside Neon alongside the trail data. Architecturally it embeds via backend SDKs rather than standing up a separate identity server, which suited this stack.

**Blocker: the SuperTokens Node SDK does not work with Deno.** SDKs exist for Node, Python, and Go only. Their documented workaround is running a separate Node service for auth behind a reverse proxy. That's an extra moving part and an extra thing to pay for and operate, for a problem this app doesn't really have.

Keycloak, Authentik, Ory, and Zitadel were surveyed. All are heavier than needed. Keycloak especially is enterprise IAM, Java-based, wrong shape for low ops burden.

### What was chosen instead

Both options are hand-rollable on Deno with no auth product in the middle, which puts **auth cost per hiker at essentially zero** beyond your own compute.

**Passkeys** — the mainstream path. First-class Android support via Google's Credential Manager API. No passwords to store, no reset flows, no credential-stuffing surface.

**Wikimedia OAuth** — "log in with your Wikipedia account." Thematically apt for a wiki-style trail database, and the open-data/OSM/Wikipedia user overlap is above average for this audience.

Confirmed supported and permitted: Wikimedia explicitly supports third-party apps using MediaWiki as an identity provider. You register a consumer at `Special:OAuthConsumerRegistration/propose` and OAuth admins review it.

Practical notes:
- **Budget several days for approval.** Before approval you can only test with your own Wikimedia account.
- Select the identity-verification-only scope. You don't need to read pages or act on the user's behalf.
- Do **not** check "this consumer is only for your username."
- Wikimedia reserves the right to disable your app at their discretion. Standard ToS language, but it means this can't be your only login method.

Neither is exotic. Confidence that both are achievable is high; neither was investigated to implementation depth.

---

## Explicitly deferred

Not oversights. Decisions to revisit.

- **Trail merge and dedup.** Anyone can create a duplicate trail. Revision schema is ready for it when it matters.
- **Moderation and anti-vandalism tooling.** Attribution exists; tooling does not.
- **Spatial validation of hike-to-trail tagging.** Pure user assertion.
- **Self-hosted tile infrastructure.** Proxy first.
- **iOS.**
- **Orphan hikes / promote-to-trail.** Genuinely undecided, see above.
- **Offline tile cache design.** Known to be mandatory, not yet designed.
- **CRDT library choice.** Automerge vs Yjs unevaluated.

---

## Next things to work on

1. Resolve the orphan-hike question. It touches schema nullability and UI.
2. REST endpoint design.
3. CRDT library evaluation: Automerge vs Yjs, specifically for Kotlin client interop.
4. Offline tile caching strategy.
5. Verify Deno compatibility for whatever passkey / WebAuthn server library gets picked.
