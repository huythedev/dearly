# Performance notes

Một phép đo nhỏ trên Linux qua **HTTP localhost thật**, hai tài khoản, database có 300 journal giả, snapshot chỉ lấy 60 bài và một chat. 20 request tuần tự cho mỗi nhóm; không phải load test đồng thời và không bao gồm WAN/TLS/iPhone rendering.

| Response | p50 | p95 | Body |
|---|---:|---:|---:|
| Snapshot 200 | 3,30 ms | 3,70 ms | Khoảng 81 KB |
| Conditional 304 | 1,11 ms | 1,40 ms | 0 byte |

Kết quả có thể thay đổi theo máy, database, OS và mạng. Chưa có số RSS đáng tin cậy trong môi trường chạy này; không đưa số từ PID wrapper ra làm footprint Python. `backend/benchmark.py` có thể đọc RSS trên Linux thông thường; Windows/macOS có thể dùng Task Manager/Activity Monitor. Không có cam kết số người dùng đồng thời.

Cơ chế giới hạn RAM: snapshot hữu hạn, phân trang, chat tối đa 500 record client, request 128 KiB, limiter 4.096 bucket, 16 worker thread và SQLite cache 2 MiB mỗi connection. Server không load toàn database vào một AppState trong RAM. Dùng một process/worker cho SQLite và limiter; tăng worker sẽ nhân bộ nhớ cache và không bỏ giới hạn một writer của SQLite.

Khi đánh giá trước pilot: đo độ trễ p95 dưới tải thực, RSS toàn process tree, thời gian lock SQLite, tốc độ tăng database/WAL và lượng data/client. Password hash được cố tình giữ tốn CPU để bảo vệ mật khẩu, không giảm số vòng chỉ để làm đẹp benchmark login.
