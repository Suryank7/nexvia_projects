from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Feedback
from app.utils.logger import get_logger

logger = get_logger(__name__)


async def create_feedback(
    db: AsyncSession,
    run_id: UUID,
    user_id: UUID,
    rating: int,
    comment: str | None = None,
) -> Feedback:
    feedback = Feedback(
        run_id=run_id,
        user_id=user_id,
        rating=rating,
        comment=comment,
    )
    db.add(feedback)
    await db.flush()
    logger.info("Created feedback id=%s run_id=%s rating=%s", feedback.id, run_id, rating)
    return feedback


async def list_feedback(
    db: AsyncSession,
    run_id: UUID | None = None,
    offset: int = 0,
    limit: int = 50,
) -> tuple[list[Feedback], int]:
    q = select(Feedback)
    count_q = select(func.count()).select_from(Feedback)
    if run_id is not None:
        q = q.where(Feedback.run_id == run_id)
        count_q = count_q.where(Feedback.run_id == run_id)
    q = q.order_by(Feedback.created_at.desc()).offset(offset).limit(limit)
    rows = list((await db.scalars(q)).all())
    total = await db.scalar(count_q)
    logger.info("Listed %d feedback rows (total=%d)", len(rows), total)
    return rows, total