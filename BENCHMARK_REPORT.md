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

### 4.1 Screenshot & Quan sát Grafana (Exercise 7.4)

- [x] Dashboard Grafana khi đang có tải (`screenshots/grafana-dashboard.png` — thấy rõ 4 Golden Signals)
- [x] Một trace chậm trong Jaeger (`screenshots/jaeger-slow-trace.png` — `trace_id`: `e4b2c7cd0aebfd368edbbd4e52eab458`)
- [x] Một trace lỗi trong Jaeger (`screenshots/jaeger-error-trace.png` — `trace_id`: `417412e60320cb37b731de026a369048`, có event `exception`)
- [x] Trang Alerts của Prometheus với ≥ 2 alert đang **firing** (`screenshots/prometheus-alert-firing.png`)

**Trả lời câu hỏi Exercise 7.4 (quan sát từ Prometheus/Grafana khi chạy tải):**
1. **`p95` vs `avg`:** Tại thời điểm chạy tải bình thường (`MOCK_SLOW_RATE=0.03`), `avg ≈ 229.5 ms` và `p95 ≈ 293.1 ms` (gần nhau vì dưới 5% request rơi vào nhóm slow ~1.7s, còn nếu nhìn `p99 ≈ 1700 ms` sẽ thấy khoảng cách lớn do tail latency).
2. **Cân bằng tải Nginx:** Có — Nginx chia đều traffic giữa 2 instance (`172.20.0.4:8000` đạt `21.36 req/s`, `172.20.0.8:8000` đạt `21.38 req/s`).
3. **Vì sao `input tokens/s` (`3276.3 tok/s`) lớn hơn `output tokens/s` (`1713.4 tok/s`):** Ở `AGENT_VERSION=v2`, prompt gửi lên LLM gồm `SYSTEM_PROMPT` + context tài liệu tìm được từ Knowledge Base + câu hỏi, nên độ dài input dài gấp ~2 lần câu trả lời ngắn gọn ở output.
4. **`curl http://localhost:8080/metrics`:** Trả về **`404 Not Found`**, vì `nginx/nginx.conf` chủ động chặn `location = /metrics { return 404; }` để không lộ thông tin nội bộ (route, lưu lượng, chi phí) ra ngoài; chỉ Prometheus trong mạng `obs_net` mới scrape trực tiếp `agent:8000/metrics`.

### 4.2 Thí nghiệm "phá hệ thống" (`promtool test rules` → `SUCCESS`)

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` (`severity: critical`) | `pending` ở `15.1s`, **`firing` ở `75.5s`** | **Error rate** (Golden Signals) & **req/s theo status (`5xx`)** |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` (`severity: warning`) | `pending` ở `20.2s`, **`firing` ở `140.8s`** | **p95 latency** (Golden Signals) & **Latency p50/p95/p99/avg** |
| C | `LLM_MODEL=mock-llm-large` | *(Không tách riêng thí nghiệm C; ghi nhận `LLMCostBurnRateHigh` cũng firing dưới tải dồn)* | `firing` dưới tải dồn `[5m]` | **Cost USD/giờ** & **LLM p95** |
| D | `docker pause k5-day14-observability-agent-1` | `AgentInstanceDown` (`severity: critical`) | **`firing` sau `45.2s`** kể từ lúc `docker pause` (`for: 30s`) | **Instances up** (Golden Signals) & bảng **Instances** |
| E | `AGENT_VERSION=v1` | **Không có alert nào firing** | — | **Retrieval hit ratio** (tụt về 0), **tokens/s** giảm, bảng **version** |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

- Các metric hạ tầng (CPU, HTTP status `200`, latency) đều xanh vì `v1` vẫn trả HTTP `200` nhanh hơn `v2`. Để bắt suy giảm chất lượng, cần: (1) chạy **eval CI/CD quality gate** trên golden dataset trước mỗi lần release/deploy (`run_eval.py --baseline ...`); (2) chạy **online eval / shadow eval** định kỳ hoặc chấm điểm ngẫu nhiên traffic thật bằng LLM-as-judge; (3) theo dõi metric nghiệp vụ/chất lượng như **retrieval hit ratio**, tỉ lệ thumbs-up/down của người dùng, và gắn alert khi retrieval hit ratio tụt bất thường.

### 4.3 Debug bằng trace

Chọn trace chậm nhất tìm được từ Jaeger & log JSON của agent:

- `trace_id`: `e4b2c7cd0aebfd368edbbd4e52eab458`
- Tổng thời gian (`POST /ask`): **`1895.94 ms`** (`agent.run`: `1798.17 ms`)
- Span chiếm nhiều thời gian nhất: **`chat mock-llm-small`** (`1779.89 ms`, **`93.9%`** tổng thời gian request; `agent.retrieve_context` chỉ mất `18.08 ms`)
- Dòng log tương ứng (`docker compose -p k5-day14-observability logs agent | grep e4b2c7cd0aebfd368edbbd4e52eab458`):

```json
{"ts": "2026-11-25T12:54:55.793928+00:00", "level": "INFO", "service": "observable-agent", "instance": "5b1b319a3412", "event": "llm_call", "trace_id": "e4b2c7cd0aebfd368edbbd4e52eab458", "span_id": "1fdfa9d9b20bb925", "request_id": "ae823be1d3f1", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 73, "output_tokens": 35, "cost_usd": 3.2e-05, "llm_ms": 1646.4}
```

*(Trace lỗi tham khảo trong Jaeger — `trace_id`: `417412e60320cb37b731de026a369048`, log `llm_error`: `Upstream LLM error: 503 Service Unavailable (mock)`).*

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Số liệu trích xuất trực tiếp từ [benchmark-results/scale_1_stats.csv](benchmark-results/scale_1_stats.csv) và [benchmark-results/scale_3_stats.csv](benchmark-results/scale_3_stats.csv) (dòng `Aggregated` / `POST /ask`):

| Số instance | RPS (`Aggregated` / `/ask`) | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | `65.49` (`59.73` `/ask`) | `190` (`200` `/ask`) | `240` | `1700` | `58 / 7835` (`0.74%`) |
| 3 | `66.12` (`60.16` `/ask`) | `190` | `230` | `1700` | `70 / 7905` (`0.89%`) |

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

- **Scale lên 3 instance hầu như không đổi RPS (`65.49 → 66.12 req/s`) và chỉ giảm nhẹ `p95` (`240 → 230 ms`), trong khi `p99` giữ nguyên `1700 ms`.**
- **Nguyên nhân & nút thắt:**
  1. **Tải sinh ra từ 100 Locust users bị giới hạn bởi think-time:** Mỗi user nghỉ `0.5–2s` (trung bình `1.25s`) cộng ~`0.24s` xử lý ≈ `1.49s/request`, nên 100 user tối đa chỉ tạo ~`66 req/s`. Với kiến trúc bất đồng bộ (`async FastAPI`), chỉ 1 instance đã dư sức xử lý mức tải này mà chưa bị bão hòa CPU.
  2. **Nút thắt nằm ở upstream LLM latency:** Mỗi request phải chờ `generate()` từ LLM (`120–180ms` + `3%` tail latency `+1500ms`), và khoảng `1%` lỗi `503` đến từ `MOCK_ERROR_RATE=0.01`. Tăng số bản sao agent giúp tăng khả năng chịu tải tổng (capacity) và độ sẵn sàng (HA), chứ không làm từng LLM call đơn lẻ nhanh hơn.

---

## 6. Kết luận

- 3 điều bạn học được về benchmark & observability:
  1. **Đừng tin vào giá trị trung bình hay chỉ nhìn hạ tầng:** `avg` che giấu `tail latency` (`p99`), còn metric hạ tầng xanh rờn không phát hiện được suy giảm chất lượng trả lời (như `AGENT_VERSION=v1`) — phải kết hợp cả load test percentile, eval trên golden dataset và giám sát chất lượng.
  2. **Ba trụ cột Metrics – Traces – Logs bổ trợ lẫn nhau:** Prometheus/Grafana cho biết *có sự cố gì và khi nào* (`AgentHighLatencyP95`), Jaeger chỉ ra *bước nào chậm* (`chat mock-llm-small` chiếm `93.9%`), và `trace_id` nối thẳng sang JSON log để xem chi tiết từng request.
  3. **Scale ngang chỉ giải quyết bottleneck ở tầng app server:** Khi nút thắt nằm ở upstream LLM latency hoặc think-time phía client, thêm replica không giảm `p95`/`p99` của từng request; muốn giảm latency thực sự phải tối ưu prompt/caching/streaming hoặc chọn model nhanh hơn.
- Nếu đưa agent này lên production thật, bạn sẽ thêm metric / alert nào nữa?
  1. **Metric chất lượng & RAG:** `agent_retrieval_hit_ratio`, tỷ lệ câu trả lời fallback/empty, và tỷ lệ feedback tiêu cực từ người dùng (kèm alert khi retrieval hit ratio giảm mạnh).
  2. **Metric Time-to-First-Token (TTFT) & Token-per-second** cho streaming response, cùng **alert ở tầng Nginx/LB** (`502`/`504`/`429` rate) để bắt các lỗi xảy ra trước khi tới được agent.
