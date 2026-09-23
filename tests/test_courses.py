from models import GeneratedPlan, Purchase


def add_paid_purchase(db, user_id, plan_id):
    db.add(
        Purchase(
            user_id=user_id,
            plan_id=plan_id,
            status="paid",
        )
    )
    db.commit()


def add_generated_plan(
    db,
    user_id,
    plan_id,
    content="# Generated Plan",
):
    db.add(
        GeneratedPlan(
            user_id=user_id,
            plan_id=plan_id,
            content=content,
        )
    )
    db.commit()


def test_questionnaire_redirects_guest_to_login(
    client,
    plan_id,
):
    response = client.get(
        "/questionnaire",
        params={
            "plan_id": plan_id
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert (
        response.headers["location"]
        == "/auth/login"
    )


def test_questionnaire_requires_purchase(
    client,
    make_user,
    login_as,
    plan_id,
):
    user = make_user()
    login_as(user)

    response = client.get(
        "/questionnaire",
        params={
            "plan_id": plan_id
        },
    )

    assert response.status_code == 403


def test_questionnaire_for_paid_user_sets_csrf(
    client,
    db,
    make_user,
    login_as,
    plan_id,
):
    user = make_user()
    add_paid_purchase(
        db,
        user.id,
        plan_id,
    )
    login_as(user)

    response = client.get(
        "/questionnaire",
        params={
            "plan_id": plan_id
        },
    )

    assert response.status_code == 200
    assert response.cookies.get(
        "csrf_token"
    )


def test_course_guest_sees_paywall(
    client,
    plan_id,
):
    response = client.get(
        f"/course/{plan_id}"
    )

    assert response.status_code == 200
    assert "BUY COURSE" in response.text


def test_paid_course_without_generated_plan_redirects_questionnaire(
    client,
    db,
    make_user,
    login_as,
    plan_id,
):
    user = make_user()
    add_paid_purchase(
        db,
        user.id,
        plan_id,
    )
    login_as(user)

    response = client.get(
        f"/course/{plan_id}",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert (
        response.headers["location"]
        == f"/questionnaire?plan_id={plan_id}"
    )


def test_paid_course_reads_only_users_generated_plan(
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
    other = make_user(
        username="other",
        email="other@example.com",
    )

    add_paid_purchase(
        db,
        owner.id,
        plan_id,
    )
    add_generated_plan(
        db,
        owner.id,
        plan_id,
        "OWNER_SECRET_PLAN",
    )

    add_paid_purchase(
        db,
        other.id,
        plan_id,
    )
    login_as(other)

    response = client.get(
        f"/course/{plan_id}",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "OWNER_SECRET_PLAN" not in response.text


def test_paid_course_returns_generated_content(
    client,
    db,
    make_user,
    login_as,
    plan_id,
):
    user = make_user()

    add_paid_purchase(
        db,
        user.id,
        plan_id,
    )
    add_generated_plan(
        db,
        user.id,
        plan_id,
        "MY_GENERATED_PLAN",
    )
    login_as(user)

    response = client.get(
        f"/course/{plan_id}"
    )

    assert response.status_code == 200
    assert "MY_GENERATED_PLAN" in response.text


def test_generate_plan_requires_paid_purchase(
    client,
    make_user,
    login_as,
    csrf,
    plan_id,
):
    user = make_user()
    login_as(user)
    token = csrf()

    response = client.post(
        f"/generate-plan/{plan_id}",
        data={
            "gender": "male",
            "weight": "80",
            "height": "185",
            "age": "25",
            "experience": "beginner",
            "equipment": "gym",
            "injuries": "none",
            "csrf_token": token,
        },
        follow_redirects=False,
    )

    assert response.status_code == 403


def test_generate_plan_rejects_csrf_mismatch(
    client,
    db,
    make_user,
    login_as,
    csrf,
    plan_id,
):
    user = make_user()
    add_paid_purchase(
        db,
        user.id,
        plan_id,
    )
    login_as(user)

    csrf()
    wrong_valid_token = __import__(
        "core.security",
        fromlist=["generate_csrf_token"],
    ).generate_csrf_token()

    response = client.post(
        f"/generate-plan/{plan_id}",
        data={
            "gender": "male",
            "weight": "80",
            "height": "185",
            "age": "25",
            "experience": "beginner",
            "equipment": "gym",
            "injuries": "none",
            "csrf_token": wrong_valid_token,
        },
        follow_redirects=False,
    )

    assert response.status_code == 403


def test_generate_plan_saves_normalized_record(
    client,
    db,
    monkeypatch,
    make_user,
    login_as,
    csrf,
    plan_id,
):
    user = make_user()
    add_paid_purchase(
        db,
        user.id,
        plan_id,
    )
    login_as(user)
    token = csrf()

    monkeypatch.setattr(
        "routers.courses.generate_training_plan",
        lambda *_args, **_kwargs: "# TEST PLAN",
    )

    response = client.post(
        f"/generate-plan/{plan_id}",
        data={
            "gender": "male",
            "weight": "81.5",
            "height": "189",
            "age": "25",
            "experience": "intermediate",
            "equipment": "gym",
            "injuries": "none",
            "csrf_token": token,
        },
        follow_redirects=False,
    )

    assert response.status_code == 303

    db.expire_all()

    generated = (
        db.query(GeneratedPlan)
        .filter(
            GeneratedPlan.user_id == user.id,
            GeneratedPlan.plan_id == plan_id,
        )
        .one()
    )

    assert generated.content == "# TEST PLAN"


def test_generate_plan_updates_existing_record(
    client,
    db,
    monkeypatch,
    make_user,
    login_as,
    csrf,
    plan_id,
):
    user = make_user()
    add_paid_purchase(
        db,
        user.id,
        plan_id,
    )
    add_generated_plan(
        db,
        user.id,
        plan_id,
        "OLD",
    )

    login_as(user)
    token = csrf()

    monkeypatch.setattr(
        "routers.courses.generate_training_plan",
        lambda *_args, **_kwargs: "NEW",
    )

    response = client.post(
        f"/generate-plan/{plan_id}",
        data={
            "gender": "male",
            "weight": "80",
            "height": "180",
            "age": "25",
            "experience": "advanced",
            "equipment": "gym",
            "injuries": "none",
            "csrf_token": token,
        },
        follow_redirects=False,
    )

    assert response.status_code == 303

    db.expire_all()

    rows = (
        db.query(GeneratedPlan)
        .filter(
            GeneratedPlan.user_id == user.id,
            GeneratedPlan.plan_id == plan_id,
        )
        .all()
    )

    assert len(rows) == 1
    assert rows[0].content == "NEW"


def test_download_requires_purchase(
    client,
    make_user,
    login_as,
    plan_id,
):
    user = make_user()
    login_as(user)

    response = client.get(
        f"/course/{plan_id}/download"
    )

    assert response.status_code == 403


def test_download_requires_generated_plan(
    client,
    db,
    make_user,
    login_as,
    plan_id,
):
    user = make_user()
    add_paid_purchase(
        db,
        user.id,
        plan_id,
    )
    login_as(user)

    response = client.get(
        f"/course/{plan_id}/download"
    )

    assert response.status_code == 404


def test_download_returns_pdf(
    client,
    db,
    monkeypatch,
    make_user,
    login_as,
    plan_id,
):
    user = make_user()
    add_paid_purchase(
        db,
        user.id,
        plan_id,
    )
    add_generated_plan(
        db,
        user.id,
        plan_id,
    )
    login_as(user)

    monkeypatch.setattr(
        "routers.courses.create_pdf_buffer",
        lambda _content: b"%PDF-test",
    )

    response = client.get(
        f"/course/{plan_id}/download"
    )

    assert response.status_code == 200
    assert (
        response.headers["content-type"]
        == "application/pdf"
    )
    assert response.content == b"%PDF-test"
