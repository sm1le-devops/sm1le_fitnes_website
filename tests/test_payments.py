from types import SimpleNamespace

from models import Purchase


def checkout_session(id="cs_test_1", **kwargs):
    return SimpleNamespace(id=id)


def set_valid_checkout_csrf(client, csrf):
    token = csrf()

    return {
        "X-CSRF-Token": token
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

    other = __import__(
        "core.security",
        fromlist=["generate_csrf_token"],
    ).generate_csrf_token()

    response = client.post(
        f"/create-checkout-session/{plan_id}",
        headers={
            "X-CSRF-Token": other
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

    def fake_create(**kwargs):
        captured.update(kwargs)
        return checkout_session()

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
        == "rub"
    )
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
        lambda _sid: {
            "payment_status": "paid",
            "metadata": {
                "user_id": str(user.id + 999),
                "plan_id": plan_id,
            },
        },
    )

    response = client.get(
        "/payment-success",
        params={
            "session_id": "cs_test"
        },
    )

    assert response.status_code == 403


def test_payment_success_requires_paid_stripe_session(
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
        lambda _sid: {
            "payment_status": "unpaid",
            "metadata": {
                "user_id": str(user.id),
                "plan_id": plan_id,
            },
        },
    )

    response = client.get(
        "/payment-success",
        params={
            "session_id": "cs_test"
        },
    )

    assert response.status_code == 400


def test_payment_success_page_does_not_write_purchase(
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
        lambda _sid: {
            "payment_status": "paid",
            "metadata": {
                "user_id": str(user.id),
                "plan_id": plan_id,
            },
        },
    )

    response = client.get(
        "/payment-success",
        params={
            "session_id": "cs_test"
        },
    )

    assert response.status_code == 200
    assert (
        db.query(Purchase)
        .filter(
            Purchase.user_id == user.id,
            Purchase.plan_id == plan_id,
        )
        .count()
        == 0
    )


def test_payment_status_processing(
    client,
    make_user,
    login_as,
    plan_id,
):
    user = make_user()
    login_as(user)

    response = client.get(
        "/payment-status",
        params={
            "plan_id": plan_id
        },
    )

    assert response.status_code == 200
    assert (
        response.json()["status"]
        == "processing"
    )


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
            "plan_id": plan_id
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "paid",
        "course_url": f"/course/{plan_id}",
    }


def test_webhook_requires_signature(
    client,
):
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
            "stripe-signature": "bad"
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
            "type": "customer.created",
            "data": {
                "object": {}
            },
        },
    )

    response = client.post(
        "/webhook",
        content=b"{}",
        headers={
            "stripe-signature": "sig"
        },
    )

    assert response.status_code == 200
    assert (
        response.json()["status"]
        == "ignored"
    )


def test_webhook_creates_purchase(
    client,
    db,
    monkeypatch,
    make_user,
    plan_id,
):
    user = make_user()

    event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_webhook_1",
                "payment_status": "paid",
                "amount_total": 2500,
                "currency": "rub",
                "metadata": {
                    "user_id": str(user.id),
                    "plan_id": plan_id,
                },
            }
        },
    }

    monkeypatch.setattr(
        "routers.payments.stripe.Webhook.construct_event",
        lambda *_args, **_kwargs: event,
    )

    response = client.post(
        "/webhook",
        content=b"{}",
        headers={
            "stripe-signature": "sig"
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
    assert (
        purchase.stripe_session_id
        == "cs_webhook_1"
    )
    assert purchase.amount_cents == 2500
    assert purchase.currency == "rub"


def test_webhook_is_idempotent_for_same_session(
    client,
    db,
    monkeypatch,
    make_user,
    plan_id,
):
    user = make_user()

    event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_same",
                "payment_status": "paid",
                "amount_total": 2500,
                "currency": "rub",
                "metadata": {
                    "user_id": str(user.id),
                    "plan_id": plan_id,
                },
            }
        },
    }

    monkeypatch.setattr(
        "routers.payments.stripe.Webhook.construct_event",
        lambda *_args, **_kwargs: event,
    )

    for _ in range(2):
        response = client.post(
            "/webhook",
            content=b"{}",
            headers={
                "stripe-signature": "sig"
            },
        )
        assert response.status_code == 200

    db.expire_all()

    count = (
        db.query(Purchase)
        .filter(
            Purchase.user_id == user.id,
            Purchase.plan_id == plan_id,
        )
        .count()
    )

    assert count == 1


def test_webhook_does_not_grant_access_for_unpaid_session(
    client,
    db,
    monkeypatch,
    make_user,
    plan_id,
):
    user = make_user()

    event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_unpaid",
                "payment_status": "unpaid",
                "metadata": {
                    "user_id": str(user.id),
                    "plan_id": plan_id,
                },
            }
        },
    }

    monkeypatch.setattr(
        "routers.payments.stripe.Webhook.construct_event",
        lambda *_args, **_kwargs: event,
    )

    response = client.post(
        "/webhook",
        content=b"{}",
        headers={
            "stripe-signature": "sig"
        },
    )

    assert response.status_code == 200
    assert (
        db.query(Purchase)
        .count()
        == 0
    )
