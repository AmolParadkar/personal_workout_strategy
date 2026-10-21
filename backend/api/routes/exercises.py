from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from api.deps import CurrentUserDep, SupabaseDep
from core import exercises as service
from core.models.exercises import ExerciseDetail, ExerciseList, Muscle, VideoFeedback
from core.profiles import own_profile_id

router = APIRouter(prefix="/api", tags=["exercises"])


@router.get("/exercises")
async def list_exercises(
    user: CurrentUserDep,
    supabase: SupabaseDep,
    search: Annotated[str | None, Query(max_length=60)] = None,
    muscle: Muscle | None = None,
    equipment: Annotated[str | None, Query(max_length=40)] = None,
    offset: Annotated[int, Query(ge=0, le=2000)] = 0,
) -> ExerciseList:
    """The exercise library, 30 at a time, by name; filter by primary muscle or equipment."""
    return await service.list_exercises(
        supabase, user.access_token, search, muscle, equipment, offset
    )


@router.get("/exercises/{exercise_id}")
async def exercise(exercise_id: str, user: CurrentUserDep, supabase: SupabaseDep) -> ExerciseDetail:
    try:
        return await service.get_exercise(supabase, user.access_token, exercise_id)
    except service.ExerciseNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Exercise not found") from error


@router.post("/exercises/{exercise_id}/prepare")
async def prepare(exercise_id: str, user: CurrentUserDep, supabase: SupabaseDep) -> ExerciseDetail:
    """Ask the Mac worker to write the guide and find a video, if still missing
    (or the video is over a month old). Safe to call repeatedly."""
    profile_id = await own_profile_id(supabase, user.access_token, user.id)
    try:
        return await service.prepare(supabase, user.access_token, profile_id, exercise_id)
    except service.ExerciseNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Exercise not found") from error


@router.post("/exercises/{exercise_id}/video-feedback")
async def video_feedback(
    exercise_id: str, body: VideoFeedback, user: CurrentUserDep, supabase: SupabaseDep
) -> ExerciseDetail:
    """ "Is this the right video?" Yes keeps it (no monthly refresh); no, with a
    reason, searches again straight away, avoiding rejected videos."""
    profile_id = await own_profile_id(supabase, user.access_token, user.id)
    try:
        return await service.give_video_feedback(
            supabase, user.access_token, profile_id, exercise_id, body
        )
    except service.ExerciseNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Exercise not found") from error
    except service.VideoChangedError as error:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "The video has changed since you opened the page. Reload it."
        ) from error
