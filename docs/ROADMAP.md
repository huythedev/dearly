# Dearly roadmap và phân công

## Hiện đã có

Native demo + server một node, tài khoản/password/session, API permission, SQLite persistence, matching gate theo ngày sinh đã operator xác minh, sync client foreground, phân trang journal/chat, báo cáo server, quản trị CLI và backup.

## Trước pilot thật

- Build/XCTest và chạy đủ luồng trên iPhone; thử bàn phím, mạng chập chờn, foreground/background, hết hạn phiên, Dynamic Type và VoiceOver.
- Chạy matrix backend trên các OS mục tiêu; triển khai HTTPS, đường dẫn database ổn định, backup/restore, user OS có quyền tối thiểu.
- Thiết kế quy trình xác minh tuổi và sự đồng ý phù hợp phạm vi pilot. Cờ CLI hiện là manual review, chưa có tự xác minh giấy tờ. Chốt timezone check-in cho sản phẩm; bản hiện tại UTC chung.
- Có người trực báo cáo, xử lý vi phạm, hướng dẫn trường hợp nhạy cảm và quy trình kháng nghị. Báo cáo đã đến server nhưng chưa có moderator dashboard hay bộ lọc tin tự động.
- Thêm quản lý/xóa/xuất tài khoản, đổi mật khẩu, revoke mọi thiết bị, email/recovery; không coi username/password prototype là hệ thống identity đầy đủ.
- Thiết kế retention journal/chat/report, vận hành bản backup và quyền truy cập người quản trị. Dữ liệu ở server hiện là SQLite, không phải mã hóa đầu-cuối.
- Đo performance dưới tải dự kiến; khi cần scale nhiều node, đổi database/repository và per-user invalidation.

## Mở rộng

Challenge tùy chọn; kỷ niệm phải hai người duyệt; push kín đáo; lịch sử cộng đồng/journal companion dài; bản địa hóa tiếng Anh, dark mode/iPad; tối ưu delta sync hoặc WebSocket khi cần latency thấp hơn polling.

## Team hai người

| Người | Sở hữu | Bằng chứng |
|---|---|---|
| Kỹ thuật | SwiftUI, API, permissions, database, tests, deploy/backup | PR, kiến trúc, test results, demo |
| Sản phẩm/nghiên cứu | Phỏng vấn, nội dung app, kịch bản test, tổng hợp feedback | Tài liệu ẩn danh, issues, thiết kế và báo cáo test |
| Cả hai | Chốt scope, review thay đổi, trình bày đóng góp/giới hạn | Decision log, changelog, README credits |

Issues phù hợp bạn không thiên tech: người thử có hiểu ba mức chia sẻ không; trải nghiệm lời mời từ bài ẩn danh; cảm giác áp lực streak; onboarding theo feedback. Dùng nội dung giả khi thử các luồng nhạy cảm.
