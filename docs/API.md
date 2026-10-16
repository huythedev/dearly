# API contract v0.4

Base URL là origin server, không có path/query. Các endpoint `/v1/*` ngoài register/login cần header `Authorization: Bearer TOKEN`. OpenAPI đầy đủ ở `/docs` trên server đang chạy.

| Method / path | Đầu vào | Đầu ra |
|---|---|---|
| GET `/health` | Không cần auth | status, version, dayBoundary UTC |
| POST `/v1/auth/register` | username, password, nickname, birthDate YYYY-MM-DD | token, userID, expiresAt |
| POST `/v1/auth/login` | username, password | token, userID, expiresAt |
| POST `/v1/auth/logout` | Bearer token | ok; thu hồi token hiện tại |
| GET `/v1/state` | Bearer; tùy chọn If-None-Match | `{state, serverNow}` + ETag, hoặc 304 không body |
| POST `/v1/actions` | requestID UUID, kind, payload | ok và id cho thao tác tạo mới |
| GET `/v1/messages` | connectionID, before ID tùy chọn, limit 1–100 | items theo thời gian tăng, nextCursor |
| GET `/v1/journals` | before ID tùy chọn, limit 1–60 | Journal của chính mình theo thời gian giảm, nextCursor |
| GET `/v1/connections` | before ID tùy chọn, limit 1–50 (mặc định 20) | Vườn đã lưu của chính mình; items, profiles, nextCursor |
| GET `/v1/staff/reports` | status open/reviewed/dismissed (mặc định open), before UUID, limit 1–50 | Report page; cần reports.read |
| GET `/v1/staff/users` | q: tiền tố username/nickname, before UUID, limit 1–50 | Account page; cần users.read |
| GET `/v1/staff/audit` | before: số nguyên event ID, limit 1–50 | Audit page; cần audit.read |

Date trong JSON là **số giây từ 2001-01-01 UTC**, tương thích cách mặc định Swift JSONEncoder/JSONDecoder encode Date. Không dùng Unix epoch cho các DTO native. `birthDate` là chuỗi ngày Gregorian, không phải timestamp. ID là UUID. Ngày check-in là chuỗi YYYY-MM-DD theo UTC server.

## Actions

Mỗi POST có dạng:

```json
{
  "requestID": "B9438240-7D2B-49A3-83EE-4B68543D34E6",
  "kind": "message.send",
  "payload": {
    "connectionID": "439903D4-52BE-454D-9F02-BF068F88F39F",
    "text": "Hôm nay mình vẫn ở đây."
  }
}
```

| kind | payload |
|---|---|
| journal.save | id nếu sửa; title, body, sharedText, audience, anonymous, commentsEnabled, support |
| journal.delete | id |
| journal.hide | id bài cộng đồng; chỉ ẩn bài đó cho người đang đăng nhập |
| journal.listen | id, enabled bool (đặt trạng thái, không toggle mù trên server) |
| journal.comment | id, text |
| invitation.send | userID **hoặc** journalID của bài công khai có hồ sơ; bài ẩn danh trả 403 |
| invitation.accept / invitation.dismiss | id của lời mời |
| message.send | connectionID, text |
| connection.checkin / connection.leave | connectionID |
| connection.pause | connectionID, paused bool |
| user.block | userID hoặc journalID bài có hồ sơ; client cũ dùng journalID ẩn danh chỉ ẩn bài đó |
| report.create | userID hoặc journalID, reason |
| profile.update | nickname, bio, interests (tối đa 8), support, pace |
| staff.report.review | id report, status open/reviewed/dismissed, reason; cần reports.review |
| staff.report.hide | id report, reason; cần reports.hide |
| staff.report.restore | id report, reason; cần reports.hide; cho phép tác giả chia sẻ lại, không tự publish |
| staff.user.suspend | userID, suspended bool, reason; cần users.suspend |
| staff.user.verify_age | userID, birthDate YYYY-MM-DD, reason; cần users.verify_age |
| staff.user.role | userID, role user/moderator, reason; cần roles.manage |

`audience`: privateOnly / companion / community. `support`: Chỉ cần lắng nghe / Chia sẻ trải nghiệm / Cùng nghĩ cách. Tạo journal không nhận ID do client tự đặt; server cấp ID. Sửa chỉ được dùng ID journal của mình đã tồn tại.

`requestID` dùng lại khi retry cùng mutation. Server giữ kết quả và hash payload 7 ngày, atomically trong transaction; cùng ID khác payload trả 409. Check-in vẫn có unique `(connection, day, user)` độc lập với khóa retry. Server không nhận ngày/streak/reward/members do client tự khai.

## Staff roles and payloads

`state.currentUserRole` is `user`, `moderator`, or `admin`; `state.permissions` contains only the current account's permission strings. Roles are never accepted from registration or public profile updates. Older state payloads omit these fields; the iOS app treats that as no staff access. The personal snapshot format remains `schemaVersion=1`; SQLite storage migrates separately to `user_version=3`.

Moderators have `reports.read`, `reports.review`, and `reports.hide`. Admins additionally have `users.read`, `users.suspend`, `users.verify_age`, `roles.manage`, and `audit.read`. Every staff read/write is authenticated and authorized server-side using the current database role, including idempotent retries after demotion. Regular users receive 403. Staff mutations reject unknown payload keys and require a non-empty reason of at most 1,000 characters.

The API cannot grant `admin`, modify an existing admin account, or let an admin modify their own account. Use the backend `set-role`, `verify-age`, `suspend`, or `restore` commands for admin accounts. The last active admin is protected from demotion/suspension.

Staff pages return `{items, nextCursor}` with 30 records by default and at most 50. Report/account cursors are UUIDs ordered by `(created,id)` descending; audit cursors are integer event IDs descending. Responses use `Cache-Control: no-store` and `Vary: Authorization`.

- Report: `id`, `reporterID`, `reportedID`, `reporterNickname`, `reportedNickname`, `reason`, `status`, `date`, optional `journalID`, `evidence`, `canHide`, `canRestore`, `reviewNote`, optional `reviewerID` and `reviewedAt`. `reviewerID` is an account UUID string or `server-cli`. Evidence is the reported public excerpt, never the author's full/private body. Legacy/account-only reports have empty evidence and no journal ID. Deleting a source post nulls its journal ID but retains the evidence. `canHide` is true only while that reported post still exists publicly under the reported author. `canRestore` indicates a durable sharing restriction. Report cursors continue working when their source report changes status.
- Account: `id`, `username`, `nickname`, `role`, `suspended`, `ageVerified`, `birthDate`. This endpoint is admin-only and never returns password hashes or sessions.
- Audit: integer `id`, `actorID` (UUID string or `server-cli`), `actorName`, `action`, `targetID`, `detail`, `date`. Details contain the reason/note and relevant status or before/after role, not birth dates or credentials.

`staff.report.hide` changes the reported community post to private, removes its comments/listening reactions, and creates a durable sharing restriction. The author receives `moderationHidden: true`, keeps the full journal, and can save private edits; attempts to share to community or companion return 403 until `staff.report.restore`. Restoration is audited and leaves the entry private. Missing/deleted/already-private posts return 409 for hide. `staff.user.suspend` revokes all sessions and ends connections without removing rewards. Suspended accounts' comments and posts are omitted from public reads. Restoring access requires a new login and does not reopen connections. Correcting a birth date also ends connections and pending invitations for eligibility re-checking; confirming the same date preserves them. Successful staff and operator mutations append audit events in the same transaction.

## Quyền riêng tư trong DTO

- Chỉ chủ journal nhận title/body gốc; người khác nhận `sharedText` được chọn và body/title rỗng.
- Bài ẩn danh dùng UUID bài làm alias authorID trong DTO cho người khác. ID tác giả thật không xuất hiện trong bài hoặc phản hồi của tác giả.
- Bài ẩn danh không nhận lời mời và luôn có `canInviteAuthor: false`. Lời mời qua hồ sơ vẫn cần đúng nhóm tuổi, xác minh và đồng thuận hai phía. Nâng cấp v3 xóa lời mời ẩn danh cũ đang chờ.
- `journal.hide` chỉ ẩn UUID bài, không chặn tài khoản, đổi danh sách gợi ý hay kết thúc kết nối. Chặn tài khoản có hồ sơ không làm biến mất bài/phản hồi của tác giả ẩn danh, để tránh dùng chặn làm công cụ dò danh tính. Muốn tránh một bài ẩn danh, hãy ẩn bài đó hoặc báo cáo để staff xử lý. Nội dung hoặc thông tin tác giả tự tiết lộ vẫn có thể giúp người đọc nhận ra họ.
- Journal companion gắn với connection ID cụ thể; kết nối đã kết thúc hoặc người đồng hành mới không đọc được.
- Snapshot gồm hồ sơ/record cần cho người đang đăng nhập, không chứa bảng users/sessions/reports toàn cục. `suggestedUserIDs` chỉ những người server đã kiểm tra khả năng kết nối. Các endpoint staff riêng chỉ cấp dữ liệu theo quyền được mô tả ở trên.
- Profile công khai có tuổi tính theo hôm nay và cờ đã xác minh, không có ngày sinh, username hay mật khẩu/token.
- Chat history chỉ đọc được bởi thành viên của kết nối đang hoạt động. Server trả summary vườn cũ, không trả transcript cũ qua endpoint history.

## Lỗi và giới hạn

Lỗi có `{ "detail": "thông điệp" }`; validation không phản chiếu mật khẩu. 401: cần đăng nhập lại. 403: không có quyền/không đúng nhóm tuổi. 404: record không tồn tại hoặc bị ẩn. 408: quá thời gian tải body; connection đóng. 409: xung đột trạng thái. 413: request quá lớn. 429: rate limit hoặc quá nhiều body đang tải. 503: database bận, có Retry-After. `support` sai kiểu trả 400, không phải 500.

State không có cursor chung; đây là snapshot các cửa sổ hữu hạn mô tả trong backend README. Journal cá nhân/chat/vườn đã lưu có endpoint phân trang riêng; các endpoint này dùng `Cache-Control: no-store`. Vườn đã lưu phân trang theo `(started,id)` giảm dần và chỉ trả hồ sơ thành viên của trang đó. Kết nối đang hoạt động luôn có trong state, kể cả nếu một archive cũ có timestamp sai. Những mutation hoặc đổi ngày UTC làm ETag đổi; ETag không chứa token và khác giữa các tài khoản. App không gửi state ngược lên server để ghi đè database.
