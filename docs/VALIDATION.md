# Validation — 2026-10-14

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
