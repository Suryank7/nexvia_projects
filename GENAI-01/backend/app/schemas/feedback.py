from pydantic import BaseModel, Field
from uuid import UUID


class FeedbackCreate(BaseModel):
    run_id: UUID
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=1000)


class FeedbackResponse(BaseModel):
    id: UUID
    run_id: UUID
    user_id: UUID
    rating: int
    comment: str | None
    created_at: str

    model_config = {"from_attributes": True}


class FeedbackListResponse(BaseModel):
    feedback: list[FeedbackResponse]
    total: int
