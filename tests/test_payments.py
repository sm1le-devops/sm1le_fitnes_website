from core.security import generate_csrf_token
from models import Purchase, StripeWebhookEvent


def set_valid_checkout_csrf(
    client,
    csrf,
):
    token = csrf()

    return {
        "X-CSRF-Token": token,
    }


def make_checkout_session(
    *,
    session_id="cs_test_1",
    user_id=1,
    plan_id="weight_loss",
    payment_status="paid",
    amount_total=2500,
    currency="rub",
):
    return {
        "id": session_id,
        "payment_status": payment_status,
        "amount_total": amount_total,
        "currency": currency,
        "metadata": {
            "user_id": str(user_id),
            "plan_id": plan_id,
        },
    }


def make_checkout_event(
    *,
    event_id="evt_test_1",
    event_type="checkout.session.completed",
    session_id="cs_test_1",
    user_id=1,
    plan_id="weight_loss",
    payment_status="paid",
    amount_total=2500,
    currency="rub",
):
    return {
        "id": event_id,
        "type": event_type,
        "data": {
            "object": make_checkout_session(
                session_id=session_id,
                user_id=user_id,
                plan_id=plan_id,
                payment_status=payment_status,
                amount_total=amount_total,
                currency=currency,
            )
        },
    }


def test_checkout_requires_login(
    client,
    csrf,
    plan_id,
):
    headers = set_valid_checkout_csrf(
        client,
        csrf,
    )

    response = client.post(
        f"/create-checkout-session/{plan_id}",
        headers=headers,
    )

    assert response.status_code == 401


def test_checkout_requires_csrf(
    client,
    make_user,
    login_as,
    plan_id,
):
    user = make_user()
    login_as(user)

    response = client.post(
        f"/create-checkout-session/{plan_id}"
    )

    assert response.status_code == 403


def test_checkout_rejects_csrf_mismatch(
    client,
    make_user,
    login_as,
    csrf,
    plan_id,
):
    user = make_user()
    login_as(user)

    csrf()

    other = generate_csrf_token()

    response = client.post(
        f"/create-checkout-session/{plan_id}",
        headers={
            "X-CSRF-Token": other,
        },
    )

    assert response.status_code == 403


def test_checkout_rejects_unknown_plan(
    client,
    make_user,
    login_as,
    csrf,
):
    user = make_user()
    login_as(user)

    headers = set_valid_checkout_csrf(
        client,
        csrf,
    )

    response = client.post(
        "/create-checkout-session/no-such-plan",
        headers=headers,
    )

    assert response.status_code == 404


def test_checkout_rejects_already_paid_plan(
    client,
    db,
    make_user,
    login_as,
    csrf,
    plan_id,
):
    user = make_user()

    db.add(
        Purchase(
            user_id=user.id,
            plan_id=plan_id,
            status="paid",
        )
    )
    db.commit()

    login_as(user)

    headers = set_valid_checkout_csrf(
        client,
        csrf,
    )

    response = client.post(
        f"/create-checkout-session/{plan_id}",
        headers=headers,
    )

    assert response.status_code == 409


def test_checkout_sends_correct_stripe_metadata(
    client,
    monkeypatch,
    make_user,
    login_as,
    csrf,
    plan_id,
):
    user = make_user()
    login_as(user)

    captured = {}

    class Checkout:
        id = "cs_test_1"

    def fake_create(**kwargs):
        captured.update(kwargs)
        return Checkout()

    monkeypatch.setattr(
        "routers.payments.stripe.checkout.Session.create",
        fake_create,
    )

    headers = set_valid_checkout_csrf(
        client,
        csrf,
    )

    response = client.post(
        f"/create-checkout-session/{plan_id}",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["id"] == "cs_test_1"

    assert (
        captured["client_reference_id"]
        == str(user.id)
    )
    assert (
        captured["metadata"]["user_id"]
        == str(user.id)
    )
    assert (
        captured["metadata"]["plan_id"]
        == plan_id
    )
    assert (
        captured["line_items"][0]
        ["price_data"]["currency"]
        == "usd"
    )
    assert "plan_id=" not in captured["success_url"]
    assert (
        "{CHECKOUT_SESSION_ID}"
        in captured["success_url"]
    )


def test_checkout_hides_stripe_exception(
    client,
    monkeypatch,
    make_user,
    login_as,
    csrf,
    plan_id,
):
    user = make_user()
    login_as(user)

    def explode(**_kwargs):
        raise RuntimeError(
            "secret stripe internals"
        )

    monkeypatch.setattr(
        "routers.payments.stripe.checkout.Session.create",
        explode,
    )

    headers = set_valid_checkout_csrf(
        client,
        csrf,
    )

    response = client.post(
        f"/create-checkout-session/{plan_id}",
        headers=headers,
    )

    assert response.status_code == 502
    assert (
        "secret stripe internals"
        not in response.text
    )


def test_payment_success_reconciliation_creates_purchase(
    client,
    db,
    monkeypatch,
    make_user,
    login_as,
    plan_id,
):
    user = make_user()
    login_as(user)

    monkeypatch.setattr(
        "routers.payments.stripe.checkout.Session.retrieve",
        lambda _sid: make_checkout_session(
            session_id="cs_reconcile",
            user_id=user.id,
            plan_id=plan_id,
            payment_status="paid",
        ),
    )

    response = client.get(
        "/payment-success",
        params={
            "session_id": "cs_reconcile",
        },
    )

    assert response.status_code == 200

    db.expire_all()

    purchase = (
        db.query(Purchase)
        .filter(
            Purchase.user_id == user.id,
            Purchase.plan_id == plan_id,
        )
        .one()
    )

    assert purchase.status == "paid"
    assert purchase.stripe_session_id == "cs_reconcile"


def test_payment_success_does_not_grant_unpaid_session(
    client,
    db,
    monkeypatch,
    make_user,
    login_as,
    plan_id,
):
    user = make_user()
    login_as(user)

    monkeypatch.setattr(
        "routers.payments.stripe.checkout.Session.retrieve",
        lambda _sid: make_checkout_session(
            session_id="cs_unpaid",
            user_id=user.id,
            plan_id=plan_id,
            payment_status="unpaid",
        ),
    )

    response = client.get(
        "/payment-success",
        params={
            "session_id": "cs_unpaid",
        },
    )

    assert response.status_code == 200
    assert db.query(Purchase).count() == 0


def test_payment_success_rejects_other_user(
    client,
    monkeypatch,
    make_user,
    login_as,
    plan_id,
):
    user = make_user()
    login_as(user)

    monkeypatch.setattr(
        "routers.payments.stripe.checkout.Session.retrieve",
        lambda _sid: make_checkout_session(
            session_id="cs_foreign",
            user_id=user.id + 999,
            plan_id=plan_id,
        ),
    )

    response = client.get(
        "/payment-success",
        params={
            "session_id": "cs_foreign",
        },
    )

    assert response.status_code == 403


def test_payment_status_processing(
    client,
    make_user,
    login_as,
):
    user = make_user()
    login_as(user)

    response = client.get(
        "/payment-status",
        params={
            "session_id": "cs_missing",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "processing",
    }


def test_payment_status_paid(
    client,
    db,
    make_user,
    login_as,
    plan_id,
):
    user = make_user()

    db.add(
        Purchase(
            user_id=user.id,
            plan_id=plan_id,
            status="paid",
            stripe_session_id="cs_paid",
        )
    )
    db.commit()

    login_as(user)

    response = client.get(
        "/payment-status",
        params={
            "session_id": "cs_paid",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "paid",
        "course_url": f"/course/{plan_id}",
    }


def test_payment_status_does_not_leak_other_users_purchase(
    client,
    db,
    make_user,
    login_as,
    plan_id,
):
    owner = make_user(
        username="owner",
        email="owner@example.com",
    )
    attacker = make_user(
        username="attacker",
        email="attacker@example.com",
    )

    db.add(
        Purchase(
            user_id=owner.id,
            plan_id=plan_id,
            status="paid",
            stripe_session_id="cs_owner",
        )
    )
    db.commit()

    login_as(attacker)

    response = client.get(
        "/payment-status",
        params={
            "session_id": "cs_owner",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "processing",
    }


def test_webhook_requires_signature(client):
    response = client.post(
        "/webhook",
        content=b"{}",
    )

    assert response.status_code == 400


def test_webhook_rejects_invalid_signature(
    client,
    monkeypatch,
):
    def invalid_event(*_args, **_kwargs):
        raise ValueError("bad signature")

    monkeypatch.setattr(
        "routers.payments.stripe.Webhook.construct_event",
        invalid_event,
    )

    response = client.post(
        "/webhook",
        content=b"{}",
        headers={
            "stripe-signature": "bad",
        },
    )

    assert response.status_code == 400


def test_webhook_ignores_unrelated_event(
    client,
    monkeypatch,
):
    monkeypatch.setattr(
        "routers.payments.stripe.Webhook.construct_event",
        lambda *_args, **_kwargs: {
            "id": "evt_other",
            "type": "customer.created",
            "data": {
                "object": {},
            },
        },
    )

    response = client.post(
        "/webhook",
        content=b"{}",
        headers={
            "stripe-signature": "sig",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


def test_webhook_does_not_grant_access_when_payment_not_paid(
    client,
    db,
    monkeypatch,
    make_user,
    plan_id,
):
    user = make_user()

    event = make_checkout_event(
        event_id="evt_unpaid",
        session_id="cs_unpaid",
        user_id=user.id,
        plan_id=plan_id,
        payment_status="unpaid",
    )

    monkeypatch.setattr(
        "routers.payments.stripe.Webhook.construct_event",
        lambda *_args, **_kwargs: event,
    )

    response = client.post(
        "/webhook",
        content=b"{}",
        headers={
            "stripe-signature": "sig",
        },
    )

    assert response.status_code == 200
    assert (
        response.json()["reason"]
        == "payment_not_paid"
    )
    assert db.query(Purchase).count() == 0
    assert db.query(StripeWebhookEvent).count() == 0


def test_webhook_creates_purchase_and_event_record(
    client,
    db,
    monkeypatch,
    make_user,
    plan_id,
):
    user = make_user()

    event = make_checkout_event(
        event_id="evt_paid",
        session_id="cs_paid",
        user_id=user.id,
        plan_id=plan_id,
    )

    monkeypatch.setattr(
        "routers.payments.stripe.Webhook.construct_event",
        lambda *_args, **_kwargs: event,
    )

    response = client.post(
        "/webhook",
        content=b"{}",
        headers={
            "stripe-signature": "sig",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "success"

    db.expire_all()

    purchase = (
        db.query(Purchase)
        .filter(
            Purchase.user_id == user.id,
            Purchase.plan_id == plan_id,
        )
        .one()
    )

    assert purchase.status == "paid"
    assert purchase.stripe_session_id == "cs_paid"

    stored_event = (
        db.query(StripeWebhookEvent)
        .filter(
            StripeWebhookEvent.event_id == "evt_paid"
        )
        .one()
    )

    assert stored_event.stripe_session_id == "cs_paid"


def test_webhook_same_event_id_is_idempotent(
    client,
    db,
    monkeypatch,
    make_user,
    plan_id,
):
    user = make_user()

    event = make_checkout_event(
        event_id="evt_same",
        session_id="cs_same",
        user_id=user.id,
        plan_id=plan_id,
    )

    monkeypatch.setattr(
        "routers.payments.stripe.Webhook.construct_event",
        lambda *_args, **_kwargs: event,
    )

    first = client.post(
        "/webhook",
        content=b"{}",
        headers={
            "stripe-signature": "sig",
        },
    )
    second = client.post(
        "/webhook",
        content=b"{}",
        headers={
            "stripe-signature": "sig",
        },
    )

    assert first.status_code == 200
    assert first.json()["status"] == "success"

    assert second.status_code == 200
    assert (
        second.json()["status"]
        == "already_processed"
    )

    db.expire_all()

    assert db.query(Purchase).count() == 1
    assert (
        db.query(StripeWebhookEvent)
        .filter(
            StripeWebhookEvent.event_id == "evt_same"
        )
        .count()
        == 1
    )


def test_two_event_ids_for_same_session_do_not_duplicate_purchase(
    client,
    db,
    monkeypatch,
    make_user,
    plan_id,
):
    user = make_user()

    events = [
        make_checkout_event(
            event_id="evt_completed",
            event_type="checkout.session.completed",
            session_id="cs_same_session",
            user_id=user.id,
            plan_id=plan_id,
        ),
        make_checkout_event(
            event_id="evt_async",
            event_type="checkout.session.async_payment_succeeded",
            session_id="cs_same_session",
            user_id=user.id,
            plan_id=plan_id,
        ),
    ]

    def next_event(*_args, **_kwargs):
        return events.pop(0)

    monkeypatch.setattr(
        "routers.payments.stripe.Webhook.construct_event",
        next_event,
    )

    first = client.post(
        "/webhook",
        content=b"{}",
        headers={
            "stripe-signature": "sig",
        },
    )
    second = client.post(
        "/webhook",
        content=b"{}",
        headers={
            "stripe-signature": "sig",
        },
    )

    assert first.status_code == 200
    assert second.status_code == 200

    db.expire_all()

    assert db.query(Purchase).count() == 1
    assert db.query(StripeWebhookEvent).count() == 2


def test_webhook_after_success_reconciliation_is_safe(
    client,
    db,
    monkeypatch,
    make_user,
    login_as,
    plan_id,
):
    user = make_user()
    login_as(user)

    session = make_checkout_session(
        session_id="cs_reconciled",
        user_id=user.id,
        plan_id=plan_id,
    )

    monkeypatch.setattr(
        "routers.payments.stripe.checkout.Session.retrieve",
        lambda _sid: session,
    )

    success = client.get(
        "/payment-success",
        params={
            "session_id": "cs_reconciled",
        },
    )

    assert success.status_code == 200

    event = make_checkout_event(
        event_id="evt_after_reconcile",
        session_id="cs_reconciled",
        user_id=user.id,
        plan_id=plan_id,
    )

    monkeypatch.setattr(
        "routers.payments.stripe.Webhook.construct_event",
        lambda *_args, **_kwargs: event,
    )

    webhook = client.post(
        "/webhook",
        content=b"{}",
        headers={
            "stripe-signature": "sig",
        },
    )

    assert webhook.status_code == 200

    db.expire_all()

    assert db.query(Purchase).count() == 1
    assert db.query(StripeWebhookEvent).count() == 1
