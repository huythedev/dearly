# Dearly roadmap và phân công

## Hiện đã có

App iOS kết nối server một node, tài khoản/password/session, API permission, SQLite persistence, matching gate theo ngày sinh đã operator xác minh, sync foreground, phân trang journal/chat, báo cáo server, giao diện moderator/admin, cấp vai trò qua CLI, audit log và backup. Giao diện tiếng Việt/Anh, System/Light/Dark và vườn ban đêm.

## Trước pilot thật

- Build/XCTest và chạy đủ luồng trên iPhone; thử bàn phím, mạng chập chờn, foreground/background, hết hạn phiên, Dynamic Type và VoiceOver.
- Chạy matrix backend trên các OS mục tiêu; triển khai HTTPS, đường dẫn database ổn định, backup/restore, user OS có quyền tối thiểu.
- Thiết kế quy trình xác minh tuổi và sự đồng ý phù hợp phạm vi pilot. Cờ CLI hiện là manual review, chưa có tự xác minh giấy tờ. Chốt timezone check-in cho sản phẩm; bản hiện tại UTC chung.
- Có người trực báo cáo, xử lý vi phạm, hướng dẫn trường hợp nhạy cảm và quy trình kháng nghị. Đã có màn hình staff xử lý báo cáo; chưa có bộ lọc tin tự động hoặc luồng kháng nghị cho người dùng.
- Thêm quản lý/xóa/xuất tài khoản, đổi mật khẩu, revoke mọi thiết bị, email/recovery; không coi username/password prototype là hệ thống identity đầy đủ.
- Thiết kế retention journal/chat/report, vận hành bản backup và quyền truy cập người quản trị. Dữ liệu ở server hiện là SQLite, không phải mã hóa đầu-cuối.
- Đo performance dưới tải dự kiến; khi cần scale nhiều node, đổi database/repository và per-user invalidation.

## Mở rộng

Challenge tùy chọn; kỷ niệm phải hai người duyệt; push kín đáo; lịch sử cộng đồng/journal companion dài; bố cục iPad; tối ưu delta sync hoặc WebSocket khi cần latency thấp hơn polling.

## Team hai người

| Người | Sở hữu | Bằng chứng |
|---|---|---|
| Kỹ thuật | SwiftUI, API, permissions, database, tests, deploy/backup | PR, kiến trúc, test results, demo |
| Sản phẩm/nghiên cứu | Phỏng vấn, nội dung app, kịch bản test, tổng hợp feedback | Tài liệu ẩn danh, issues, thiết kế và báo cáo test |
| Cả hai | Chốt scope, review thay đổi, trình bày đóng góp/giới hạn | Decision log, changelog, README credits |

Issues phù hợp bạn không thiên tech: người thử có hiểu ba mức chia sẻ không; phân biệt ẩn câu chuyện ẩn danh và chặn hồ sơ; cảm giác áp lực streak; onboarding theo feedback. Dùng nội dung giả khi thử các luồng nhạy cảm.
