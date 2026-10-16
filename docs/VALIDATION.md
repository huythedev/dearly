# Validation — security fixes, 2026-10-16

- **55 backend tests passed** on Linux/Python 3.12, including 22 added regression cases for the audit findings and adjacent bugs. A real loopback HTTP test verifies upload admission, timeout responses, and continued health availability.
- A separate real-HTTP two-account smoke test passed: login/registration, invitation acceptance, messaging, check-ins, and conditional state synchronization with 300 journal fixtures.
- **517 payload-type variations** across mutation handlers completed without unexpected exceptions; each trial rolled back its database changes. This was an exploratory input-validation check, not a production test.
- Ruff `F,E9`, Python compilation, and whitespace checks passed. The dependency advisory scan reported no known vulnerabilities across the 14 pinned runtime packages, including the formerly unpinned OpenTelemetry dependency.
- Bandit's SQL-construction warnings were reviewed: interpolated fragments are fixed clauses or generated parameter placeholders, with user values bound separately. Development subprocess/assert/fixture-password alerts do not establish a runtime exploit.
- Native XCTest coverage was added for signed-out model access, Gregorian UTC dates, anonymous invitation guards, independent anonymous visibility, and archived garden DTOs. The `ios` GitHub Actions job performs the simulator build and XCTest run; check its result for the specific PR commit. Local Linux checks do not replace native validation.
- Database upgrade coverage includes v1→v3 preservation and v2→v3 reconstruction of earlier moderation restrictions, cancellation of unsafe anonymous invitations, repeated startup, and foreign-key integrity.
- Remaining manual scope: iPhone layout/VoiceOver, Windows/macOS backend operation, Docker, the production proxy/TLS boundary, and App Store/TestFlight distribution.

## Historical validation — roles and appearance, 2026-10-16

- **33 backend pytest tests passed** on Linux/Python 3.12 with the repository's pinned runtime dependencies. This includes the original 21 cases plus authorization, attempted role escalation, moderator review/hiding, live demotion and replay rejection, admin suspension/restoration, CLI bootstrap/last-admin protection, pagination, and v1→v2 migration preserving existing data.
- The test runner reports one upstream Starlette warning about its httpx TestClient adapter; there were no test failures.
- Swift grammar, Xcode source/resource references, light/dark asset JSON, and Info.plist checks passed. `staff-responses.json` was exported from actual API responses; an added native XCTest decodes the state role, staff reports/accounts/audit DTOs, including a CLI reviewer ID. The older state fixture verifies absence of staff fields stays compatible.
- **Not verified for this revision:** native Swift compilation/type checking, Xcode builds/XCTest, Simulator/device rendering, Windows/macOS execution, Docker, or deployment. This environment has no Apple SDK or Simulator. Run the expanded manual checklist and native tests on a Mac.

## Historical validation — 2026-10-14

## Đã thực hiện

- 21 pytest API trên Linux/Python 3.12: pass. Bao gồm HTTP contract, privacy/anonymous alias, xác thực/logout/expiry, gate tuổi/birthday, đồng thuận, write đồng thời, check-in trùng, streak/giữ thưởng, pause/rời/chặn/báo cáo, retry idempotent, phân trang và database restart.
- Server Uvicorn thật trên localhost: đăng ký hai tài khoản, xác minh fixture, gửi/chấp nhận lời mời, gửi tin từ tài khoản A và đọc ở B, cả hai check-in. Pass.
- Benchmark HTTP tuần tự với 300 journal fixture; kết quả và giới hạn trong PERFORMANCE.md.
- Fixture `DearlyTests/Fixtures/server-state.json` được xuất từ response API thật, không chứa token hoặc phần journal riêng của người khác. Một XCTest sẽ decode fixture thành DTO native để phát hiện lệch wire contract khi chạy Xcode.
- Kiểm tra grammar toàn bộ Swift, cấu trúc/source references Xcode, scheme XML, asset catalogs và Info.plist Debug/Release.
- CLI help/khởi tạo database, cấu trúc đóng gói source.

## Chưa thực hiện

- Apple Swift compiler/type checking/linking, xcodebuild, 17 XCTest native, code signing, Simulator/device và kiểm tra layout/VoiceOver.
- Chạy thực trên Windows/macOS, build Docker, hoặc chạy các workflow GitHub Actions. Matrix Windows/macOS/Linux × Python 3.11/3.12/3.13 đã được chuẩn bị.
- Load test đồng thời lớn, TLS public server hoặc App Store/TestFlight release.

Môi trường hiện tại không có Swift compiler, Xcode/Apple SDK hay iOS Simulator. Parser Swift không thay thế Xcode build. Trên Mac chạy ⌘U rồi checklist MANUAL-TESTS.md. Backend qua test không tự xác nhận UI iOS đã hoạt động trên thiết bị.
