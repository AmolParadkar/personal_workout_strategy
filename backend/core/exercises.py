"""The exercise library: browsing, one exercise in detail, and asking the worker
to prepare its guide and video (context/pages/exercise-guide.md)."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from core.jobs import queue
from core.models.exercises import ExerciseDetail, ExerciseList, ExerciseSummary, PartStatus, Video
from core.supabase import SupabaseClient

PAGE_SIZE = 30
VIDEO_REFRESH = timedelta(days=30)
FAILED_WAIT = timedelta(days=1)
GUIDE_JOB = "write_exercise_guide"
VIDEO_JOB = "find_exercise_video"


class ExerciseNotFoundError(Exception):
    pass


def _search_term(text: str) -> str:
    # Supabase filter syntax uses commas, brackets and * : keep letters, digits, spaces, '-'.
    return "".join(ch for ch in text if ch.isalnum() or ch in " -").strip()


async def list_exercises(
    supabase: SupabaseClient,
    token: str,
    search: str | None,
    muscle: str | None,
    equipment: str | None,
    offset: int,
) -> ExerciseList:
    params = {
        "select": "id,name,category,equipment,level,primary_muscles,images",
        "order": "name",
        "limit": str(PAGE_SIZE + 1),
        "offset": str(offset),
    }
    term = _search_term(search or "")
    if term:
        params["name"] = f"ilike.*{term}*"
    if muscle:
        params["primary_muscles"] = f'cs.{{"{muscle}"}}'
    if equipment:
        params["equipment"] = f"eq.{equipment}"
    rows = await supabase.select("exercises", params, token)
    return ExerciseList(
        items=[
            ExerciseSummary(
                **{k: v for k, v in row.items() if k != "images"},
                image=(row["images"] or [None])[0],
            )
            for row in rows[:PAGE_SIZE]
        ],
        has_more=len(rows) > PAGE_SIZE,
    )


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


def video_due(row: dict[str, Any], now: datetime) -> bool:
    checked = row.get("video_checked_at")
    return not checked or now - datetime.fromisoformat(checked) > VIDEO_REFRESH


def _status(ready: bool, queued: bool, failed: bool, none_found: bool = False) -> PartStatus:
    if queued:
        return "preparing"
    if ready:
        return "ready"
    if none_found:
        return "none_found"
    return "failed" if failed else "missing"


def to_detail(row: dict[str, Any], jobs: JobState) -> ExerciseDetail:
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
        )
    return ExerciseDetail(
        **{
            k: row.get(k)
            for k in ExerciseDetail.model_fields
            if k not in ("video", "guide_status", "video_status", "guide_error", "video_error")
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
    )


async def _row(supabase: SupabaseClient, token: str, exercise_id: str) -> dict[str, Any]:
    rows = await supabase.select("exercises", {"select": "*", "id": f"eq.{exercise_id}"}, token)
    if not rows:
        raise ExerciseNotFoundError
    return rows[0]


async def get_exercise(supabase: SupabaseClient, token: str, exercise_id: str) -> ExerciseDetail:
    row = await _row(supabase, token, exercise_id)
    return to_detail(row, await _job_state(supabase, token, exercise_id))


async def prepare(
    supabase: SupabaseClient, token: str, profile_id: str, exercise_id: str
) -> ExerciseDetail:
    """Queue the guide and video jobs this exercise still needs (once each; not
    again within a day of one failing, so a broken setup doesn't queue on every visit)."""
    row = await _row(supabase, token, exercise_id)
    jobs = await _job_state(supabase, token, exercise_id)
    payload = {"exercise_id": exercise_id}
    for job_type, needed in (
        (GUIDE_JOB, guide_missing(row)),
        (VIDEO_JOB, video_due(row, datetime.now(UTC))),
    ):
        if needed and job_type not in jobs.queued and job_type not in jobs.failed:
            await queue.enqueue(supabase, token, profile_id, job_type, payload)
            jobs.queued.add(job_type)
    return to_detail(row, jobs)
