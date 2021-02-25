import datetime


from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import RedirectResponse, Response
from loguru import logger
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.status import HTTP_302_FOUND, HTTP_400_BAD_REQUEST

from app.dependencies import get_db, templates
from app.database.models import UserMenstrualPeriodLength
from app.internal.menstrual_predictor_utils import (
    add_prediction_events_if_valid,
    is_user_signed_up_to_menstrual_predictor,
    generate_predicted_period_dates,
)
from app.internal.security.schema import CurrentUser
from app.internal.security.dependancies import current_user
from app.internal.utils import create_model


router = APIRouter(
    prefix="/menstrual_predictor",
    tags=["menstrual_predictor"],
    dependencies=[Depends(get_db)],
)

MENSTRUAL_PERIOD_CATEGORY_ID = 111


@router.get("/")
def join_menstrual_predictor(
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(current_user),
) -> Response:
    current_user_id = user.user_id

    if not is_user_signed_up_to_menstrual_predictor(db, current_user_id):
        return templates.TemplateResponse(
            "join_menstrual_predictor.html",
            {
                "request": request,
            },
        )
    return RedirectResponse(url="/", status_code=HTTP_302_FOUND)


@router.get("/add-period-start/{start_date}")
def add_period_start(
    request: Request,
    start_date: str,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(current_user),
) -> RedirectResponse:
    try:
        period_start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d")
    except ValueError as err:
        logger.exception(err)
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="The given date doesn't match a date format YYYY-MM-DD",
        )
    else:
        add_prediction_events_if_valid(period_start_date, db, user)
    logger.info("Adding menstrual start date")
    return RedirectResponse("/", status_code=HTTP_302_FOUND)


@router.post("/")
async def submit_join_form(
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(current_user),
) -> RedirectResponse:

    data = await request.form()

    user_menstrual_period_length = {
        "user_id": user.user_id,
        "period_length": data["avg-period-length"],
    }
    last_period_date = datetime.datetime.strptime(
        data["last-period-date"],
        "%Y-%m-%d",
    )
    try:
        create_model(
            session=db,
            model_class=UserMenstrualPeriodLength,
            **user_menstrual_period_length,
        )
    except SQLAlchemyError:
        logger.info("Current user already signed up to the service, hurray")
        db.rollback()
    url = "/"
    generate_predicted_period_dates(
        db,
        data["avg-period-length"],
        last_period_date,
        user.user_id,
    )

    return RedirectResponse(url=url, status_code=HTTP_302_FOUND)
