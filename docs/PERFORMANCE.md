# Performance notes

A small Linux measurement over **real localhost HTTP** used two accounts and 300 synthetic journals, with a snapshot window of 60 entries and one chat. Each group ran 20 sequential requests. This was not a concurrent load test and excluded WAN/TLS and iPhone rendering.

| Response | p50 | p95 | Body |
|---|---:|---:|---:|
| Snapshot 200 | 3.30 ms | 3.70 ms | About 81 KB |
| Conditional 304 | 1.11 ms | 1.40 ms | 0 bytes |

Results vary by hardware, database, OS, and network. This environment did not provide reliable RSS measurements; wrapper PID usage is not the Python process footprint. `backend/benchmark.py` can read RSS on conventional Linux; Windows/macOS operators can use Task Manager/Activity Monitor. No concurrent-user capacity is promised.

Memory controls include bounded snapshots, pagination, at most 500 chat records on the client, 256 KiB requests, 4,096 rate-limit buckets, 16 worker threads, and a 2 MiB SQLite cache per connection. The server does not load its entire database into an in-memory AppState. Use one process/worker for SQLite and the limiter; additional workers multiply cache memory without removing SQLite's single-writer limit.

Before a pilot, measure p95 latency at realistic load, RSS across the process tree, SQLite lock duration, database/WAL growth, and data transferred per client. Password hashing is deliberately CPU-intensive; do not reduce its iteration count to improve login benchmark numbers.
