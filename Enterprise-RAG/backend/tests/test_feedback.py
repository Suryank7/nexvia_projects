"""Unit tests for feedback schemas (no external services required)."""

import uuid
from app.schemas.feedback import FeedbackCreate, FeedbackResponse


def test_feedback_create_valid():
    fb = FeedbackCreate(
        run_id=uuid.uuid4(),
        rating=5,
        comment="Great answer",
    )
    assert 1 <= fb.rating <= 5
    assert fb.comment == "Great answer"


def test_feedback_create_rating_out_of_range():
    import pydantic

    try:
        FeedbackCreate(run_id=uuid.uuid4(), rating=0)
        assert False, "Expected validation error"
    except pydantic.ValidationError:
        pass

    try:
        FeedbackCreate(run_id=uuid.uuid4(), rating=6)
        assert False, "Expected validation error"
    except pydantic.ValidationError:
        pass


def test_feedback_create_comment_too_long():
    import pydantic

    try:
        FeedbackCreate(run_id=uuid.uuid4(), rating=3, comment="x" * 1001)
        assert False, "Expected validation error"
    except pydantic.ValidationError:
        pass


def test_feedback_create_no_comment():
    fb = FeedbackCreate(run_id=uuid.uuid4(), rating=3)
    assert fb.comment is None


def test_feedback_response_from_attributes():
    fb = FeedbackResponse(
        id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        rating=4,
        comment=None,
        created_at="2026-01-01T00:00:00",
    )
    assert fb.rating == 4
