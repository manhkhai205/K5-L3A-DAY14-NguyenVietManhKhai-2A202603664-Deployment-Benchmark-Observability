# Day 14 Lab — Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns phát hiện trong `develop/app.py`

Qua kiểm tra [01-localhost-vs-production/develop/app.py](01-localhost-vs-production/develop/app.py) và đối chiếu với bản sửa trong [01-localhost-vs-production/production/app.py](01-localhost-vs-production/production/app.py) và [01-localhost-vs-production/production/config.py](01-localhost-vs-production/production/config.py), có 7 anti-pattern sau:

1. **Hardcode secrets trong source code** (`develop/app.py` dòng 17–18):
   - Gán trực tiếp `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"`. Nếu push lên Git sẽ lộ thông tin nhạy cảm ngay lập tức.
   - **Đã sửa:** `production/config.py` dòng 27, 32 đọc từ biến môi trường bằng `os.getenv("OPENAI_API_KEY", "")` và `os.getenv("AGENT_API_KEY", "")`, kèm file mẫu `.env.example`.
2. **Hardcode cấu hình, không quản lý theo môi trường** (`develop/app.py` dòng 21–22):
   - Gán cứng `DEBUG = True` và `MAX_TOKENS = 500`, muốn đổi giữa dev/staging/prod phải sửa code.
   - **Đã sửa:** `production/config.py` dòng 15–46 dùng `@dataclass class Settings` đọc toàn bộ cấu hình qua `os.getenv(...)` và có hàm `validate()` để fail-fast nếu thiếu `AGENT_API_KEY` khi `ENVIRONMENT == "production"`.
3. **Dùng `print()` thay cho structured logging và log trực tiếp secret** (`develop/app.py` dòng 33–38):
   - Dùng `print(...)` nên không có timestamp, log level hay format chuẩn JSON để hệ thống thu thập log parse; đặc biệt dòng 34 còn `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` làm lộ key ra stdout.
   - **Đã sửa:** `production/app.py` dòng 28–32 cấu hình `logging.basicConfig` xuất JSON (`time`, `level`, `msg`), và dòng 111–122 ghi log sự kiện `agent_request` / `agent_response` bằng `json.dumps(...)` với `question_length`, `client_ip`, `response_length`, tuyệt đối không log secret.
4. **Thiếu endpoint kiểm tra sức khỏe (health check & readiness check)** (`develop/app.py` dòng 42–43):
   - Không có `/health` hay `/ready`, nên cloud platform hoặc load balancer không biết container còn sống hay đã sẵn sàng nhận traffic để tự restart hoặc điều hướng.
   - **Đã sửa:** `production/app.py` dòng 135–161 bổ sung `GET /health` (liveness probe trả `200` cùng uptime, version, environment, timestamp) và `GET /ready` (readiness probe trả `503` khi `is_ready == False`, `200` khi sẵn sàng).
5. **Bind cứng `host="localhost"`, `port=8000` và bật `reload=True`** (`develop/app.py` dòng 49–54):
   - `host="localhost"` chỉ nhận kết nối nội bộ (không nhận traffic từ ngoài container), `port=8000` không nhận cổng động `PORT` do Railway/Render inject, và `reload=True` gây tốn tài nguyên và không ổn định trên production.
   - **Đã sửa:** `production/app.py` dòng 194–199 dùng `host=settings.host` (mặc định `0.0.0.0`), `port=settings.port` (đọc từ `PORT`), và `reload=settings.debug` (mặc định `False`).
6. **Không xử lý vòng đời ứng dụng và graceful shutdown (`SIGTERM`)**:
   - Khi tắt hoặc deploy phiên bản mới, process dừng đột ngột, có thể cắt ngang request đang xử lý và không dọn dẹp kết nối.
   - **Đã sửa:** `production/app.py` dòng 39–67 dùng `lifespan` quản lý startup/shutdown và dòng 180–189 đăng ký `signal.signal(signal.SIGTERM, handle_sigterm)` để ghi log và cho phép request đang chạy hoàn thành trước khi thoát.
7. **Thiếu cấu hình CORS và thiết kế API chưa chuẩn production** (`develop/app.py` dòng 30–31):
   - `POST /ask` nhận `question` qua query parameter (`?question=...`), không validate input chuẩn hóa và không giới hạn CORS origins.
   - **Đã sửa:** `production/app.py` dòng 77–82 thêm `CORSMiddleware` với `allow_origins=settings.allowed_origins` và dòng 102–108 đọc JSON body, trả HTTP `422` rõ ràng nếu thiếu `question`.

---

### Exercise 1.2: Kết quả chạy bản `develop`

Lệnh test (bản `develop` nhận `question` qua query parameter):
```bash
curl -X POST "http://localhost:8000/ask?question=Hello"
```

Log thực tế quan sát được trên terminal chạy `01-localhost-vs-production/develop/app.py`:
```text
INFO:     Application startup complete.
[DEBUG] Got question: Hello
[DEBUG] Using key: sk-hardcoded-fake-key-never-do-this
[DEBUG] Response: Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic.
INFO:     127.0.0.1:43312 - "POST /ask?question=Hello HTTP/1.1" 200 OK
^CINFO:     Shutting down
INFO:     Waiting for application shutdown.
INFO:     Application shutdown complete.
INFO:     Finished server process [2427]
INFO:     Stopping reloader process [2425]
```

**Nhận xét:**
- Dù API trả `200 OK`, log đã in thẳng chuỗi secret `sk-hardcoded-fake-key-never-do-this` ra màn hình.
- Tiến trình chạy kèm reloader (`Stopping reloader process [2425]`) do `reload=True` được hardcode.

---

### Exercise 1.3: Kết quả chạy bản `production` & Bảng so sánh

Kết quả test các endpoint của `01-localhost-vs-production/production/app.py`:
```bash
curl http://localhost:8000/health
# {"status":"ok","uptime_seconds":213.6,"version":"1.0.0","environment":"development","timestamp":"2026-11-25T09:31:13.414741+00:00"}

curl http://localhost:8000/ready
# {"ready":true}

curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'
# {"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","model":"gpt-4o-mini"}
```

Log server:
```text
INFO:     127.0.0.1:37096 - "GET /health HTTP/1.1" 200 OK
INFO:     127.0.0.1:37112 - "GET /ready HTTP/1.1" 200 OK
INFO:     127.0.0.1:37124 - "POST /ask HTTP/1.1" 200 OK
```

#### Bảng so sánh Develop vs Production

| Feature | Develop | Production | Tại sao quan trọng? |
| :--- | :--- | :--- | :--- |
| **Secrets** | Hardcode `OPENAI_API_KEY`, `DATABASE_URL` trong code | Đọc từ biến môi trường (`os.getenv`), mẫu trong `.env.example`, không commit `.env` | Tránh lộ API key/mật khẩu khi đưa code lên Git và dễ xoay vòng (rotate) key |
| **Config management** | Hardcode `DEBUG = True`, `MAX_TOKENS = 500` | Tập trung trong `Settings` (`config.py`), validate fail-fast theo `ENVIRONMENT` | Dễ thay đổi cấu hình giữa dev/staging/prod mà không cần sửa code hay build lại |
| **Logging** | `print()` tự do, in cả API key ra stdout | `logging` xuất JSON có cấu trúc (`time`, `level`, `msg`), không log secret | Dễ tìm kiếm/lọc log trên hệ thống tập trung (Loki, Datadog) và bảo mật thông tin |
| **Health & Readiness check** | Không có `/health` và `/ready` | Có `GET /health` (liveness) và `GET /ready` (readiness, trả `503` nếu chưa sẵn sàng) | Cloud orchestrator/Load balancer biết khi nào container hỏng để restart và khi nào sẵn sàng nhận traffic |
| **Host / Port / Reload** | `host="localhost"`, `port=8000`, `reload=True` | `host="0.0.0.0"`, `port` đọc từ env `PORT`, `reload=settings.debug` (`False`) | Cho phép nhận kết nối từ bên ngoài container, tương thích cổng động trên cloud, ổn định hiệu năng |
| **Graceful shutdown & Lifespan** | Không có `lifespan` hay handler `SIGTERM` | Có `lifespan` quản lý startup/shutdown và handler `SIGTERM` | Đảm bảo request đang xử lý được hoàn tất trước khi container tắt khi deploy/scale |
| **CORS & Input validation** | Không có CORS; `POST /ask` nhận query string | Có `CORSMiddleware` theo `ALLOWED_ORIGINS`; `POST /ask` nhận JSON và trả `422` nếu thiếu `question` | Kiểm soát nguồn gọi từ trình duyệt và chuẩn hóa contract API khi giao tiếp với client |

---

## Part 2: Docker

### Exercise 2.1: Phân tích Dockerfile cơ bản (`02-docker/develop/Dockerfile`)

1. **Base image:** `python:3.11` (bản full Python ~1 GB).
2. **Working directory:** `/app` (`WORKDIR /app`).
3. **Tại sao `COPY requirements.txt` đứng trước `COPY app.py`:** Tận dụng cơ chế Docker layer cache. File `requirements.txt` ít thay đổi hơn source code, nên khi chỉ sửa `app.py` và build lại, Docker tái sử dụng lại layer `RUN pip install --no-cache-dir -r requirements.txt` từ cache mà không phải tải và cài lại toàn bộ thư viện.
4. **Phân biệt `CMD` và `ENTRYPOINT`:**
   - `ENTRYPOINT` định nghĩa tiến trình chính cố định của container (khó bị ghi đè, chỉ đổi khi truyền cờ `--entrypoint`).
   - `CMD` định nghĩa lệnh mặc định (hoặc tham số mặc định cho `ENTRYPOINT`) và dễ dàng bị ghi đè bằng đối số truyền ở cuối lệnh `docker run <image> <args>`.

---

### Exercise 2.2: Build và test container `my-agent:develop`

Lệnh build từ gốc repo và chạy container:
```bash
docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
docker run -d --rm --name test-dev -p 8000:8000 my-agent:develop
curl -X POST "http://localhost:8000/ask?question=What+is+Docker"
```

Kết quả trả về thực tế:
```json
{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
```

---

### Exercise 2.3: Multi-stage build & So sánh kích thước image

Phân tích [02-docker/production/Dockerfile](02-docker/production/Dockerfile):
- **Stage 1 (`builder` — `FROM python:3.11-slim AS builder`):** Cài build tools hệ thống (`gcc`, `libpq-dev`) để biên dịch dependencies và cài các package Python bằng `pip install --no-cache-dir --user -r requirements.txt` vào `/root/.local`.
- **Stage 2 (`runtime` — `FROM python:3.11-slim AS runtime`):** Tạo non-root user `appuser`, chỉ copy kết quả đã cài từ builder (`COPY --from=builder /root/.local /home/appuser/.local`), copy `main.py` và `utils/mock_llm.py`, thiết lập `HEALTHCHECK` và chạy `uvicorn` với 2 workers.
- **Tại sao image nhỏ hơn:** Dùng base `python:3.11-slim` thay vì `python:3.11` full, đồng thời loại bỏ hoàn toàn `gcc`, `libpq-dev`, apt cache và các file trung gian của giai đoạn build khỏi image cuối.

Kết quả đo thực tế bằng `docker images my-agent`:
```text
IMAGE               ID             DISK USAGE   CONTENT SIZE   EXTRA
my-agent:advanced   008300206f6b        240MB         57.4MB
my-agent:develop    b12449b8a04e       1.67GB          426MB
```

- **Develop (`my-agent:develop`):** Disk Usage **1.67 GB** (1670 MB) · Content Size **426 MB**
- **Production (`my-agent:advanced`):** Disk Usage **240 MB** · Content Size **57.4 MB**
- **Chênh lệch:** Giảm **85.6%** theo Disk Usage (`(1670 - 240) / 1670 ≈ 85.63%`) và giảm **86.5%** theo Content Size (`(426 - 57.4) / 426 ≈ 86.53%`), đạt chuẩn `< 500 MB`.

---

### Exercise 2.4: Docker Compose stack & Kiến trúc

Sơ đồ kiến trúc stack trong [02-docker/production/docker-compose.yml](02-docker/production/docker-compose.yml) và [nginx.conf](02-docker/production/nginx/nginx.conf):

```text
┌────────┐   HTTP :80 / :443    ┌──────────────────────────────┐
│ Client │ ───────────────────► │  nginx (nginx:alpine)        │
└────────┘                      │  Rate limit 10r/s + Headers  │
                                └──────────────┬───────────────┘
                                               │ (network: internal)
                                               ▼
                                ┌──────────────────────────────┐
                                │  agent (my-agent:advanced)   │
                                │  uvicorn :8000 (2 workers)   │
                                └──────┬───────────────┬───────┘
                                       │               │
                 redis://redis:6379/0  ▼               ▼  http://qdrant:6333
                         ┌──────────────────┐   ┌──────────────────┐
                         │ redis:7-alpine   │   │ qdrant:v1.9.0    │
                         │ vol: redis_data  │   │ vol: qdrant_data │
                         └──────────────────┘   └──────────────────┘
```

**Cách các service giao tiếp:**
- Các service nằm chung trong bridge network `internal` và gọi nhau bằng tên service DNS nội bộ (`http://agent:8000`, `redis://redis:6379/0`, `http://qdrant:6333`).
- Chỉ `nginx` mở cổng `80` và `443` ra máy host; các service `agent`, `redis`, `qdrant` được cô lập bên trong mạng `internal`.
- `agent` khai báo `depends_on` với `condition: service_healthy` để chỉ khởi động sau khi `redis` và `qdrant` đã vượt qua health check.

Trạng thái stack thực tế (`docker compose -p k5-day14-docker ps`):
```text
NAME                       IMAGE                   COMMAND                  SERVICE   CREATED         STATUS                   PORTS
k5-day14-docker-agent-1    k5-day14-docker-agent   "uvicorn main:app --…"   agent     6 minutes ago   Up 5 minutes (healthy)   8000/tcp
k5-day14-docker-nginx-1    nginx:alpine            "/docker-entrypoint.…"   nginx     6 minutes ago   Up 5 minutes             0.0.0.0:80->80/tcp, [::]:80->80/tcp, 0.0.0.0:443->443/tcp, [::]:443->443/tcp
k5-day14-docker-qdrant-1   qdrant/qdrant:v1.9.0    "./entrypoint.sh"        qdrant    6 minutes ago   Up 6 minutes (healthy)   6333-6334/tcp
k5-day14-docker-redis-1    redis:7-alpine          "docker-entrypoint.s…"   redis     6 minutes ago   Up 6 minutes (healthy)   6379/tcp
```

Kết quả test qua Nginx (`http://localhost`):
```bash
curl http://localhost/health
# {"status":"ok","uptime_seconds":369.7,"version":"2.0.0","timestamp":"2026-11-25T10:02:41.643212"}

curl -X POST http://localhost/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Explain microservices"}'
# {"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

---

## Part 3: Cloud Deployment

### Exercise 3.1: Deploy agent Part 6 lên Railway

- **Public URL:** https://k5-l3a-day14-nguyenvietmanhkhai-2a202603664-depl-production.up.railway.app
- **Chi tiết triển khai & biến môi trường:** Xem [DEPLOYMENT.md](DEPLOYMENT.md)
- **Ảnh chụp màn hình:** `screenshots/dashboard.png`, `screenshots/running.png`, `screenshots/test.png`

**Kết quả kiểm tra 4 lệnh CP6 trên URL public:**

| Endpoint | Điều kiện | HTTP Code | Response thực tế |
| :--- | :--- | :---: | :--- |
| `GET /health` | Không cần key | **200** | `{"status":"ok","environment":"production"}` |
| `GET /ready` | Kết nối Redis Railway | **200** | `{"status":"ready","redis":"ok"}` |
| `POST /ask` | Không gửi `X-API-Key` | **401** | `{"detail":"Invalid or missing API key"}` |
| `POST /ask` | Gửi `X-API-Key: $AGENT_API_KEY` | **200** | `{"question":"Hello","answer":"Đây là câu trả lời từ AI agent (mock)...","cost_usd":2.07e-05}` |

---

### So sánh `railway.toml` vs `render.yaml`

| Tiêu chí | [06-lab-complete/railway.toml](06-lab-complete/railway.toml) | [06-lab-complete/render.yaml](06-lab-complete/render.yaml) |
| :--- | :--- | :--- |
| **Định dạng** | TOML (`[build]`, `[deploy]`) | YAML (Blueprint schema: `services:`) |
| **Phạm vi cấu hình** | Chỉ cấu hình build & deploy cho **một service** hiện tại; Redis và biến môi trường được thêm/quản lý riêng trên Railway Dashboard hoặc CLI. | Khai báo **Infrastructure-as-Code cho cả stack** trong 1 file (tên service, runtime, plan, `envVars`, và có thể khai báo kèm Redis/DB). |
| **Health check** | `healthcheckPath = "/health"`, `healthcheckTimeout = 30` | `healthCheckPath: /health` |
| **Quản lý biến môi trường & Secrets** | Không khai báo secret trong file; cấu hình trực tiếp trên dashboard hoặc qua `railway variables set` (và reference tới Redis plugin). | Khai báo danh sách `envVars` ngay trong YAML; dùng `generateValue: true` (Render tự sinh chuỗi ngẫu nhiên) hoặc `sync: false` (nhập tay trên dashboard khi tạo Blueprint) để không lộ secret vào Git. |
| **Restart & Cơ chế deploy** | Hỗ trợ `restartPolicyType = "ON_FAILURE"` + `restartPolicyMaxRetries = 3`; có thể deploy nhanh từ máy bằng `railway up` hoặc nối GitHub. | Quản lý theo Render Blueprint sync trực tiếp từ GitHub repository. |

**Vì sao có sự khác biệt này:** Railway thiết kế theo hướng *service-first* (mỗi service đọc `railway.toml` riêng còn hạ tầng phụ trợ & env vars gắn trực tiếp trên canvas/project), còn Render Blueprint dùng `render.yaml` làm đặc tả IaC tổng thể để tái tạo toàn bộ dịch vụ và cấu hình môi trường từ một lần import GitHub repo.

---

### Exercise 3.3: Mô tả pipeline CI/CD GCP Cloud Run

Dựa trên [cloudbuild.yaml](03-cloud-deployment/production-cloud-run/cloudbuild.yaml) và [service.yaml](03-cloud-deployment/production-cloud-run/service.yaml), pipeline CI/CD tự động chạy khi push lên nhánh `main` qua 4 bước tuần tự (`waitFor`):
1. **`test`** (`python:3.11-slim`): cài đặt `requirements.txt` + `pytest` và chạy `pytest tests/ -v --tb=short`; chỉ khi test pass mới đi tiếp.
2. **`build`** (`gcr.io/cloud-builders/docker`): build Docker image từ `.`, gắn đồng thời 2 tag `$COMMIT_SHA` và `latest`, tận dụng `--cache-from` để tăng tốc build.
3. **`push`** (`gcr.io/cloud-builders/docker`): đẩy toàn bộ tag image lên Google Container Registry (`gcr.io/$PROJECT_ID/ai-agent`).
4. **`deploy`** (`gcr.io/cloud-builders/gcloud`): triển khai bản `$COMMIT_SHA` lên Cloud Run (`asia-southeast1`), cấu hình `--min-instances=1` (giảm cold start), `--max-instances=10`, `512Mi`/1 vCPU, và inject secret từ Secret Manager (`--set-secrets`). Song song đó, `service.yaml` định nghĩa hạ tầng Knative (IaC) với `containerConcurrency: 80`, `livenessProbe` (`/health`) và `startupProbe` (`/ready`).

---

## Part 4: API Security

### Exercise 4.1: API Key Authentication (`04-api-gateway/develop/app.py`)

1. **API key được kiểm tra ở đâu:**
   - Trong [04-api-gateway/develop/app.py](04-api-gateway/develop/app.py) (dòng 36, 39–54), `api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)` đọc header `X-API-Key`, sau đó hàm dependency `verify_api_key` kiểm tra và được gắn vào route `POST /ask` qua `_key: str = Depends(verify_api_key)` (dòng 70). Các endpoint `/` và `/health` được giữ public.
2. **Điều gì xảy ra nếu thiếu hoặc sai key:**
   - Thiếu header `X-API-Key`: trả `401 Unauthorized` (`Missing API key. Include header: X-API-Key: <your-key>`).
   - Sai key: trả `403 Forbidden` (`Invalid API key.`).
3. **Cách rotate key (xoay vòng khóa):**
   - Hỗ trợ nhiều key hợp lệ cùng lúc trong biến môi trường (ví dụ `AGENT_API_KEYS=old_key,new_key`), phát hành key mới cho client, theo dõi tới khi toàn bộ client chuyển sang key mới rồi gỡ `old_key` khỏi cấu hình và restart/reload dịch vụ mà không gây gián đoạn (zero-downtime).

#### Kết quả test thực tế (`04-api-gateway/develop`, `AGENT_API_KEY=secret-key-123`)

**1. Không có header `X-API-Key` → `401 Unauthorized`:**
```http
HTTP/1.1 401 Unauthorized
date: Wed, 25 Nov 2026 10:22:08 GMT
server: uvicorn
content-length: 67
content-type: application/json

{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}
```

**2. Có header `X-API-Key: secret-key-123` → `200 OK`:**
```http
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 10:22:08 GMT
server: uvicorn
content-length: 145
content-type: application/json

{"question":"Hello","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```

---

### Exercise 4.2 & 4.3: JWT Authentication & Rate Limiting (`04-api-gateway/production/`)

#### Trả lời câu hỏi về `rate_limiter.py`
1. **Thuật toán được dùng:** **Sliding Window Counter** — dùng `collections.deque` lưu danh sách timestamp của từng request theo `user_id` trong cửa sổ `window_seconds = 60` giây, loại bỏ các timestamp cũ hơn `now - 60` ở đầu hàng đợi trước khi kiểm tra (`04-api-gateway/production/rate_limiter.py` dòng 7, 27, 39–40).
2. **Giới hạn (limit):**
   - User thường (`role == "user"`, tài khoản `student`): **10 requests/phút** (`rate_limiter_user`).
   - Admin (`role == "admin"`, tài khoản `teacher`): **100 requests/phút** (`rate_limiter_admin`).
3. **Cách bypass/nâng giới hạn cho admin:** Trong [04-api-gateway/production/app.py](04-api-gateway/production/app.py) dòng 141, server chọn limiter dựa trên `role` trích từ payload JWT (`limiter = rate_limiter_admin if role == "admin" else rate_limiter_user`). Nếu muốn bypass hoàn toàn rate limit cho admin, chỉ cần bỏ qua bước gọi `limiter.check(username)` khi `role == "admin"`.

#### Kết quả test thực tế (`curl -i`, đã che token)

**1. Lấy JWT token tại `POST /auth/token` (`student` / `demo123`):**
```json
{"access_token":"eyJhbGci...<REDACTED>","token_type":"bearer","expires_in_minutes":60,"hint":"Include in header: Authorization: Bearer eyJhbGci...<REDACTED>"}
```

**2. Trường hợp gửi token không hợp lệ → `403 Forbidden`:**
```http
HTTP/1.1 403 Forbidden
date: Wed, 25 Nov 2026 10:11:44 GMT
server: uvicorn
content-length: 27
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"detail":"Invalid token."}
```

**3. Trường hợp token hợp lệ (`POST /ask`) → `200 OK` (request 1 và request thứ 10 trong cửa sổ 60s):**
```http
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 10:14:08 GMT
server: uvicorn
content-length: 192
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"question":"Explain JWT","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.","usage":{"requests_remaining":9,"budget_remaining_usd":...}}
```
Và trong vòng lặp 15 lần tiếp theo (từ `Test 1` đến `Test 9` trả `200 OK` với `requests_remaining` giảm dần từ `8` về `0`):
```http
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 10:14:20 GMT
server: uvicorn
content-length: 179
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"question":"Test 1","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","usage":{"requests_remaining":8,"budget_remaining_usd":3.5e-05}}
```

**4. Chạm ngưỡng 10 req/phút (từ `Request 10` đến `Request 15` trong vòng lặp, tức request thứ 11–16 trong 60s) → `429 Too Many Requests`:**
```http
HTTP/1.1 429 Too Many Requests
date: Wed, 25 Nov 2026 10:14:21 GMT
server: uvicorn
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
x-ratelimit-reset: 1795601722
retry-after: 47
content-length: 98
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
```

**Log server thực tế quan sát được (10 request `200 OK` kèm cost tracking, 6 request tiếp theo bị chặn `429`):**
```text
INFO:     127.0.0.1:58050 - "POST /auth/token HTTP/1.1" 200 OK
INFO:cost_guard:Usage: user=student req=1 cost=$0.0000/1.0
INFO:     127.0.0.1:59096 - "POST /ask HTTP/1.1" 200 OK
...
INFO:cost_guard:Usage: user=student req=10 cost=$0.0002/1.0
INFO:     127.0.0.1:43424 - "POST /ask HTTP/1.1" 200 OK
INFO:     127.0.0.1:43428 - "POST /ask HTTP/1.1" 429 Too Many Requests
INFO:     127.0.0.1:43434 - "POST /ask HTTP/1.1" 429 Too Many Requests
INFO:     127.0.0.1:43436 - "POST /ask HTTP/1.1" 429 Too Many Requests
INFO:     127.0.0.1:43450 - "POST /ask HTTP/1.1" 429 Too Many Requests
INFO:     127.0.0.1:43460 - "POST /ask HTTP/1.1" 429 Too Many Requests
INFO:     127.0.0.1:43476 - "POST /ask HTTP/1.1" 429 Too Many Requests
```

---

### Exercise 4.4: Cost Guard & Giải thích

- **Cơ chế hoạt động trong [04-api-gateway/production/cost_guard.py](04-api-gateway/production/cost_guard.py):**
  - Trước khi gọi LLM, gọi `cost_guard.check_budget(username)`: kiểm tra ngân sách tổng (`global_daily_budget_usd = $10/ngày` → vượt sẽ trả `503`), sau đó kiểm tra ngân sách của từng user (`daily_budget_usd = $1/ngày` → vượt sẽ trả `402 Payment Required`), và ghi log cảnh báo khi mức dùng đạt `80%`.
  - Sau khi gọi LLM xong, gọi `cost_guard.record_usage(username, input_tokens, output_tokens)` để quy đổi token thành USD theo `PRICE_PER_1K_INPUT_TOKENS` (`$0.00015`) và `PRICE_PER_1K_OUTPUT_TOKENS` (`$0.0006`) rồi cộng dồn vào mức chi tiêu.
- **Tại sao cần cả Rate Limiting và Cost Guard:**
  - **Rate Limiting** bảo vệ **tốc độ & tài nguyên hệ thống** (giới hạn số request/phút để chống spam, brute-force, DoS).
  - **Cost Guard** bảo vệ **ngân sách tiền** (ngăn hóa đơn LLM tăng vọt). Nếu chỉ có rate limit, kẻ xấu hoặc người dùng hợp lệ vẫn có thể gửi ít request nhưng prompt/output rất dài hoặc dùng model đắt để đốt hết tiền mà chưa chạm ngưỡng request/phút.
- **Cách triển khai trong Production (Redis):**
  - Lưu chi phí theo khóa thời gian trong Redis (ví dụ `budget:{user_id}:{YYYY-MM}` hoặc theo ngày), đọc số tiền hiện tại để kiểm tra trước khi gọi LLM, cộng chi phí nguyên tử bằng `INCRBYFLOAT` và đặt `EXPIRE` tự dọn key hết hạn. Việc lưu trên Redis thay vì RAM đảm bảo dữ liệu dùng chung chính xác giữa nhiều worker/instance và không bị reset về `0` khi container restart.

---

## Part 5: Scaling & Reliability

### Exercise 5.1 & 5.2: Health/Readiness Checks & Graceful Shutdown (`05-scaling-reliability/develop/app.py`)

- **Phân biệt Liveness (`/health`) và Readiness (`/ready`):**
  - `GET /health` (**Liveness probe**): Kiểm tra tiến trình ứng dụng còn sống không. Trả về `200 OK` khi process đang chạy; nếu fail hoặc timeout, orchestrator/platform sẽ tự động restart container.
  - `GET /ready` (**Readiness probe**): Kiểm tra instance đã sẵn sàng nhận traffic chưa. Trả về `503 Service Unavailable` khi đang startup, đang shutdown hoặc mất kết nối tới dependency (Redis/DB) để Load Balancer tạm ngưng điều hướng request vào instance đó mà không cần restart container.
- **Graceful Shutdown (`SIGTERM`):**
  - Khi nhận signal `15` (`SIGTERM`), ứng dụng đặt cờ `_is_ready = False` để ngừng nhận request mới, chờ các request đang xử lý (`_in_flight_requests`) hoàn thành (tối đa `timeout_graceful_shutdown = 30s`), dọn dẹp kết nối rồi mới thoát với exit code `0`.

**Kết quả chạy thực tế (`05-scaling-reliability/develop/app.py`):**
```json
// GET /health -> 200 OK
{"status":"ok","uptime_seconds":1.6,"version":"1.0.0","environment":"development","timestamp":"2026-11-25T10:23:37.493728+00:00","checks":{"memory":{"status":"ok","used_percent":16.1}}}

// GET /ready -> 200 OK
{"ready":true,"in_flight_requests":1}
```
Khi gửi `kill -TERM $PID`, server ghi nhận signal `15` và hoàn tất shutdown an toàn:
```text
INFO:     Shutting down
INFO:     Waiting for application shutdown.
2026-11-25 17:23:37,695 INFO 🔄 Graceful shutdown initiated...
2026-11-25 17:23:37,696 INFO ✅ Shutdown complete
INFO:     Application shutdown complete.
INFO:     Finished server process [4424]
2026-11-25 17:23:37,696 INFO Received signal 15 — uvicorn will handle graceful shutdown
```

---

### Exercise 5.3–5.5: Stateless Design, Nginx Load Balancing (3 Instances) & `test_stateless.py`

- **Vì sao state trong RAM bị hỏng khi scale nhiều instance:**
  - Khi chạy nhiều container `agent` sau Nginx Load Balancer, các request trong cùng một phiên hội thoại có thể được điều hướng tới các instance khác nhau (ví dụ request 1 vào `agent-1`, request 2 vào `agent-2`). Nếu lưu lịch sử trong bộ nhớ RAM cục bộ của từng process, `agent-2` sẽ không thấy lịch sử ở `agent-1` và toàn bộ dữ liệu cũng bị mất khi container restart.
- **Giải pháp Stateless với Redis:**
  - Đưa toàn bộ session và conversation history ra Redis dùng chung (`REDIS_URL=redis://redis:6379/0`). Nhờ đó mọi instance đều bình đẳng và có thể xử lý bất kỳ request nào của người dùng.

**Kết quả triển khai stack (`docker compose -p k5-day14-scaling up -d --build --scale agent=3`):**
- Hệ thống chạy 5 container: `k5-day14-scaling-agent-1`, `k5-day14-scaling-agent-2`, `k5-day14-scaling-agent-3`, `k5-day14-scaling-redis-1` (`healthy`), và `k5-day14-scaling-nginx-1` (mở cổng `8080 -> 80`).
- Log của cả 3 instance `agent-1`, `agent-2`, `agent-3` đều xác nhận `Storage: Redis ✅`.

**Kết quả chạy `python test_stateless.py` và phân tích:**
```text
Session ID: 9879fa3d-20b3-40bb-9f33-f3a97bd71b78

Request 1: [instance-a8a085]  Q: What is Docker?
Request 2: [instance-c798bb]  Q: Why do we need containers?
Request 3: [instance-9d4cc6]  Q: What is Kubernetes?
Request 4: [instance-a8a085]  Q: How does load balancing work?
Request 5: [instance-c798bb]  Q: What is Redis used for?

Total requests: 5
Instances used: {'instance-c798bb', 'instance-a8a085', 'instance-9d4cc6'}
✅ All requests served despite different instances!

--- Conversation History ---
Total messages: 10
✅ Session history preserved across all instances via Redis!
```
- **Phân tích log & tải:** 5 request `POST /chat` tới Nginx (`http://localhost:8080`) đã được cân bằng tải qua cả **3 instance khác nhau** (`agent-2` xử lý 2 `POST /chat`, `agent-3` xử lý 2 `POST /chat`, `agent-1` xử lý 1 `POST /chat` và 1 `GET /chat/9879fa3d-20b3-40bb-9f33-f3a97bd71b78/history`).
- Dù các câu hỏi đi qua 3 container độc lập, lịch sử lấy về vẫn giữ nguyên đủ **10 tin nhắn** (5 câu hỏi `user` + 5 câu trả lời `assistant`), chứng minh thiết kế stateless với Redis hoạt động đúng khi scale ngang.

---

## Part 6: Final Project (`check_production_ready.py`)

Chạy `python check_production_ready.py` trong `06-lab-complete/` (chế độ đầy đủ có Docker trong WSL `Ubuntu-22.04`, Python `3.11.18`):

- Kích thước Docker image: **238 MB** (`< 500 MB`), `docker stop` thoát với exit code `0` trong `1.1s`.
- Log JSON hợp lệ (`17 dòng JSON`), rate limit `429` giữ state trong Redis sau restart, `/ready` trả `503` khi mất Redis, graceful shutdown `SIGTERM` trả `200` cho request đang chạy và thoát `0`.

```text
================================================================
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```

---

## AI Log

| Thời điểm | Mục | Đã hỏi gì / Nhận gì | Tự kiểm tra & chỉnh sửa |
| :--- | :--- | :--- | :--- |
| 2026-11-25 | CP0 | Nhờ hỗ trợ chẩn đoán lỗi `Wsl/Service/E_UNEXPECTED` khi cài Ubuntu WSL2 và lỗi thiếu quyền Docker socket trong WSL. | Tự cài `Ubuntu-22.04`, tạo venv Python `3.11.18` (`os.name == posix`), cấu hình Docker Desktop WSL integration và kiểm tra chạy lệnh thực tế. |
| 2026-11-25 | CP1 (Part 1) | Nhờ tổng hợp kết quả chạy thực tế của bản `develop` và `production` thành file `MISSION_ANSWERS.md` đúng mẫu. | Đã tự chạy cả 2 server, gọi `curl` kiểm tra `/ask`, `/health`, `/ready`, đối chiếu trực tiếp từng dòng code trong `develop/app.py`, `production/app.py` và `config.py`. |
| 2026-11-25 | CP2 (Part 2) | Nhờ tổng hợp các số liệu build/kích thước Docker và kết quả chạy Compose vào mục Part 2 trong `MISSION_ANSWERS.md`. | Đã tự build `my-agent:develop` & `my-agent:advanced`, đo `docker images`, test container và chạy stack `k5-day14-docker` qua Nginx. |
| 2026-11-25 | CP3 (Part 4) | Nhờ chạy kiểm tra Exercise 4.1 (`401`/`200`), che JWT token và tổng hợp output test `curl -i` + giải thích rate limit/cost guard vào Part 4 của `MISSION_ANSWERS.md`. | Đã tự chạy `04-api-gateway/production/app.py`, lấy JWT token cho `student`, test sai token (`403`), hợp lệ (`200`) và vòng lặp 15 lần chạm giới hạn `429`; chạy thêm Exercise 4.1 để lấy output `401` và `200`. |
| 2026-11-25 | CP4 (Part 5) | Nhờ tổng hợp kết quả health/readiness, graceful shutdown và kiểm thử stateless 3 instance vào Part 5 của `MISSION_ANSWERS.md`. | Đã tự chạy `05-scaling-reliability/develop/app.py` với `kill -TERM`, scale stack `k5-day14-scaling` lên 3 agent với Nginx + Redis và chạy `test_stateless.py`. |
| 2026-11-25 | CP5 (Part 6) | Nhờ hoàn thiện các TODO trong `06-lab-complete/` (config, auth, Redis rate limit/cost guard, JSON logging, health/ready, Dockerfile multi-stage, Compose, railway.toml/render.yaml). | Đã rà soát toàn bộ mã nguồn, chạy `python check_production_ready.py` chế độ đầy đủ có Docker trong WSL và kiểm chứng đạt `PASS 12/12` (`43/43 checks passed`). |
| 2026-11-25 | CP6 (Part 3) | Nhờ kiểm tra 4 endpoint trên URL Railway public, viết `DEPLOYMENT.md`, so sánh `railway.toml` vs `render.yaml` và tóm tắt pipeline Cloud Run vào Part 3 của `MISSION_ANSWERS.md`. | Đã tự tạo service agent + Redis trên Railway, cấu hình biến môi trường (`AGENT_API_KEY`, `REDIS_URL`, `ENVIRONMENT`), deploy thành công và đối chiếu với `cloudbuild.yaml`/`service.yaml`. |
| 2026-11-25 | CP7 (Part 7 Bước 1) | Nhờ chạy benchmark hiệu năng (`load_test.py`) và eval (`run_eval.py`), sửa `KNOWLEDGE_BASE`, viết `.github/workflows/eval.yml` và tổng hợp số liệu vào `BENCHMARK_REPORT.md`. | Đã kiểm chứng toàn bộ 10 file JSON trong `reports/`, xác nhận `eval_v2_fixed.json` đạt `23/23` (`100%`, 0 regression) và đối chiếu từng con số trong báo cáo khớp với JSON. |
