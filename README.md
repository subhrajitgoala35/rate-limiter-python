# API Gateway with Rate Limiting

**Language:** Python (FastAPI) &nbsp;|&nbsp; **Needs:** Postgres + Redis

This is a **starter**. The application already works. Your job is everything
that gets it building, tested and running in CI.

---

## You do not need Python installed

You will build this into a container, and the container brings its own
Python 3.12. You are not being asked to extend the app — you are being asked
to ship it.

---

## 1. What this app needs

| | |
|---|---|
| **Runtime** | Python 3.12 |
| **Install dependencies** | `pip install -r requirements.txt` |
| **Start the app** | `uvicorn app.main:app --host 0.0.0.0 --port 8080` |
| **Listens on** | port 8080, bound to `0.0.0.0` |
| **Environment variables** | `DATABASE_URL`, `REDIS_URL` |
| **Needs running first** | Postgres, Redis, and the migrations applied |

### What it does

Sits in front of a small API. Every client gets an API key on a tier - free, basic or pro - and each tier has its own requests-per-minute allowance. Go over it and you get a 429 with a Retry-After. Both a fixed-window and a sliding-window limiter are implemented, and you choose between them per request, so the difference is something you can measure rather than argue about.

### Endpoints

```
GET  /health
GET  /tiers                          the configured allowances
POST /keys                           {"owner":"asha","tier":"free"}
GET  /keys/{api_key}                 tier, and what both limiters currently think
PUT  /keys/{api_key}/tier            {"tier":"pro"} - also resets the counters
GET  /api/{resource}                 the gated call. Header: X-API-Key
                                     ?algorithm=fixed|sliding   (default sliding)
                                     resources: time, quote, echo
GET  /usage/{api_key}                counts by status, and the last ten calls
GET  /explain/boundary?limit=5       the fixed-window flaw, as numbers

Try it:  for i in $(seq 1 8); do curl -s -o /dev/null -w "%{http_code} " \
           -H 'X-API-Key: YOUR_API_KEY_HERE' localhost:8080/api/time
```

`/health` reports Postgres and Redis **separately**. If it says
`postgres: false` the app started fine and your compose wiring is wrong —
do not go looking in the application code.

### Migrations

`migrations/` holds `.sql` files applied **in filename order** before the app
starts. They create the tables and insert sample data. A container running
`psql` over them in order is enough; you do not need a migration tool.

---

## 2. What you must write

| File | What it has to do |
|---|---|
| `Dockerfile` | Install dependencies **before** copying source, pin the base image, do not run as root. |
| `docker-compose.yml` | App + Postgres + Redis + a migration step, one `docker compose up`. |
| `.circleci/config.yml` | lint → unit tests → integration tests → secret scan → image build |
| Unit tests | For `app/buckets.py`. No database, no network. |
| Integration tests | Against a real Postgres and Redis as CircleCI service containers. |

Then push your image to **your own Docker Hub account**, tagged `:1.0`.

### When it works

```bash
docker compose up --build
curl localhost:8080/health
```

```json
{"status":"ok","postgres":true,"redis":true}
```

---

## Where the marks are

`app/buckets.py` is **pure logic** — plain functions over plain data, no
database and no HTTP. Start your tests there. Use pytest:
`pytest --cov=app --cov-report=term-missing`. Minimum 70%.

`boundary_burst(limit)` hands you the timestamps of an attack. Feed them to `fixed_window_check` and to `sliding_log_check` in the same test and assert that the two disagree - that one assertion is the whole point of this project.

## Why Redis is here

This is the one project where Redis is not a cache - it is the feature. The fixed-window limiter is a single INCR with an EXPIRE, issued in one pipeline so a counter can never be created without a TTL. The sliding window is a sorted set scored by timestamp: ZREMRANGEBYSCORE ages the old entries out, ZADD records this one, ZCARD counts what is left, all in one round trip. Doing either of these in Postgres would mean a write on every single request.

## The hard part: Comparing rate-limiting algorithms

### 1. Boundary-burst problem

A fixed-window limiter counts requests within fixed time intervals, such as 10:00:00–10:00:59 and 10:01:00–10:01:59. When the counter resets, a client can send requests immediately before and after the boundary. Therefore, a client may send nearly twice the configured limit within a short period, even though neither individual window exceeds its limit.

For example, with a limit of 5 requests per minute, a client can send 5 requests near the end of one window and another 5 immediately after the next window begins. All 10 requests can be accepted within a few seconds.

The `boundary_burst(limit)` function generates timestamps for this scenario. Passing those timestamps to `fixed_window_check` and `sliding_log_check` demonstrates the difference: the fixed-window algorithm can accept the burst, while the sliding-log algorithm rejects requests that exceed the limit within the trailing 60 seconds.

The `GET /explain/boundary?limit=5` endpoint provides a way to inspect the boundary problem through the running application.

### 2. Fixed window versus sliding log

**Fixed window:** This approach maintains a counter for each API key and time window. It is efficient and requires relatively little memory. Redis can implement it using `INCR` and `EXPIRE`, executed through a pipeline or suitable script. However, the counter reset creates the boundary-burst problem.

**Sliding log:** This approach stores request timestamps and counts only those within the most recent 60 seconds. It provides accurate rolling-window enforcement and avoids the fixed-window boundary burst. Its disadvantages are higher memory usage, because timestamps must be stored, and additional Redis operations to remove expired entries, record requests, and count the remaining entries.

### 3. The sliding-counter compromise

A sliding counter estimates the rolling request count using the current window's counter and the previous window's counter. It weights the previous counter according to how much of that window overlaps the trailing time interval.

The estimate reduces the boundary-burst problem without storing every request timestamp. However, it is an approximation: it assumes requests were distributed evenly within the previous window. If requests were concentrated near one end of that window, the estimate can differ from the exact sliding-log count.

The `sliding_counter_estimate` function should be compared with `sliding_log_check` using different timestamp distributions. This helps demonstrate when the estimate is close to the exact count and when the approximation differs.

### 4. Shipping decision

For a gateway where accurate rolling request limits are important and traffic per API key is moderate, I would initially ship the sliding-log approach. It provides exact rolling-window enforcement and is straightforward to reason about.

I would monitor request volume per key, Redis memory consumption, and request latency. If timestamp storage or processing becomes too expensive at measured production traffic levels, I would benchmark a sliding-counter implementation and consider switching if its approximation meets the product's requirements.

A fixed-window limiter remains appropriate when low overhead is more important than strict rolling-window enforcement. The choice should be based on measured traffic, resource usage, and the required accuracy rather than an arbitrary universal request-rate threshold.
## Getting unstuck

| Symptom | Almost always |
|---|---|
| `/health` says `postgres: false` | Wrong hostname. In compose the host is the **service name**, not `localhost`. |
| Page will not load, logs fine | No `ports:` mapping, or bound to `127.0.0.1` not `0.0.0.0`. |
| `relation "..." does not exist` | Migrations did not run, or the app started before they finished. |
| Build takes minutes each time | `COPY . .` is above your dependency install. |
| CI cannot reach the database | In CircleCI service containers the host **is** `localhost` — opposite of compose. |
