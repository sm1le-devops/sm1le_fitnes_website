from secrets import compare_digest
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Request,
)
from fastapi.responses import (
    HTMLResponse,
    RedirectResponse,
    Response,
)
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from core.config import settings
from core.security import (
    generate_csrf_token,
    validate_csrf_token,
)
from database import get_db
from dependencies import (
    get_current_user_optional,
    require_current_user,
)
from models import User
from services.ai_service import generate_training_plan
from services.course_access_service import (
    get_generated_plan,
    has_paid_purchase,
    save_generated_plan,
)
from services.pdf_service import create_pdf_buffer
from services.plan_service import PLANS


router = APIRouter()
templates = Jinja2Templates(directory="templates")


def check_csrf(
    cookie_token: Optional[str],
    form_token: Optional[str],
) -> None:
    if (
        not cookie_token
        or not form_token
        or not compare_digest(
            cookie_token,
            form_token,
        )
        or not validate_csrf_token(form_token)
    ):
        raise HTTPException(
            status_code=403,
            detail="Security error (CSRF)",
        )


@router.get(
    "/questionnaire",
    response_class=HTMLResponse,
)
async def get_questionnaire(
    request: Request,
    plan_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(
        get_current_user_optional
    ),
):
    if current_user is None:
        return RedirectResponse(
            url="/auth/login",
            status_code=303,
        )

    if plan_id not in PLANS:
        raise HTTPException(
            status_code=404,
            detail="Plan not found",
        )

    if not has_paid_purchase(
        db=db,
        user_id=current_user.id,
        plan_id=plan_id,
    ):
        raise HTTPException(
            status_code=403,
            detail="Plan has not been purchased",
        )

    csrf_token = generate_csrf_token()

    response = templates.TemplateResponse(
        request,
        "questionnaire.html",
        {
            "request": request,
            "plan_id": plan_id,
            "csrf_token": csrf_token,
        },
    )

    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=False,
        secure=True,
        samesite="Lax",
        path="/",
    )

    return response


@router.get("/course/{plan_id}/download")
def download_pdf(
    plan_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_current_user
    ),
):
    if not has_paid_purchase(
        db=db,
        user_id=current_user.id,
        plan_id=plan_id,
    ):
        raise HTTPException(
            status_code=403,
            detail="Plan has not been purchased",
        )

    generated_plan = get_generated_plan(
        db=db,
        user_id=current_user.id,
        plan_id=plan_id,
    )

    if not generated_plan:
        raise HTTPException(
            status_code=404,
            detail="Generated plan content not found",
        )

    pdf_bytes = create_pdf_buffer(
        generated_plan.content
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f"attachment; "
                f"filename=plan_{plan_id}.pdf"
            )
        },
    )


@router.get(
    "/course/{plan_id}",
    response_class=HTMLResponse,
)
async def view_course(
    request: Request,
    plan_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(
        get_current_user_optional
    ),
):
    plan = PLANS.get(plan_id)

    if not plan:
        raise HTTPException(
            status_code=404,
            detail="Program not found in the catalog",
        )

    is_purchased = False
    generated_content = None

    if current_user:
        is_purchased = has_paid_purchase(
            db=db,
            user_id=current_user.id,
            plan_id=plan_id,
        )

        if is_purchased:
            generated_plan = get_generated_plan(
                db=db,
                user_id=current_user.id,
                plan_id=plan_id,
            )

            if not generated_plan:
                return RedirectResponse(
                    url=(
                        "/questionnaire"
                        f"?plan_id={plan_id}"
                    ),
                    status_code=303,
                )

            generated_content = (
                generated_plan.content
            )

    return templates.TemplateResponse(
        request,
        "course_view.html",
        {
            "request": request,
            "plan": plan,
            "plan_id": plan_id,
            "is_purchased": is_purchased,
            "plan_json": generated_content,
            "stripe_publishable_key": (
                settings.stripe_publishable_key
            ),
        },
    )


@router.post("/generate-plan/{plan_id}")
def process_questionnaire(
    request: Request,
    plan_id: str,
    gender: str = Form(...),
    weight: float = Form(...),
    height: float = Form(...),
    age: int = Form(...),
    experience: str = Form(...),
    equipment: str = Form(...),
    injuries: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_current_user
    ),
):
    check_csrf(
        request.cookies.get("csrf_token"),
        csrf_token,
    )

    plan_info = PLANS.get(plan_id)

    if not plan_info:
        raise HTTPException(
            status_code=404,
            detail="Plan not found",
        )

    if not has_paid_purchase(
        db=db,
        user_id=current_user.id,
        plan_id=plan_id,
    ):
        raise HTTPException(
            status_code=403,
            detail="Plan has not been purchased",
        )

    ai_user_data = {
        "gender": gender,
        "weight": weight,
        "height": height,
        "age": age,
        "experience": experience,
        "equipment": equipment,
        "injuries": injuries,
    }

    generated_text = generate_training_plan(
        ai_user_data,
        plan_info.get(
            "title",
            "Personalized Plan",
        ),
    )

    if generated_text is None:
        raise HTTPException(
            status_code=503,
            detail="Failed to generate the plan",
        )

    save_generated_plan(
        db=db,
        user_id=current_user.id,
        plan_id=plan_id,
        content=generated_text,
    )

    if current_user.profile:
        current_user.profile.gender = gender
        current_user.profile.age = age
        current_user.profile.weight = weight
        current_user.profile.height = height

    db.commit()

    return RedirectResponse(
        url=f"/course/{plan_id}",
        status_code=303,
    )
