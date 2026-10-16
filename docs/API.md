# API contract v0.3

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
| journal.listen | id, enabled bool (đặt trạng thái, không toggle mù trên server) |
| journal.comment | id, text |
| invitation.send | userID **hoặc** journalID; dùng journalID cho lời mời từ bài ẩn danh |
| invitation.accept / invitation.dismiss | id của lời mời |
| message.send | connectionID, text |
| connection.checkin / connection.leave | connectionID |
| connection.pause | connectionID, paused bool |
| user.block | userID hoặc journalID |
| report.create | userID hoặc journalID, reason |
| profile.update | nickname, bio, interests (tối đa 8), support, pace |
| staff.report.review | id report, status open/reviewed/dismissed, reason; cần reports.review |
| staff.report.hide | id report, reason; cần reports.hide |
| staff.user.suspend | userID, suspended bool, reason; cần users.suspend |
| staff.user.verify_age | userID, birthDate YYYY-MM-DD, reason; cần users.verify_age |
| staff.user.role | userID, role user/moderator, reason; cần roles.manage |

`audience`: privateOnly / companion / community. `support`: Chỉ cần lắng nghe / Chia sẻ trải nghiệm / Cùng nghĩ cách. Tạo journal không nhận ID do client tự đặt; server cấp ID. Sửa chỉ được dùng ID journal của mình đã tồn tại.

`requestID` dùng lại khi retry cùng mutation. Server giữ kết quả và hash payload 7 ngày, atomically trong transaction; cùng ID khác payload trả 409. Check-in vẫn có unique `(connection, day, user)` độc lập với khóa retry. Server không nhận ngày/streak/reward/members do client tự khai.

## Staff roles and payloads

`state.currentUserRole` is `user`, `moderator`, or `admin`; `state.permissions` contains only the current account's permission strings. Roles are never accepted from registration or public profile updates. Older state payloads omit these fields; the iOS app treats that as no staff access. The personal snapshot format remains `schemaVersion=1`; SQLite storage migrates separately to `user_version=2`.

Moderators have `reports.read`, `reports.review`, and `reports.hide`. Admins additionally have `users.read`, `users.suspend`, `users.verify_age`, `roles.manage`, and `audit.read`. Every staff read/write is authenticated and authorized server-side using the current database role, including idempotent retries after demotion. Regular users receive 403. Staff mutations reject unknown payload keys and require a non-empty reason of at most 1,000 characters.

The API cannot grant `admin`, modify an existing admin account, or let an admin modify their own account. Use the backend `set-role`, `verify-age`, `suspend`, or `restore` commands for admin accounts. The last active admin is protected from demotion/suspension.

Staff pages return `{items, nextCursor}` with 30 records by default and at most 50. Report/account cursors are UUIDs ordered by `(created,id)` descending; audit cursors are integer event IDs descending. Responses use `Cache-Control: no-store` and `Vary: Authorization`.

- Report: `id`, `reporterID`, `reportedID`, `reporterNickname`, `reportedNickname`, `reason`, `status`, `date`, optional `journalID`, `evidence`, `canHide`, `reviewNote`, optional `reviewerID` and `reviewedAt`. `reviewerID` is an account UUID string or `server-cli`. Evidence is the reported public excerpt, never the author's full/private body. Legacy/account-only reports have empty evidence and no journal ID. Deleting a source post nulls its journal ID but retains the evidence. `canHide` is true only while that reported post still exists publicly under the reported author.
- Account: `id`, `username`, `nickname`, `role`, `suspended`, `ageVerified`, `birthDate`. This endpoint is admin-only and never returns password hashes or sessions.
- Audit: integer `id`, `actorID` (UUID string or `server-cli`), `actorName`, `action`, `targetID`, `detail`, `date`. Details contain the reason/note and relevant status or before/after role, not birth dates or credentials.

`staff.report.hide` changes the reported community post to private and removes its comments/listening reactions, while preserving the author's journal body and pending anonymous invitation aliases. Missing/deleted/already-private posts return 409. Authors retain the normal ability to edit/share their journal. `staff.user.suspend` revokes all sessions and ends connections without removing rewards. Restoring access requires a new login and does not reopen connections. Correcting a birth date also ends connections and pending invitations for eligibility re-checking; confirming the same date preserves them. Successful staff and operator mutations append audit events in the same transaction.

## Quyền riêng tư trong DTO

- Chỉ chủ journal nhận title/body gốc; người khác nhận `sharedText` được chọn và body/title rỗng.
- Bài ẩn danh dùng UUID bài làm alias authorID trong DTO cho người khác. ID tác giả thật không xuất hiện trong bài hoặc phản hồi của tác giả.
- Lời mời gửi tới bài ẩn danh giữ recipient alias cho người gửi trong lúc chờ, kể cả tác giả xóa bài nguồn. Khi người nhận chấp nhận, kết nối cung cấp nickname/profile của hai thành viên; bài cũ vẫn không có link hồ sơ.
- Journal companion gắn với connection ID cụ thể; kết nối đã kết thúc hoặc người đồng hành mới không đọc được.
- Snapshot gồm hồ sơ/record cần cho người đang đăng nhập, không chứa bảng users/sessions/reports toàn cục. `suggestedUserIDs` chỉ những người server đã kiểm tra khả năng kết nối. Các endpoint staff riêng chỉ cấp dữ liệu theo quyền được mô tả ở trên.
- Profile công khai có tuổi tính theo hôm nay và cờ đã xác minh, không có ngày sinh, username hay mật khẩu/token.
- Chat history chỉ đọc được bởi thành viên của kết nối đang hoạt động. Server trả summary vườn cũ, không trả transcript cũ qua endpoint history.

## Lỗi và giới hạn

Lỗi có `{ "detail": "thông điệp" }`; validation không phản chiếu mật khẩu. 401: cần đăng nhập lại. 403: không có quyền/không đúng nhóm tuổi. 404: record không tồn tại hoặc bị ẩn. 409: xung đột trạng thái. 413: request quá lớn. 429: rate limit. 503: database bận, có Retry-After.

State không có cursor chung; đây là snapshot các cửa sổ hữu hạn mô tả trong backend README. Journal cá nhân/chat có endpoint phân trang riêng. Những mutation hoặc đổi ngày UTC làm ETag đổi; ETag không chứa token và khác giữa các tài khoản. App không gửi state ngược lên server để ghi đè database.
