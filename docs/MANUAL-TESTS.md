# Kiểm tra thủ công trên Xcode / iPhone

Chưa được chạy trong môi trường tạo source. Điền kết quả thực sau khi chạy.

| Tình huống | Kết quả mong đợi | Kết quả thực |
|---|---|---|
| Lần mở đầu | Onboarding, nhãn demo, thông tin dữ liệu giả lập | Chưa chạy |
| Journal mới | Chỉ mình tôi là mặc định | Chưa chạy |
| Chia sẻ đoạn không thuộc bài | Không lưu; hiển thị giải thích | Chưa chạy |
| Publish ẩn danh | Chỉ đoạn đã chọn; không lộ tiêu đề, nickname hay link hồ sơ | Chưa chạy |
| Rút bài về riêng tư | Biến mất khỏi feed của vai khác | Chưa chạy |
| Người khác phản hồi bài tắt bình luận | Không có ô nhập phản hồi | Chưa chạy |
| Gửi lời mời khi chưa đồng thuận | Chưa mở chat | Chưa chạy |
| Đổi sang người nhận | Có profile ngắn, nút chấp nhận/từ chối | Chưa chạy |
| Vai 17 tuổi và vai 22 tuổi | Không gửi/nhận lời mời; áp dụng cả từ feed | Chưa chạy |
| Hai vai đồng ý | Cùng thấy một kết nối và chat | Chưa chạy |
| Gửi chat rồi đổi vai | Tin nhắn đúng người gửi, theo đúng kết nối | Chưa chạy |
| Một vai check-in hai lần | Không cộng ngày nếu chưa có vai kia | Chưa chạy |
| Cả hai check-in | Cộng đúng một ngày | Chưa chạy |
| Bỏ trống một ngày | Streak ngắt, phần thưởng giữ nguyên | Chưa chạy |
| Bật nghỉ | Không check-in; không mất phần thưởng | Chưa chạy |
| Rời/chặn | Chat đóng, vườn lưu, không chia sẻ journal cũ sang kết nối mới | Chưa chạy |
| Báo cáo | Nêu rõ chỉ lưu local, không giả vờ đã có moderator nhận | Chưa chạy |
| Đóng/mở app | Bài, chat, connection và vườn được phục hồi | Chưa chạy |
| Bật VoiceOver | Nút gửi, tạo journal, check-in, hình vườn có nhãn | Chưa chạy |
| iPhone nhỏ + chữ lớn | Không che nút quan trọng; nội dung cuộn được | Chưa chạy |


# Online (cần chạy trên Xcode/iPhone)

| Tình huống | Kết quả mong đợi | Kết quả thực |
|---|---|---|
| Server Windows/Linux, iPhone cùng LAN | URL đúng IP host; app xin quyền Local Network | Chưa chạy |
| Đăng ký/login/logout | Token Keychain; logout server xác nhận, UI trở về demo riêng | Chưa chạy |
| Tài khoản chưa xác minh tuổi | Có journal; không matching; hiển thị hướng dẫn xác minh | Chưa chạy |
| Hai thiết bị đăng nhập hai tài khoản | Bài/lời mời/chat/check-in đồng bộ qua server | Chưa chạy |
| Đóng/mở app | Khôi phục phiên Keychain, tải state online mới | Chưa chạy |
| Mất mạng sau POST | Retry cùng ID không tạo chat/journal hai lần; báo trạng thái rõ | Chưa chạy |
| Scroll journal cũ / load tin cũ | Phân trang đúng quyền; không lẫn tài khoản | Chưa chạy |
| Bài ẩn danh gửi lời mời | Trước accept không hiện profile tác giả, kể cả xóa bài | Chưa chạy |
| Qua ngày UTC | Check-in/streak cùng ngày server, không phụ thuộc timezone máy | Chưa chạy |
| Bản Release | Chỉ HTTPS có certificate tin cậy | Chưa chạy |
