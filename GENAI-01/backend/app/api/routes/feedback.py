from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.db.models import Feedback, User
from app.schemas.feedback import (
    FeedbackCreate,
    FeedbackListResponse,
    FeedbackResponse,
)
from app.services.feedback_service import create_feedback, list_feedback
from app.utils.logger import get_logger

router = APIRouter(prefix="/feedback", tags=["feedback"])
logger = get_logger(__name__)


@router.post("", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
async def submit_feedback(
    body: FeedbackCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    feedback = await create_feedback(
        db=db,
        run_id=body.run_id,
        user_id=current_user.id,
        rating=body.rating,
        comment=body.comment,
    )
    return FeedbackResponse(
        id=feedback.id,
        run_id=feedback.run_id,
        user_id=feedback.user_id,
        rating=feedback.rating,
        comment=feedback.comment,
        created_at=feedback.created_at.isoformat(),
    )


@router.get("", response_model=FeedbackListResponse)
async def list_feedback_route(
    run_id: UUID | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows, total = await list_feedback(db, run_id=run_id, offset=offset, limit=limit)
    return FeedbackListResponse(
        feedback=[
            FeedbackResponse(
                id=r.id,
                run_id=r.run_id,
                user_id=r.user_id,
                rating=r.rating,
                comment=r.comment,
                created_at=r.created_at.isoformat(),
            )
            for r in rows
        ],
        total=total,
    )


@router.get("/{feedback_id}", response_model=FeedbackResponse)
async def get_feedback(
    feedback_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from sqlalchemy import select

    row = await db.get(Feedback, feedback_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feedback not found")
    return FeedbackResponse(
        id=row.id,
        run_id=row.run_id,
        user_id=row.user_id,
        rating=row.rating,
        comment=row.comment,
        created_at=row.created_at.isoformat(),
    )