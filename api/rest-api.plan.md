# Plan: REST API surface

`ARCHITECTURE.md` next-item 2. Design only; no handlers written yet.

Reviewed in `rest-api.asr.md`. **Three blockers changed this plan, and one of them removed a
whole endpoint class that the handoff assumed.** Read that file.

## Shape

`/v1` prefix. Cursor pagination, never offset. Errors as `application/problem+json`
(RFC 9457). Reads public, writes authenticated.

Client-minted UUIDv7 makes every `POST` naturally idempotent: re-posting an id that exists
returns the existing resource with `200`, not `409`. This is not a nicety. Connectivity at a
trailhead is exactly flaky enough that every write will be retried, and a retry that creates
a duplicate hike is a bug the user sees.

## The cost model drives the design

Deno Deploy bills per request, so the surface is designed around **not making requests**
rather than around resource elegance.

The lever is that **a revision's path is immutable**. A revision is never edited; an edit
creates a new revision. So path bytes can be keyed by revision id and cached forever:

```
GET /v1/revisions/{revisionId}/path
    Cache-Control: public, max-age=31536000, immutable
```

That turns the expensive payload into something each client fetches at most once, ever, and
a CDN serves to everyone else. It is why paths are not embedded in list responses.

## Reads

```
GET /v1/trails?lat=&lon=&precision=5&limit=50&cursor=
```
Proximity. Server geohashes the point, expands to the **9-cell net** (target plus 8
neighbours, per the non-negotiable), matches the generated prefix column by equality.
Returns summaries: `id`, `name`, `trailhead` (GeoJSON Point), `current_revision_id`.
**No paths.** `precision` accepts 5 or 6, matching the indexed columns.

The client diffs `current_revision_id` against its local cache and fetches only what it does
not have. That is the whole sync story for trail geometry on the read side.

```
GET /v1/trails/{id}                  trail + current revision metadata
GET /v1/trails/{id}/revisions        history, cursor over (created_at, id)
GET /v1/revisions/{id}               one revision, including description
GET /v1/revisions/{id}/path          GeoJSON LineString, immutable, cached forever
GET /v1/hikes/{id}                   one hike, with its ordered trail tags
GET /v1/accounts/{id}/hikes          one hiker's hikes, ordered by created_at
```

Ordering and cursors use server `created_at`, never the device-supplied `started_at`.

## Writes

```
POST /v1/trails                      create; body carries the client-minted trail id
                                     and its first revision, in one request
POST /v1/trails/{id}/revisions       propose an edit; requires parent_revision_id
POST /v1/hikes                       upload a hike (recorded or uploaded)
PUT  /v1/hikes/{id}/trails           replace the ordered tag list wholesale
```

`POST /v1/trails/{id}/revisions` returns **`409 Conflict`** when `parent_revision_id` is not
the trail's current revision. The body carries the current revision so the client can drive
its conflict UI without a second round trip. The server does not merge and does not pick a
winner; silently overwriting a path edit is forbidden.

`PUT` on tags rather than `POST`/`DELETE` per tag because the ordered list is the unit the
user edits, and because three requests to reorder a thru-hike is three billed requests.

## Sync

One endpoint, one request per trigger.

```
POST /v1/sync
```
Request: a cursor plus everything the client has queued. Response: an ack per submitted
item, server-side changes since the cursor, and a new cursor.

Per-item acks rather than whole-batch success, because a batch that fails atomically on one
bad item means a client with one poisoned record can never sync again.

Triggers are app foreground, reconnect, hike upload, and pull-to-refresh. **No poll loop.**

## Not in this API

**Tiles.** See ASR B1. The API serves no tile bytes, at any path.

**GPX parsing.** See ASR B2. The client sends GeoJSON; the server never parses an upload
format.

## Open

The sync payload's exact shape depends on the server-merges-versus-client-merges fork in
`docs/crdt-library-evaluation.md`. Specified here down to the envelope and no further.
