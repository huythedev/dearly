# Security behavior and audit fixes

## Client encryption and account lifecycle

Updated web/iOS clients encrypt new journal titles/bodies, direct messages and companion passages. The API verifies signatures and ownership without receiving decryption keys. Recovery, historical plaintext limitations, fingerprint verification, download contents and deletion retention are described in the [privacy and recovery guide](ENCRYPTION.md). The [security test report](PRIVACY-AUDIT.md) records the isolated adversarial checks and their limits; this is not an independent cryptographic audit.

## Anonymous community stories

An anonymous community story uses the story's UUID as its displayed author alias. Private titles and unshared text stay with the author. Author replies use the same story alias. Anonymous stories do not expose matching eligibility or accept companion invitations; users connect through identified profiles instead.

**Hide this story** affects only that story for the reader. It does not add an account block, remove a named candidate, cancel invitations, or end a relationship. Account blocks apply to identified profiles/posts/comments and connections. They do not filter anonymous stories or their anonymous author replies, because doing so would let someone probe a named account to identify its anonymous writing. Readers can hide individual anonymous stories and report them to staff. Staff can identify reported accounts and restrict a violating post or suspend its account.

This separation closes the invitation-response and block-list correlation paths found in the audit. It cannot remove identifying details that authors put in their writing or information that readers already learned from an earlier identified publication. Previously disclosed account links cannot be undone by a code upgrade.

## Staff restrictions

A staff hide creates a durable restriction in `moderation_holds`, independently of the author's audience setting. It withdraws the public excerpt, deletes community comments/listening reactions, and preserves the journal body. Authors can save private edits. Publication to the community or a companion is denied until an authorized `staff.report.restore` action removes the restriction. Restoration is audited and leaves the entry private.

The v3 migration reconstructs these restrictions from earlier `report.hide` audit events. It also removes legacy pending anonymous invitations. Back up before upgrading and stop the older server before starting the new code.

## Management access

Management documents, staff list APIs, and staff mutations are restricted by the current server-side role. The web console also requires a fresh staff authorization response before displaying controls. Both clients check the role and its explicit grants; stale permission arrays alone do not expose Management. Account-bound web reads, immediate clearing after a denial, and resetting pending dialogs on permission changes prevent old staff screens from surviving account/role changes. See the [Management access audit](MANAGEMENT-AUDIT.md) for the verified scope and fixes.

## Request handling

The body reader enforces 256 KiB, a five-second idle deadline, a fifteen-second total deadline, and admission limits of 32 uploads overall and 8 per client IP. A rejected upload gets 429; a timed-out upload gets 408 and a closed connection. Reader slots are released on success, oversized input, disconnection, timeout, and cancellation. Body-free health/state reads do not consume the upload budget.

These limits begin after headers arrive. Use a front proxy with header/body deadlines and appropriate buffering, restrict origin access, and configure `--proxy-ips` only for trusted proxies so client-based limits use trustworthy addresses. Keep the single-worker deployment: the application counters are per process.

## Regression coverage

`backend/tests/test_security_regressions.py` exercises anonymous action responses and named-block side effects, persistent moderation/restoration, v2→v3 upgrades, malformed payload types, report cursors changing status, more than 20 gardens with equal timestamps, archive ownership, suspended content, upload deadlines/admission, and a real loopback HTTP slow-upload scenario. The existing v1 migration test still checks account/session/journal/report preservation.

Native tests cover the safe signed-out model, Gregorian UTC calendar, legacy fixture compatibility, anonymous invitation guard, independent anonymous story visibility, and archived-garden DTOs. GitHub Actions also runs the complete backend suite, static checks, a current dependency advisory scan, and an iPhone Simulator build/test job. Native device layout, production proxy configuration, and live TLS need separate validation.
