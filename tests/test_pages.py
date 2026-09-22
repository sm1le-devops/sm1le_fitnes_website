from models import Purchase


def test_root_is_public(client):
    response = client.get("/")

    assert response.status_code == 200


def test_welcome_requires_login(client):
    response = client.get(
        "/auth/welcome",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert (
        response.headers["location"]
        == "/auth/login"
    )


def test_plan_page_marks_paid_purchase(
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
        )
    )
    db.commit()

    login_as(user)

    response = client.get(
        f"/plans/{plan_id}"
    )

    assert response.status_code == 200
    assert "Открыть программу" in response.text
