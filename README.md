# sm1le.fitness

**Production-hardened FastAPI platform for purchasing personalized fitness courses.**

Users can register, complete their profile, choose a fitness goal, purchase a course through Stripe, and receive access to personalized training content. The backend is built around secure authentication, payment reliability, user-data isolation, Redis-backed state, observability, automated testing, and verified CI/CD.

**Live:** https://sm1le-fitnes-website-pojo.onrender.com

## Stack

**Python 3.12 · FastAPI · PostgreSQL · SQLAlchemy · Alembic · Redis · Docker · Stripe · GitHub Actions**

## Verified Quality

```text
Pytest                  128 passed
Mypy                    0 issues / 20 source files
Ruff                    All checks passed
Dependency audit        0 known vulnerabilities
Alembic drift check     Passed
Docker production build Passed
Production smoke tests  Passed
```

## Key Engineering Features

### Security
- bcrypt password hashing
- Secure / HttpOnly cookie-based sessions
- CSRF protection
- email verification and password reset
- RBAC and user-data isolation
- brute-force / abuse rate limiting
- CSP, HSTS, TrustedHost and restricted CORS

### Payments
- Stripe Checkout
- verified webhook processing
- webhook idempotency to prevent duplicate processing
- PostgreSQL-backed purchase state

### Reliability & Observability
- Redis-backed sessions and security state
- structured JSON request logging
- unique `X-Request-ID` for production tracing
- `/health` liveness endpoint
- `/ready` readiness endpoint with real PostgreSQL + Redis checks
- automatic Alembic migrations before application startup

## Architecture

```text
Client
  ↓
FastAPI
  ├── Security middleware
  ├── Request ID / structured logs
  │
  ├── PostgreSQL
  │    └── SQLAlchemy + Alembic
  │
  ├── Redis
  │    └── sessions / rate limits / verification state
  │
  └── Stripe
       └── Checkout + idempotent webhooks
```

## CI/CD

```text
Git push
   ↓
Ruff + Mypy
   ↓
Alembic validation
   ↓
Pytest
   ↓
Dependency audit
   ↓
Docker build
   ↓
Render deploy
   ↓
Production migrations
   ↓
/ready: PostgreSQL + Redis
   ↓
Exact Git commit verification
   ↓
Smoke tests
   ↓
Deployment verified
```

The deployment is considered successful only when the **exact Git commit** sent by GitHub Actions is running in production and these endpoints return successfully:

```text
/health
/ready
/
/auth/login
/auth/register
```

## What This Project Demonstrates

**Secure authentication, PostgreSQL design, Redis-backed state, Stripe payment consistency, webhook idempotency, production migrations, structured logging, request tracing, automated testing, Docker, and end-to-end CI/CD with real production verification.**

**Status:** `v1.0` — production-ready portfolio release
