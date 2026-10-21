"""The exercise library as the website sees it."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# Muscle names used by the library (free-exercise-db).
Muscle = Literal[
    "abdominals",
    "abductors",
    "adductors",
    "biceps",
    "calves",
    "chest",
    "forearms",
    "glutes",
    "hamstrings",
    "lats",
    "lower back",
    "middle back",
    "neck",
    "quadriceps",
    "shoulders",
    "traps",
    "triceps",
]

# ready: saved · preparing: a job is queued or running · missing: not asked for yet
# none_found: the video search found nothing suitable · failed: the job failed
# in the last day (not retried until then; the reason is in *_error)
PartStatus = Literal["ready", "preparing", "missing", "none_found", "failed"]


class ExerciseSummary(BaseModel):
    id: str
    name: str
    category: str | None
    equipment: str | None
    level: str | None
    primary_muscles: list[str]
    # The start-position image, for lists.
    image: str | None


class ExerciseList(BaseModel):
    items: list[ExerciseSummary]
    has_more: bool
    # When a search finds nothing: the 5 closest names, shown as the results.
    suggestions: list[ExerciseSummary] = []


class Video(BaseModel):
    id: str
    title: str | None
    channel: str | None
    duration_seconds: int | None
    views: int | None
    url: str
    thumbnail: str
    # Someone said "Yes, this is the right video": kept, not refreshed monthly.
    confirmed: bool = False


class ExerciseDetail(BaseModel):
    id: str
    name: str
    category: str | None
    level: str | None
    force: str | None
    mechanic: str | None
    equipment: str | None
    primary_muscles: list[str]
    secondary_muscles: list[str]
    instructions: list[str]
    images: list[str]
    about: str | None
    form_cues: list[str] | None
    precautions: list[str] | None
    guide_written_at: datetime | None
    video: Video | None
    guide_status: PartStatus
    video_status: PartStatus
    guide_error: str | None = None
    video_error: str | None = None
    # Videos people said were wrong for this exercise (never chosen again).
    videos_rejected: int = 0


class VideoFeedback(BaseModel):
    """ "Is this the right video?" Yes, or no with a reason (which guides the next search)."""

    video_id: str = Field(pattern=r"^[A-Za-z0-9_-]{6,20}$")
    verdict: Literal["right", "wrong"]
    reason: Annotated[str, Field(min_length=3, max_length=300)] | None = None

    @field_validator("reason", mode="before")
    @classmethod
    def blank_is_none(cls, value: object) -> object:
        return value.strip() or None if isinstance(value, str) else value

    @model_validator(mode="after")
    def wrong_needs_a_reason(self) -> "VideoFeedback":
        if self.verdict == "wrong" and not self.reason:
            raise ValueError("Say why it's the wrong video, so the next search can do better")
        return self
