# Administer Dearly

[All guides](README.md) · [Setup](SETUP.md) · [Hosting and backups](DEPLOYMENT.md)

Use the staff console to review reports and manage eligible accounts. New accounts always start as regular users; create your first administrator from the backend host.

## Create your first administrator

1. Create an account through the app.
2. On the server, run the command below, replacing `YOUR_USERNAME` with that account's username.
3. In the app, use **Sync now** or wait for the next sync. On iOS, open your avatar → **Dearly management / Quản lý Dearly**. On web, open **Management**, or **Settings → Management** on mobile.

For Docker, run from the repository root:

```bash
docker compose exec backend python run.py set-role --username YOUR_USERNAME --role admin --reason "Initial administrator"
```

For a Python-only backend, run from `backend`:

```bash
# macOS / Linux
.venv/bin/python run.py set-role --username YOUR_USERNAME --role admin --reason "Initial administrator"
```

```powershell
# Windows PowerShell
.\.venv\Scripts\python.exe run.py set-role --username YOUR_USERNAME --role admin --reason "Initial administrator"
```

For a custom database, put `--db /path/to/dearly.sqlite3` **before** `set-role`, or use the same `DEARLY_DB` environment variable as the server. The CLI can also set `--role moderator` or `--role user`. There is no default admin password or public admin-registration endpoint. Changes appear on the next sync; use **Sync now** in settings if needed. The last active admin cannot be demoted or suspended.

## Access to Management

Management is available only to signed-in moderators and admins. Regular members do not see its menu entry and cannot open its URL or APIs. If your session has expired, open the normal Dearly address and log in first.

Dearly checks your current server permissions before opening the console. Removing staff access closes its controls; changing roles also closes pending management forms. A moderator can still verify reviewed ages, while role changes, suspension, and the audit log remain admin permissions.

When installing this access-control update, rebuild **both** Docker services after pulling the latest code:

```bash
docker compose up -d --build frontend backend
```

For the technical findings and regression coverage, see the [Management access audit](MANAGEMENT-AUDIT.md).

## Staff roles

| Function | User | Moderator | Admin |
|---|:---:|:---:|:---:|
| Personal journals, community, companions, garden, block/report | ✓ | ✓ | ✓ |
| Read reports and their reported public excerpts | — | ✓ | ✓ |
| Mark reports open, reviewed, or dismissed with a note | — | ✓ | ✓ |
| Restrict/restore sharing of a reported community post | — | ✓ | ✓ |
| Search accounts; review birth dates and verify age | — | ✓ | ✓ |
| Suspend/restore users and moderators | — | — | ✓ |
| Assign/remove moderator access | — | — | ✓ |
| Read the administration audit log | — | — | ✓ |
| Grant/revoke admin or modify an admin account | Server CLI only | Server CLI only | Server CLI only |

Only the server CLI can grant/revoke admin or change an admin account. Admins can assign/remove moderator access in the app. Access is checked on every request, so a role change takes effect without waiting for a new login.

## Reports and account actions

Staff access does not allow browsing other people's private journal bodies or chat transcripts. A report about a public post retains only its published excerpt as evidence, including after the author withdraws/deletes that post; authorized staff can identify the reported account. Hiding a post preserves its author's private journal, removes community comments, and restricts further sharing until staff allow it again. Private edits remain available. Account suspension revokes sessions and ends connections while keeping garden rewards; restoring an account requires a fresh login. Staff mutations and CLI administration record the actor and reason in the audit log. See the [backend guide](../backend/README.md#roles-and-the-in-app-staff-console) for migration and operational details.

## Age verification

A new account can use journals and community before age review. To unlock companion matching, a moderator or administrator can review the account in the app or web staff console:

1. Open **Dearly management / Management → Accounts** and search for the member.
2. On iOS, open the account and find **Age verification**. On web, choose **Verify age**.
3. Review the birth date outside the app, enter the reviewed date, and provide a reason.
4. On iOS, choose **Confirm reviewed age** and confirm the change. On web, choose **Save decision**. The member sees the verified status on their next sync.

Every verification records the reviewer and reason. Moderators can verify age but cannot change roles, suspend accounts, or read the audit log. Staff cannot verify their own account or an admin account through the app; use the server CLI for those accounts. An operator can also record a reviewed birth date with the CLI.

For Docker, from the repository root (replace the username and date):

```bash
docker compose exec backend python run.py verify-age --username USERNAME --birth-date YYYY-MM-DD --reason "Birth date reviewed"
```

This records manual review; it does not automatically verify identity documents. Correcting a birth date ends existing connections so eligibility can be checked again; confirming the same date preserves them. Under-18 accounts connect only with other under-18 accounts at most one year apart; adults form a separate group.

For Python-only commands, report handling, suspension/restoration, and migration details, see the [backend administration reference](../backend/README.md#age-verification-and-administration). For what a regular user sees, read the [companion guide](USAGE.md#connect-with-a-companion).
