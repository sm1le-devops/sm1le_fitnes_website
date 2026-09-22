# sm1le.fitness — pytest suite

Этот набор тестов не требует реальных:
- PostgreSQL
- Redis
- Stripe
- SMTP

Он использует SQLite in-memory, FakeRedis и monkeypatch.

## Установка

Если pytest ещё не добавлен:

```powershell
poetry add --group dev pytest
```

или:

```powershell
pip install pytest
```

## Запуск

Из корня проекта:

```powershell
pytest -v
```

Быстрая остановка на первой ошибке:

```powershell
pytest -x -v
```

Конкретный файл:

```powershell
pytest tests/test_payments.py -v
```

## Что покрыто

- health
- CSRF / password hashing / username validation
- Pydantic schemas
- DB constraints и cascade delete
- Redis sessions
- register/login/profile/logout
- password reset + one-time token + session invalidation
- Purchase / GeneratedPlan services
- course authorization / user isolation / generation / PDF
- pages
- Stripe checkout
- payment-success polling flow
- webhook verification + idempotency
- AI plan generator
