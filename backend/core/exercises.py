"""The exercise library: browsing, one exercise in detail, and asking the worker
to prepare its guide and video (context/pages/exercise-guide.md)."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from core.jobs import queue
from core.models.exercises import (
    ExerciseDetail,
    ExerciseList,
    ExerciseSummary,
    PartStatus,
    Video,
    VideoFeedback,
)
from core.supabase import SupabaseClient

PAGE_SIZE = 30
VIDEO_REFRESH = timedelta(days=30)
FAILED_WAIT = timedelta(days=1)
GUIDE_JOB = "write_exercise_guide"
VIDEO_JOB = "find_exercise_video"


SUMMARY_COLUMNS = "id,name,category,equipment,level,primary_muscles,images"
MAX_SEARCH_WORDS = 6
SUGGESTIONS = 5


class ExerciseNotFoundError(Exception):
    pass


class VideoChangedError(Exception):
    """Feedback for a video that's no longer the exercise's video (someone else changed it)."""


def _search_term(text: str) -> str:
    # Supabase filter syntax uses commas, brackets and * : keep letters, digits, spaces, '-'.
    return "".join(ch for ch in text if ch.isalnum() or ch in " -").strip()


def _summary(row: dict[str, Any]) -> ExerciseSummary:
    return ExerciseSummary(
        **{
            k: row.get(k)
            for k in ExerciseSummary.model_fields
            if k not in ("image", "primary_muscles")
        },
        primary_muscles=row.get("primary_muscles") or [],
        image=(row.get("images") or [None])[0],
    )


async def list_exercises(
    supabase: SupabaseClient,
    token: str,
    search: str | None,
    muscle: str | None,
    equipment: str | None,
    offset: int,
) -> ExerciseList:
    params = {
        "select": SUMMARY_COLUMNS,
        "order": "name",
        "limit": str(PAGE_SIZE + 1),
        "offset": str(offset),
    }
    # Every word must appear, in any order: "squat barbell" finds "Barbell Squat".
    words = _search_term(search or "").split()[:MAX_SEARCH_WORDS]
    if words:
        params["and"] = "(" + ",".join(f"name.ilike.*{word}*" for word in words) + ")"
    if muscle:
        params["primary_muscles"] = f'cs.{{"{muscle}"}}'
    if equipment:
        params["equipment"] = f"eq.{equipment}"
    rows = await supabase.select("exercises", params, token)
    result = ExerciseList(
        items=[_summary(r) for r in rows[:PAGE_SIZE]], has_more=len(rows) > PAGE_SIZE
    )
    if words and not rows and offset == 0:
        # Nothing matched exactly: show the closest names instead of an empty page.
        close = await supabase.rpc(
            "suggest_exercises",
            {
                "p_query": " ".join(words),
                "p_muscle": muscle,
                "p_equipment": equipment,
                "p_limit": SUGGESTIONS,
            },
            token,
        )
        result.suggestions = [_summary(r) for r in close]
    return result


@dataclass
class JobState:
    # Job types waiting or running for this exercise.
    queued: set[str] = field(default_factory=set)
    # Job types that failed in the last day, with the reason (not retried until then).
    failed: dict[str, str] = field(default_factory=dict)


async def _job_state(supabase: SupabaseClient, token: str, exercise_id: str) -> JobState:
    rows = await supabase.select(
        "jobs",
        {
            "select": "type,status,last_error,finished_at",
            "type": f"in.({GUIDE_JOB},{VIDEO_JOB})",
            "status": "in.(pending,processing,failed)",
            "payload->>exercise_id": f"eq.{exercise_id}",
            "order": "created_at.desc",
            "limit": "10",
        },
        token,
    )
    state = JobState()
    since = datetime.now(UTC) - FAILED_WAIT
    for row in rows:
        if row["status"] in ("pending", "processing"):
            state.queued.add(row["type"])
        elif (
            row["type"] not in state.failed
            and row.get("finished_at")
            and datetime.fromisoformat(row["finished_at"]) > since
        ):
            state.failed[row["type"]] = row.get("last_error") or "Unknown error"
    return state


def guide_missing(row: dict[str, Any]) -> bool:
    return not row.get("guide_written_at")


def video_due(row: dict[str, Any], now: datetime, confirmed: bool = False) -> bool:
    """Search (again) if never searched or over a month ago, unless someone confirmed the video."""
    if confirmed and row.get("video_id"):
        return False
    checked = row.get("video_checked_at")
    return not checked or now - datetime.fromisoformat(checked) > VIDEO_REFRESH


def is_confirmed(row: dict[str, Any], feedback: list[dict[str, Any]]) -> bool:
    """The latest verdict on the current video is "right" (feedback is newest first)."""
    for item in feedback:
        if item["video_id"] == row.get("video_id"):
            return item["verdict"] == "right"
    return False


async def _feedback(supabase: SupabaseClient, token: str, exercise_id: str) -> list[dict[str, Any]]:
    return await supabase.select(
        "video_feedback",
        {
            "select": "video_id,verdict",
            "exercise_id": f"eq.{exercise_id}",
            "order": "created_at.desc",
            "limit": "50",
        },
        token,
    )


def _status(ready: bool, queued: bool, failed: bool, none_found: bool = False) -> PartStatus:
    if queued:
        return "preparing"
    if ready:
        return "ready"
    if none_found:
        return "none_found"
    return "failed" if failed else "missing"


def to_detail(
    row: dict[str, Any], jobs: JobState, feedback: list[dict[str, Any]] | None = None
) -> ExerciseDetail:
    feedback = feedback or []
    video = None
    if row.get("video_id"):
        video = Video(
            id=row["video_id"],
            title=row.get("video_title"),
            channel=row.get("video_channel"),
            duration_seconds=row.get("video_duration_seconds"),
            views=row.get("video_views"),
            url=f"https://www.youtube.com/watch?v={row['video_id']}",
            thumbnail=f"https://i.ytimg.com/vi/{row['video_id']}/hqdefault.jpg",
            confirmed=is_confirmed(row, feedback),
        )
    return ExerciseDetail(
        **{
            k: row.get(k)
            for k in ExerciseDetail.model_fields
            if k
            not in (
                "video",
                "guide_status",
                "video_status",
                "guide_error",
                "video_error",
                "videos_rejected",
            )
        },
        video=video,
        guide_status=_status(
            not guide_missing(row), GUIDE_JOB in jobs.queued, GUIDE_JOB in jobs.failed
        ),
        video_status=_status(
            video is not None,
            VIDEO_JOB in jobs.queued,
            VIDEO_JOB in jobs.failed,
            none_found=bool(row.get("video_checked_at")) and video is None,
        ),
        guide_error=jobs.failed.get(GUIDE_JOB),
        video_error=jobs.failed.get(VIDEO_JOB),
        videos_rejected=len({f["video_id"] for f in feedback if f["verdict"] == "wrong"}),
    )


async def _row(supabase: SupabaseClient, token: str, exercise_id: str) -> dict[str, Any]:
    rows = await supabase.select("exercises", {"select": "*", "id": f"eq.{exercise_id}"}, token)
    if not rows:
        raise ExerciseNotFoundError
    return rows[0]


async def get_exercise(supabase: SupabaseClient, token: str, exercise_id: str) -> ExerciseDetail:
    row = await _row(supabase, token, exercise_id)
    jobs = await _job_state(supabase, token, exercise_id)
    return to_detail(row, jobs, await _feedback(supabase, token, exercise_id))


async def prepare(
    supabase: SupabaseClient, token: str, profile_id: str, exercise_id: str
) -> ExerciseDetail:
    """Queue the guide and video jobs this exercise still needs (once each; not
    again within a day of one failing, so a broken setup doesn't queue on every visit)."""
    row = await _row(supabase, token, exercise_id)
    jobs = await _job_state(supabase, token, exercise_id)
    feedback = await _feedback(supabase, token, exercise_id)
    payload = {"exercise_id": exercise_id}
    for job_type, needed in (
        (GUIDE_JOB, guide_missing(row)),
        (VIDEO_JOB, video_due(row, datetime.now(UTC), is_confirmed(row, feedback))),
    ):
        if needed and job_type not in jobs.queued and job_type not in jobs.failed:
            await queue.enqueue(supabase, token, profile_id, job_type, payload)
            jobs.queued.add(job_type)
    return to_detail(row, jobs, feedback)


async def give_video_feedback(
    supabase: SupabaseClient, token: str, profile_id: str, exercise_id: str, body: VideoFeedback
) -> ExerciseDetail:
    """Save "right" or "wrong + reason" for the exercise's current video. "Wrong"
    searches again straight away (even if a search failed recently): the job
    avoids rejected videos and uses the reasons."""
    row = await _row(supabase, token, exercise_id)
    if row.get("video_id") != body.video_id:
        raise VideoChangedError
    await supabase.insert(
        "video_feedback",
        {
            "exercise_id": exercise_id,
            "profile_id": profile_id,
            "video_id": body.video_id,
            "video_title": (row.get("video_title") or "")[:200] or None,
            "verdict": body.verdict,
            "reason": body.reason,
        },
        token,
        returning="id",
    )
    jobs = await _job_state(supabase, token, exercise_id)
    if body.verdict == "wrong" and VIDEO_JOB not in jobs.queued:
        await queue.enqueue(supabase, token, profile_id, VIDEO_JOB, {"exercise_id": exercise_id})
        jobs.queued.add(VIDEO_JOB)
        jobs.failed.pop(VIDEO_JOB, None)
    return to_detail(row, jobs, await _feedback(supabase, token, exercise_id))
