# Manual checks on Xcode / iPhone

These device checks were not run in the source-generation environment. Record actual results after execution. Use separate test accounts/devices for each participant.

| Scenario | Expected result | Actual result |
|---|---|---|
| First launch | Login screen; restores a valid Keychain session if present | Not run |
| New journal | Only me is the default audience | Not run |
| Share a passage absent from the entry | Refuses to save and explains why | Not run |
| Anonymous publication | Shows only the chosen passage without title, nickname, or profile link | Not run |
| Withdraw a post to private | Disappears from the other account's feed | Not run |
| Responses disabled | Other users have no response field | Not run |
| Invitation without mutual consent | Chat remains closed | Not run |
| Recipient opens an invitation | Short profile and accept/decline controls appear | Not run |
| Ages 17 and 22 | Cannot send/receive invitations, including from the feed | Not run |
| Both people accept | Both see the same connection and chat | Not run |
| Send chat and view as the other participant | Correct sender and connection | Not run |
| One participant checks in twice | No complete day without the other participant | Not run |
| Both participants check in | Counts exactly one day | Not run |
| Miss a day | Streak ends; rewards remain | Not run |
| Pause the garden | Check-in unavailable; rewards remain | Not run |
| Leave/block | Chat closes, garden is saved, old journals are not shared into a new connection | Not run |
| Report | Sent to the server and appears in the staff queue | Not run |
| Close/reopen app | Entries, chat, connections, and gardens are restored | Not run |
| Enable VoiceOver | Send, compose, check-in, and garden illustrations have labels | Not run |
| Small iPhone with large text | Important controls remain visible and content scrolls | Not run |


# Online checks on Xcode/iPhone

| Scenario | Expected result | Actual result |
|---|---|---|
| Windows/Linux server and iPhone on the same LAN | Correct host IP URL; app requests Local Network access | Not run |
| Register/login/logout | Keychain token; confirmed server logout returns to login | Not run |
| Unverified age | Journals available, matching blocked, verification guidance shown | Not run |
| Two devices with different accounts | Entries/invitations/chat/check-ins synchronize through the server | Not run |
| Close/reopen app | Restores Keychain session and loads fresh online state | Not run |
| Lose network after POST | Retry with the same ID avoids duplicate messages/journals; clear status | Not run |
| Browse old journals/messages | Pagination enforces ownership without mixing accounts | Not run |
| Anonymous post | No invitation control; hiding leaves suggestions/connections intact; profile blocks do not filter anonymous posts | Not run |
| UTC day boundary | Check-in/streak matches the server date regardless of device timezone | Not run |
| Release build | HTTPS with trusted certificates only | Not run |

# Roles and appearance checks (v0.3)

Use synthetic accounts/content for these checks and run the updated backend with the updated iOS build.

1. Create a regular user, moderator, and admin. Grant admin with `run.py set-role --username NAME --role admin --reason "Pilot operator"` on the backend host. Confirm the management entry appears under the avatar after state sync; a normal user has no entry.
2. As admin, search an account and assign moderator. On that account's existing session, confirm the report queue opens and account/audit screens remain unavailable. Attempt staff API requests with a normal user's token and expect 403.
3. Publish an anonymous excerpt from a longer journal and report it with another account. A moderator can see the report reason and published excerpt; the original private journal text and unrelated chat must not appear.
4. Review, dismiss, and reopen a report with notes. Hide the reported community post after confirmation. Confirm its author still has the full private journal, the community no longer shows the post/comments, and the audit records the action. Verify empty notes cannot be submitted.
5. Suspend an account in a connection. Its session should expire; its companion keeps the archived garden/rewards. Restore the account and confirm it needs a new login and does not regain the old connection. Check externally verified age and birth-date correction behavior.
6. Demote a moderator while their staff screen is open. After sync, staff content disappears; subsequent staff API calls and retries return 403. Confirm the API cannot grant admin or modify an admin account. Verify the CLI refuses to remove the last active admin.
7. Test report/account/audit pagination, username search, empty lists, request failure, refresh/retry, and returning from a detail screen. Confirm pages replace prior page content and notes/actions do not cross accounts after logout.
8. On the login screen, choose System, Light, then Dark. Repeat under avatar → Appearance. Check the choice survives restart and logout, and System follows changes in iOS Settings while the app is open.
9. Inspect login/registration, all four tabs, editors, comments, sent/received chat bubbles, garden stages/archives, settings, and staff screens in both appearances. Open sheets and confirmation dialogs, use the keyboard, and check text/control contrast, large text, VoiceOver labels, and the night garden.
10. Run a native Debug and Release build plus **⌘U** in Xcode. Linux syntax/project checks do not validate Swift type checking, the asset compiler, or actual iOS rendering.

## Security fixes (v0.4)

1. Hide one anonymous story. Other stories and named suggestions remain unchanged. Named profile blocking still ends the identified connection and hides identified posts; use story hiding/reporting for anonymous content.
2. Hide a reported post as staff, then try sharing from an editor opened before that action. The server rejects publication. The author can save privately. Staff restoration permits sharing again but never publishes automatically.
3. Review/dismiss the report at a different device's current pagination cursor. The other device can still load the next page.
4. Browse more than 20 saved gardens, move forward/back through pages, and confirm rewards and partner names remain available.
5. Let a session expire while settings or archive/editor sheets are open. The app returns to login without a force-unwrap crash or another account's data remaining in a sheet. Repeat logout when the token has already been revoked.
6. Set the device calendar to a non-Gregorian calendar. Daily check-in remains aligned with the server's Gregorian UTC date.

## English source and Vietnamese translations

1. Start with no saved language preference. Login, registration, settings, tabs, journal, community, chat, garden, and staff screens use English. Restart and confirm English remains the default.
2. Choose Vietnamese from the language menu, then repeat those screens, accessibility labels, confirmations, and dynamic names/counts. Restart and log out/in; the saved Vietnamese preference remains selected.
3. Trigger login, field-validation, permission, and oversized-upload errors in both languages. Each uses the chosen language without exposing credentials.
4. Upgrade a test database with legacy support preferences and Vietnamese user-written content. Both old and new support choices display translated labels; nicknames, journal text, messages, interests, and conversation pace retain their original content. Update app/backend together.


## iOS and web live chat (v0.5)

- Open an iOS client and a web client as the two members of an active connection. Send from each side; messages should appear immediately once, even if REST acknowledgement and a live event race.
- Disconnect/reconnect the network; repeat a send after a lost reply. Confirm history contains one copy and reconnect loads missed messages.
- Background the iOS app and return. Its socket must stop/restart without accumulating connections; polling remains available while a socket is unavailable.
- End/block the connection, revoke the session, change age eligibility, or suspend a member while sockets are open. Further messages must be rejected and stale chat must disappear after reconciliation.
- Verify mobile web account settings include logout and Management for authorized staff. Check desktop/mobile English/Vietnamese, dark/system appearance, keyboard focus, dialogs, sharing previews, and multiline content.
