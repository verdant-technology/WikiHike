# CRDT library evaluation: Automerge vs Yjs

`ARCHITECTURE.md` next-item 3. The deciding axis it named is **Kotlin client interop**, and
that axis settles it.

**Recommendation: Automerge.** Not because it is the better CRDT. Because the Kotlin binding
exists, is official, and is published, and Yjs's is not.

**Confidence: high on the interop finding, low on the Deno Deploy risk below.** Neither was
taken to implementation depth.

---

## Kotlin interop, which is the whole question

### Automerge

- **`automerge/automerge-java`** — official, under the Automerge org. JNI wrapper over the
  Rust core, targeting Java 8+.
- **Published to Maven Central** as `org.automerge:automerge`. Latest observed `0.0.7`.
- Repo carries `android` and `android-test-app` modules and builds shared libraries for
  multiple Android ABIs, bundled into an AAR. Android is a supported target, not an
  aspiration.
- Kotlin-native (as opposed to Java) bindings and Kotlin Multiplatform are discussed but not
  shipped. From Kotlin you consume the Java API, which is fine and ugly in the usual ways.

**What the `0.0.x` version actually means:** pre-1.0 API, no stability guarantee, and no
documented statement of which Rust Automerge version a given release tracks. Budget for the
API changing under you. Documentation is "mostly just the API docs."

### Yjs

- **`y-crdt/ykt`** (Kotlin bindings for yrs) is **inactive**. Three commits total, and the
  README says so outright, pointing at `y-uniffi` instead.
- **`y-crdt/y-uniffi`** is the successor, built on Mozilla's UniFFI, which does generate
  Kotlin as well as Swift. It self-describes as WIP and states that not all Yrs/Yjs
  capabilities are exposed yet. The repository's documentation is Swift-forward.
- **No published Maven Central artifact found.**

**So using Yjs from Kotlin means owning a UniFFI binding pipeline**: generating bindings,
cross-compiling the Rust core for four Android ABIs, packaging an AAR, and re-doing it on
every upstream bump. That is a build-infrastructure project living inside a hiking app, and
it fails the low-ops-burden test in `AGENTS.md` on principle before it fails it in practice.

---

## What Automerge costs

Worth stating plainly, because the recommendation is not free.

- **Pre-1.0.** Expect breaking changes. Pin exactly, upgrade deliberately.
- **JNI and native `.so` files.** APK size grows and you care about ABI splits. Not a
  problem, but it is a thing on the list that was not there before.
- **Yjs is the more mature and faster implementation on the JS side**, with a far larger
  ecosystem. That advantage is real and it is almost entirely on the axis this project does
  not weight.

## What Automerge buys, beyond the binding

The shape `ARCHITECTURE.md` asked for maps cleanly:

- Description as a text CRDT → Automerge `Text`.
- Path as a last-writer-wins register or add-only proposal per revision, explicitly **not**
  a character-by-character merge → a scalar value holding the encoded geometry, versioned
  per revision.

Nothing here needs an exotic CRDT type. Both libraries would have served; only one of them
can be imported.

---

## The fork this evaluation uncovered

**Does the server run CRDT code at all?**

`AGENTS.md` says the server is deliberately dumb. Taken seriously, that has a consequence
nobody has decided yet, and it changes what the library risk even is:

**Option A — server merges.** The API loads Automerge, applies incoming deltas, merges, and
materializes `trail_revision`. Server is authoritative. Conflicts resolved in one place.
Requires Automerge running on Deno Deploy, which is **unverified** (see risk below).

**Option B — server stores, clients merge.** The API stores deltas as opaque blobs plus a
materialized snapshot written by whichever client last merged. Server never executes CRDT
code. Matches the dumb-server principle exactly, eliminates the Deno risk entirely, and
keeps per-request compute near zero, which is the cost shape the platform bills on.

Option B's cost is real: the server can no longer validate what it stores, the public read
API is serving a snapshot it did not compute and cannot verify, and a malicious or buggy
client can write a bad snapshot. That is a moderation problem in a system whose moderation
tooling is already deferred.

**This is a decision, not a detail, and it is upstream of the library risk.** It wants its
own plan and ASR before either path gets built.

---

## Risk: Automerge on Deno Deploy (unverified)

Only applies under Option A.

Automerge's JS package is WASM-backed. Modern Deno supports `npm:` specifiers, so
`npm:@automerge/automerge` plausibly works in a local `deno` process. **Deno Deploy is the
open question**, not Deno. The upstream issue tracking Deno releases
(`automerge/automerge#488`) is closed, but the closure does not document a resolution, a
supported import path, or a JSR package.

Do not treat this as working until it has been deployed. The SuperTokens finding in
`ARCHITECTURE.md` is the precedent: "there is an SDK" and "the SDK runs on our runtime" are
different claims, and the gap between them already cost this project its preferred auth
choice once.

---

## Next

1. **Decide Option A vs B first.** It may retire the risk below entirely.
2. If A: spike `npm:@automerge/automerge` on an actual Deno Deploy deployment. Load the
   module, build a doc, apply a delta, read it back. Half a day, and it is binary.
3. Either way: spike `org.automerge:automerge` in an Android module. Confirm the AAR
   resolves, the ABIs you need are present, and note the APK size delta.
4. Pin the version and record the Rust Automerge version it tracks, since upstream does not.

## Sources

- [automerge/automerge-java](https://github.com/automerge/automerge-java)
- [automerge-java: Kotlin multiplatform support? (issue #2)](https://github.com/automerge/automerge-java/issues/2)
- [Maven Repository: org.automerge](https://mvnrepository.com/artifact/org.automerge)
- [y-crdt/ykt](https://github.com/y-crdt/ykt)
- [y-crdt/y-uniffi](https://github.com/y-crdt/y-uniffi)
- [y-crdt/y-crdt: Looking for contributors! (issue #217)](https://github.com/y-crdt/y-crdt/issues/217)
- [automerge/automerge: Deno Releases (issue #488)](https://github.com/automerge/automerge/issues/488)
