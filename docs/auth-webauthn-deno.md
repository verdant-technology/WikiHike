# Deno compatibility for passkeys and Wikimedia OAuth

`ARCHITECTURE.md` next-item 5: verify Deno compatibility for whatever passkey / WebAuthn
server library gets picked, before the SuperTokens surprise happens twice.

**Recommendation: SimpleWebAuthn, imported from JSR.** Deno is a documented, first-class
target, not a community port.

**Confidence: high for the passkey half. Medium for the Wikimedia half**, which was checked
less deeply and has one unresolved protocol question.

---

## Passkeys: SimpleWebAuthn

`@simplewebauthn/server` (v13.x observed) lists **Deno alongside Node, Bun, and Cloudflare
Workers** as supported runtimes. Cloudflare Workers being on that list is the useful signal:
a library that runs there is built against Web Crypto and the standard platform surface
rather than Node built-ins, which is exactly the property Deno Deploy needs.

This is the structural difference from SuperTokens. SuperTokens' Node SDK assumes Node.
SimpleWebAuthn assumes the web platform. That is why one of them requires a sidecar service
and the other is an import.

### Import path, which has changed

`https://deno.land/x/simplewebauthn/...` is **no longer supported**. Use JSR:

```ts
import { generateAuthenticationOptions } from "jsr:@simplewebauthn/server";
```

Requires a recent Deno (their notes reference v2.4.x and higher for the current
NPM-and-JSR install story; Deno's native JSR support landed in 1.42). Any tutorial you find
using a `deno.land/x` URL is stale — check the date before copying it.

### What still needs verifying

Runtime support being documented is not the same as this project's specific ceremony
working on Deno Deploy. What is genuinely unverified:

- Attestation verification. Some attestation formats historically pulled in heavier crypto
  than Web Crypto provides. v13 is reported to handle this, but it was not confirmed.
  **Mitigation that is probably right anyway:** for a hiking app, request `none`
  attestation. You do not need to know the make and model of the authenticator, and asking
  for attestation you do not use is a privacy cost with no benefit.
- Challenge storage. WebAuthn needs a short-lived server-side challenge between the options
  call and the verification call. Deno Deploy is stateless and edge-distributed per request,
  so **the challenge cannot live in process memory** — a user can and will hit two different
  isolates across the two halves of one ceremony. It goes in Postgres with a TTL, or in a
  signed stateless token. This is an architectural consequence of the platform choice, not a
  library concern, and it is the most likely thing to be got wrong.

### Spike

Deploy a two-endpoint Deno Deploy service doing registration and authentication against a
real Android device using Credential Manager. Half a day, and it retires the last open risk
in the auth decision.

---

## Wikimedia OAuth

No library needed. This is a plain OAuth flow against Wikimedia's endpoints, which is most
of why it is cheap.

**Unresolved:** Wikimedia has historically offered both OAuth 1.0a (the original MediaWiki
extension) and OAuth 2.0. **Use OAuth 2.0** if the consumer registration offers it. OAuth
1.0a requires request signing, which means an HMAC implementation and a canonicalization
step that is tedious to get exactly right; OAuth 2.0 over HTTPS needs none of that. This
was not verified against the current registration form, and it is worth checking **before**
submitting the consumer proposal, because the choice is made at registration time and
approval takes days.

The operational notes already in `ARCHITECTURE.md` stand: identity-verification-only scope,
do not check "only for your username," budget several days for approval, and it cannot be
the only login method because Wikimedia reserves the right to disable the consumer.

---

## Why this matters beyond auth

Both halves confirm the constraint `AGENTS.md` records as a non-negotiable, from a direction
that is easy to miss: **Deno Deploy is stateless per request.** For imports that means work
must be fast or offloaded. For auth it means a WebAuthn challenge has nowhere to live unless
you give it one. Any flow with a server-side step between two client calls has this problem.
It will come up again in sync.

## Sources

- [MasterKale/SimpleWebAuthn](https://github.com/MasterKale/SimpleWebAuthn)
- [@simplewebauthn/server docs](https://simplewebauthn.dev/docs/packages/server)
- [SimpleWebAuthn CHANGELOG](https://github.com/MasterKale/SimpleWebAuthn/blob/master/CHANGELOG.md)
- [simplewebauthn on JSR](https://jsr.io/@simplewebauthn)
