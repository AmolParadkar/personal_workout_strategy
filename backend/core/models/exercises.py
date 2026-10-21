"""The exercise library as the website sees it."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

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


class Video(BaseModel):
    id: str
    title: str | None
    channel: str | None
    duration_seconds: int | None
    views: int | None
    url: str
    thumbnail: str


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
