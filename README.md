# sm1le.fitness

**Production-oriented fitness platform built with FastAPI, PostgreSQL and Redis.**

Users can register, verify email, manage a profile, purchase a plan through Stripe, and receive personalized training content.

**Live:** https://sm1le-fitnes-website-pojo.onrender.com

## Stack

**Python 3.12 · FastAPI · PostgreSQL · SQLAlchemy · Alembic · Redis · Stripe · Resend · Docker · Pytest · GitHub Actions**

## Backend Highlights

- Secure / HttpOnly cookie sessions, bcrypt, CSRF protection and account recovery
- PostgreSQL persistence with SQLAlchemy + Alembic migrations
- Redis-backed sessions, rate limiting and security state
- Stripe Checkout with verified, idempotent webhook processing
- Email verification and password reset via Resend
- Structured JSON logs with `X-Request-ID`
- `/health` liveness and `/ready` PostgreSQL + Redis readiness checks

## Verified Quality

```text
Pytest                  128 passed
Mypy                    0 issues
Ruff                    All checks passed
Dependency audit        0 known vulnerabilities
Alembic drift check     Passed
Docker production build Passed
Production smoke tests  Passed
```

## Performance Testing

Performance tests are implemented with **Grafana k6** and stored in `load_tests/`.

Predefined SLO for the PostgreSQL/Redis-backed readiness path:

```text
P95 latency       < 500 ms
Request failures  < 1%
```

Verified local capacity across three independent 60-second runs:

```text
Concurrent VUs        200
Average throughput    ~547 req/s
Average P95 latency   ~478 ms
Request failures      0.00%
Total requests        98,752
```

At **205 VUs**, P95 increased to **509 ms** while failures remained **0%**, identifying the beginning of saturation for this test path.

A separate stress test reached **2,000 VUs** to observe overload and failure behavior beyond normal capacity.

> These figures describe the tested `/ready` infrastructure path in a local production-mode environment, not total real-user capacity of the entire application.

## CI/CD

```text
Git push
  → Ruff + Mypy
  → Alembic validation
  → Pytest
  → Dependency audit
  → Docker build
  → Render deploy
  → Production migrations
  → /ready verification
  → Exact Git commit verification
  → Smoke tests
```

**Status:** `v1.0` — production portfolio release
