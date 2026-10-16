# Kiểm tra thủ công trên Xcode / iPhone

Chưa được chạy trong môi trường tạo source. Điền kết quả thực sau khi chạy.

| Tình huống | Kết quả mong đợi | Kết quả thực |
|---|---|---|
| Lần mở đầu | Màn hình đăng nhập; khôi phục phiên Keychain hợp lệ nếu có | Chưa chạy |
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
| Báo cáo | Báo cáo gửi tới server và xuất hiện trong hàng đợi staff | Chưa chạy |
| Đóng/mở app | Bài, chat, connection và vườn được phục hồi | Chưa chạy |
| Bật VoiceOver | Nút gửi, tạo journal, check-in, hình vườn có nhãn | Chưa chạy |
| iPhone nhỏ + chữ lớn | Không che nút quan trọng; nội dung cuộn được | Chưa chạy |


# Online (cần chạy trên Xcode/iPhone)

| Tình huống | Kết quả mong đợi | Kết quả thực |
|---|---|---|
| Server Windows/Linux, iPhone cùng LAN | URL đúng IP host; app xin quyền Local Network | Chưa chạy |
| Đăng ký/login/logout | Token Keychain; logout server xác nhận, UI trở về màn hình đăng nhập | Chưa chạy |
| Tài khoản chưa xác minh tuổi | Có journal; không matching; hiển thị hướng dẫn xác minh | Chưa chạy |
| Hai thiết bị đăng nhập hai tài khoản | Bài/lời mời/chat/check-in đồng bộ qua server | Chưa chạy |
| Đóng/mở app | Khôi phục phiên Keychain, tải state online mới | Chưa chạy |
| Mất mạng sau POST | Retry cùng ID không tạo chat/journal hai lần; báo trạng thái rõ | Chưa chạy |
| Scroll journal cũ / load tin cũ | Phân trang đúng quyền; không lẫn tài khoản | Chưa chạy |
| Bài ẩn danh gửi lời mời | Trước accept không hiện profile tác giả, kể cả xóa bài | Chưa chạy |
| Qua ngày UTC | Check-in/streak cùng ngày server, không phụ thuộc timezone máy | Chưa chạy |
| Bản Release | Chỉ HTTPS có certificate tin cậy | Chưa chạy |

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
