# Deployment Information

## Public URL
https://k5-l3a-day14-nguyenvietmanhkhai-2a202603664-depl-production.up.railway.app

## Platform
Railway (deploy trực tiếp thư mục `06-lab-complete/` bằng `railway.toml` + `Dockerfile`, kết nối Railway Managed Redis)

## Test Commands

```bash
BASE="https://k5-l3a-day14-nguyenvietmanhkhai-2a202603664-depl-production.up.railway.app"
```

### 1. Health Check (`GET /health` → `200`)
```bash
curl -sS -w '\nHTTP %{http_code}\n' "$BASE/health"
# {"status":"ok","environment":"production"}
# HTTP 200
```

### 2. Readiness Check (`GET /ready` → `200`)
```bash
curl -sS -w '\nHTTP %{http_code}\n' "$BASE/ready"
# {"status":"ready","redis":"ok"}
# HTTP 200
```

### 3. API Test — Không có key (`POST /ask` → `401`)
```bash
curl -sS -w '\nHTTP %{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' \
  -d '{"question":"Hello"}'
# {"detail":"Invalid or missing API key"}
# HTTP 401
```

### 4. API Test — Có API key hợp lệ (`POST /ask` → `200`)
```bash
curl -sS -w '\nHTTP %{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $AGENT_API_KEY" \
  -d '{"question":"Hello"}'
# {"question":"Hello","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic.","cost_usd":2.07e-05}
# HTTP 200
```

## Environment Variables Set
- `PORT` (Railway tự động cấp)
- `ENVIRONMENT` (`production`)
- `REDIS_URL` (tham chiếu từ service Redis trên Railway)
- `AGENT_API_KEY` (đặt trên Railway Dashboard, không ghi vào source code)
- `RATE_LIMIT_PER_MINUTE` (mặc định `10`)
- `DAILY_BUDGET_USD` (mặc định `1.0`)

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
