# Benchmark & Observability Report — Day 14

> Mọi con số dưới đây được trích xuất trực tiếp từ các file JSON trong `reports/` (CP7) và sẽ bổ sung phần Observability stack / Locust CSV ở CP8.

**Họ tên:** Nguyen Viet Manh Khai (2A202603664)  
**Ngày chạy:** 2026-11-25  
**Môi trường:** Windows 11 + WSL2 Ubuntu 22.04 (Python 3.11.18), Docker Desktop 29.9.2  

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | `< 500 ms` | Latency cơ bản của mock LLM là ~120–180ms (+ ~20ms retrieval); ngưỡng 500ms cho phép 95% người dùng nhận phản hồi nhanh ngay cả khi có jitter ở mức concurrency vừa phải, đồng thời khớp với ngưỡng mặc định của `load_test.py`. |
| Error rate `/ask` | `< 2.0 %` | Mock LLM có tỉ lệ lỗi ngẫu nhiên `MOCK_ERROR_RATE=0.01` (1%); đặt SLO `< 2.0%` giúp chừa biên độ dao động nhỏ của mẫu thử nhưng vẫn bắt kịp khi lỗi tăng bất thường. |
| Accuracy trên golden dataset | `≥ 85 %` | Đảm bảo chất lượng RAG (`v2`) đạt ít nhất ~20/23 câu đúng trở lên và không bị regression trước khi cho phép merge PR trên CI. |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2, `300` requests/mức, `MOCK_SLOW_RATE=0.03`)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 3.77 | 195.3 | 727.5 | 1711.4 | 2.00% (`6/300`) | ❌ FAIL |
| 10 | 38.76 | 188.8 | 223.5 | 1708.7 | 0.67% (`2/300`) | ✅ PASS |
| 50 | 100.63 | 205.6 | 268.2 | 1722.9 | 0.33% (`1/300`) | ✅ PASS |
| 100 | 56.93 | 374.2 | 3428.4 | 3772.4 | 1.67% (`5/300`) | ❌ FAIL |

**Nhận xét:** RPS có tăng tuyến tính theo concurrency không? Vì sao?

- **Không tăng tuyến tính ở tải cao:** Từ concurrency `1 → 10 → 50`, RPS tăng gần tuyến tính (`3.77 → 38.76 → 100.63 req/s`) nhờ I/O async xử lý song song tốt khi chưa bão hòa. Nhưng khi tăng lên concurrency `100`, RPS **tụt mạnh xuống `56.93 req/s`**, `p50` gần gấp đôi (`374.2 ms`) và `p95` vọt lên **`3428.4 ms` (`FAIL` SLO)**.
- **Nguyên nhân:** Chỉ có **1 process uvicorn** trên local nên khi quá nhiều coroutine đồng thời (100 kết nối song song), CPU/event-loop chuyển ngữ cảnh và hàng đợi socket bị nghẽn (*saturation*), khiến request phải xếp hàng chờ xử lý và kéo toàn bộ tail latency tăng vọt. (Ngoài ra ở concurrency `1`, chỉ cần >5% mẫu rơi vào slow request ~1.7s trong lúc lấy mẫu ngẫu nhiên đã làm `p95 = 727.5 ms`).

### 2.2 Tail latency (`300` requests, `concurrency=20`)

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 191.5 | 222.2 | 246.7 |
| 0.03 (mặc định) | 247.5 | 225.3 | 1704.6 |
| 0.1 | 301.7 | 1685.9 | 1708.5 |

**Nhận xét:** Chỉ số nào nhạy nhất với request chậm? Vì sao SLO không nên đặt theo average?

- **`p99` (và `p95` khi tỉ lệ chậm vượt 5%) nhạy nhất với request chậm:** Khi `MOCK_SLOW_RATE` tăng từ `0` lên `0.03`, `avg` chỉ nhích nhẹ từ `191.5 ms` lên `247.5 ms` (+29%), trong khi `p99` nhảy vọt gần **7 lần** từ `246.7 ms` lên **`1704.6 ms`**. Khi `MOCK_SLOW_RATE` tăng lên `0.1` (10% request chậm > 5%), đến lượt `p95` cũng nhảy vọt từ `225.3 ms` lên **`1685.9 ms`** (vi phạm SLO `< 500 ms`), còn `avg` vẫn chỉ ở mức `301.7 ms`.
- **Vì sao SLO không đặt theo average:** Giá trị trung bình bị 90–97% request nhanh kéo xuống nên che giấu trải nghiệm tệ của nhóm người dùng gặp *tail latency* (3–10% người dùng phải chờ gần 2 giây). Đặt SLO theo **percentile (`p95`/`p99`)** phản ánh đúng giới hạn trải nghiệm tệ nhất mà hệ thống cam kết.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.3% (`1/23`) | 91.3% (`21/23`) | 100.0% (`23/23`) |
| Avg tokens / câu | 56.8 | 108.8 | 113.8 |
| Tổng cost (USD) | $0.000400 (`0.0004`) | $0.000757 | $0.000792 |
| Cost / câu đúng (USD) | $0.00039975 | $0.00003607 | $0.00003443 |
| Quality gate | ❌ FAIL | ✅ PASS (gate 80%) | ✅ PASS (gate 100%, 0 regression) |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| `security-02` | `token`, `hết hạn`, `chữ ký` | Thêm entry về `jwt` vào `KNOWLEDGE_BASE` trong `develop/utils/mock_llm.py` và `production/utils/mock_llm.py`, giải thích sự khác biệt giữa API key cố định và JWT có chữ ký số, thông tin user và thời điểm hết hạn. |
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Thêm entry về `hpa` / `kubernetes` / `autoscal` vào `KNOWLEDGE_BASE`, nêu rõ Kubernetes HPA scale pod theo CPU, memory hoặc custom metrics (RPS, queue length). |

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**

- **Chất lượng vs Chi phí:** `v1` không có retrieval nên dùng ít token hơn (`56.8` vs `108.8`–`113.8` tokens/câu) và tổng cost thấp hơn (`$0.0004` vs `$0.000792`), nhưng độ chính xác chỉ đạt **`4.3%` (1/23)** — gần như vô dụng trong thực tế. `v2` (sau khi bổ sung KB) đạt **`100.0%` (23/23)**, giúp **`cost / câu đúng` giảm hơn 11 lần** (từ `$0.00039975` xuống `$0.00003443`). Vì vậy dùng **`cost / câu đúng`** đánh giá hiệu quả kinh tế chính xác hơn nhiều so với `cost / câu`.
- **Latency:** `v2` chậm hơn `v1` khoảng ~30ms ở `p50` (`163.7 ms` vs `191.8`–`199.8 ms`) do thêm bước tìm tài liệu (`MOCK_RETRIEVAL_MS=20ms`) và prompt dài hơn, nhưng vẫn nằm gọn dưới SLO `p95 < 500 ms` (`221.4 ms`).
- **CI Quality Gate:** Đã tạo workflow [.github/workflows/eval.yml](.github/workflows/eval.yml) chạy `python eval/run_eval.py --url http://localhost:8000 --min-accuracy 0.85` trên mỗi Pull Request. Khi `accuracy < 85%` hoặc có bất kỳ câu nào bị regression so với baseline, script trả về **exit code `1`** làm job CI fail và chặn merge tự động.

*(Đã bổ sung thêm metric Histogram `agent_question_length_chars` vào `develop/app.py` để theo dõi phân bố độ dài câu hỏi mà không gây bùng nổ cardinality).*

---

## 4. Observability stack (production)

### 4.1 Screenshot

- [ ] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals)
- [ ] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian)
- [ ] Một trace lỗi trong Jaeger (có event `exception`)
- [ ] Trang Alerts của Prometheus với ít nhất 1 alert đang **firing**

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | <!-- TODO CP8 --> | | |
| B | `MOCK_SLOW_RATE=0.3` | <!-- TODO CP8 --> | | |
| C | `LLM_MODEL=mock-llm-large` | <!-- TODO CP8 --> | | |
| D | `docker pause` 1 instance | <!-- TODO CP8 --> | | |
| E | `AGENT_VERSION=v1` | <!-- TODO CP8 --> | | |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

<!-- TODO CP8 -->

### 4.3 Debug bằng trace

Chọn 1 trace chậm nhất bạn tìm được:

- `trace_id`: <!-- TODO CP8 -->
- Tổng thời gian: ... ms
- Span chiếm nhiều thời gian nhất: ... (... ms, ...%)
- Dòng log tương ứng (grep theo `trace_id`):

```json

```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | <!-- TODO CP8 --> | | | | |
| 3 | <!-- TODO CP8 --> | | | | |

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

<!-- TODO CP8 -->

---

## 6. Kết luận

- 3 điều bạn học được về benchmark & observability:
  1. <!-- TODO CP8 -->
  2. <!-- TODO CP8 -->
  3. <!-- TODO CP8 -->
- Nếu đưa agent này lên production thật, bạn sẽ thêm metric / alert nào nữa?

<!-- TODO CP8 -->
