# Dearly roadmap and responsibilities

## Available now

The iOS app connects to a single-node backend with accounts/passwords/sessions, API permissions, SQLite persistence, matching gated by operator-reviewed birth dates, foreground synchronization, journal/chat/garden pagination, server reports, moderator/admin screens, CLI role grants, audit logs, and backups. English is the source/default language with Vietnamese translations. System/Light/Dark appearances include a night garden.

## Before a real pilot

- Build/run XCTest and complete all flows on iPhone, including keyboards, unreliable networks, foreground/background transitions, session expiry, Dynamic Type, and VoiceOver.
- Run the backend on each target OS; configure HTTPS, a stable database path, backup/restore, and an OS account with minimal privileges.
- Design age-verification and consent procedures for the pilot. The CLI flag records manual review rather than automatic document verification. Confirm the product's check-in timezone; the current implementation uses shared UTC.
- Assign report coverage, violation handling, guidance for sensitive cases, and an appeals process. Staff report screens exist; automatic message filtering and user appeals do not.
- Add account management/deletion/export, password changes, session revocation across devices, and email/recovery. The username/password prototype is not a complete identity system.
- Define journal/chat/report retention, backup operations, and administrator access. Server data is stored in SQLite without end-to-end encryption.
- Measure performance at expected load; move to a server database/repository and per-user invalidation when multiple nodes are required.

## Future extensions

Optional challenges; memories approved by both people; discreet push notifications; longer community/companion journal history; iPad layouts; delta synchronization or WebSockets when lower latency is needed.

## Two-person team

| Person | Ownership | Evidence |
|---|---|---|
| Engineering | SwiftUI, API, permissions, database, tests, deployment/backups | PRs, architecture, test results, demos |
| Product/research | Interviews, app copy, test scenarios, feedback synthesis | Anonymized documents, issues, designs, test reports |
| Both | Scope, change review, contributions and limitations | Decision log, changelog, README credits |

Suitable nontechnical issues include whether testers understand the three sharing levels, the difference between hiding an anonymous story and blocking a profile, pressure from streaks, and onboarding improvements from feedback. Use synthetic content for sensitive test flows.
