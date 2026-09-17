# ASR: REST API surface

Reviews `rest-api.plan.md`. Design-stage only; there is no diff to review yet.

Open blockers: **none.** Three were found and resolved. Two of them deleted functionality
the handoff assumed would exist, which is the more useful kind of finding.

---

## Blockers (all resolved)

**B1. Proxying tiles through the API inverts the entire cost model.**
`ARCHITECTURE.md` says proxy a third-party tile provider for v1, and the obvious reading is
a `GET /v1/tiles/{z}/{x}/{y}` endpoint. That endpoint would be, by an enormous margin, the
most-requested thing in the system. A single map screen is dozens of tiles; a pan is dozens
more. On a platform that bills per request, routing tiles through the API means the cheapest
byte in the product becomes the most expensive line on the invoice, and it scales with
scrolling rather than with hiking. Every other guardrail in `ARCHITECTURE.md` — batch sync,
no poll loop, deltas only — is aimed at shaving requests that this one endpoint would dwarf.

*Resolved:* **the API serves no tiles.** The tile path does not touch Deno Deploy.

This does not decide *how* tiles get served, and that decision is now load-bearing:

- **Client talks to the provider directly.** Simplest, zero marginal cost to us. The API key
  ships in the APK and is extractable; providers generally expect this and rate-limit per
  key and per referrer. Check the provider's terms before assuming it is allowed.
- **CDN in front of a tile origin that is not the API.** Keeps the key server-side. Adds a
  thing to operate, which `AGENTS.md` says needs an argument.
- **Bandwidth-priced host for the tile path only.** Matches the cost shape, since tiles are
  a bandwidth problem and not a compute problem. Closest to where the self-hosted phase ends
  up anyway.

Recommendation is the first for v1, on the grounds that it is the only one that adds nothing
to operate. **This wants your call, not mine.**

**B2. Server-side GPX parsing cannot exist on this platform, and does not need to.**
`ARCHITECTURE.md` flags that long-running imports cannot live in the API process and will
need offloading. The plan inherited that and was heading toward an upload-and-job endpoint,
which means a queue, a worker, a job table, and status polling — polling being the thing
that is explicitly banned, on a platform chosen to avoid operating workers.

The offload is avoidable. **The client already has the file, already has to parse GeoJSON,
and already does the geospatial work by design.** Parsing GPX in Kotlin is ordinary work.

*Resolved:* the API accepts GeoJSON only. The client parses whatever the user picked. The
entire import-job apparatus is deleted before it is built, along with the `ARCHITECTURE.md`
concern that motivated it.

*Cost accepted:* GPX parsing is now written twice if iOS ever happens, and a malformed file
produces a client-side error message rather than a server-side one. Both are cheaper than
operating a job queue.

**B3. An atomic sync batch lets one bad record permanently wedge a client.**
The first pass had `POST /v1/sync` succeed or fail as a unit. A client holding one record
the server rejects — a schema drift after an app update, a hike referencing a trail someone
deleted — retries forever, fails forever, and every subsequent change queues behind it. The
user's symptom is "the app stopped syncing," with no way out but reinstalling.

*Resolved:* per-item acks. Good items land, bad items come back with a reason, and the
client can quarantine them and keep going.

## Should-fix (open, carried)

**S1. `PUT /v1/hikes/{id}/trails` has no optimistic concurrency.** Two devices editing tags
means last write wins silently. Tolerable now: tags are personal data with one author, so
the conflict is a user with two phones. An `If-Match` on an ETag is the fix when it matters.

**S2. `precision` is a client-supplied enum of exactly two values.** Honest, and it leaks a
storage detail into the public API. Worth reconsidering as `radius_m` mapped server-side,
which would let precision be retuned without breaking clients.

**S3. Nothing bounds `limit`.** Specify a maximum and enforce it, or the proximity endpoint
becomes a way to ask for every trail in a region in one request.

**S4. `POST /v1/trails` creating a trail and its first revision in one request** is not
strictly RESTful and is right anyway, because a trail with no revision is not a legal state
in the schema. Noted so nobody "fixes" it into two requests.

## Noted

**N1. Immutable path caching depends on revision ids never being reused.** They are UUIDs
and revisions are append-only, so this holds. It would stop holding the moment anyone adds a
revision-editing or squashing feature, and the cache would then serve stale geometry
indefinitely with no way to purge it. Worth remembering before any such feature.

**N2. The 409 body carries the current revision.** Saves a round trip on the common
conflict path, at the cost of a fatter error response. Right trade on a per-request platform.

**N3. Ordering by `created_at` is inherited from the schema ASR (B5)** and is the same
convention, restated at the API boundary where it is easy to violate by accident.
