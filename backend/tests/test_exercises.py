"""Exercise library, guide and video jobs (core/exercises.py, core/jobs/exercise_*.py),
with the LLM and YouTube faked."""

import asyncio
import json
from datetime import UTC, datetime, timedelta

import httpx2
import pytest
from pydantic import ValidationError

from core import exercises
from core.jobs import JobContext, PermanentJobError, exercise_guide, exercise_video
from core.llm import LlmConfig, LlmError, ask_json

NOW = datetime(2026, 10, 21, 9, tzinfo=UTC)
SQUAT = {
    "id": "Barbell_Squat",
    "name": "Barbell Squat",
    "category": "strength",
    "equipment": "barbell",
    "primary_muscles": ["quadriceps"],
    "secondary_muscles": ["glutes", "hamstrings"],
    "instructions": ["Stand under the bar.", "Squat down."],
}
GUIDE = {
    "about": "A compound lower-body lift that builds leg and hip strength.",
    "form_cues": ["Heels stay down.", "Knees follow your toes", "Brace your core"],
    "precautions": ["Use safety pins when training alone", "Stop if a knee hurts"],
}


def run(coroutine):
    return asyncio.run(coroutine)


class FakeDb:
    def __init__(self, rows, feedback=()):
        self.rows = rows
        self.feedback = list(feedback)
        self.updates = []

    async def select(self, table, params):
        return self.feedback if table == "video_feedback" else self.rows

    async def update(self, table, filters, values):
        self.updates.append(values)


def client(handler) -> httpx2.AsyncClient:
    return httpx2.AsyncClient(transport=httpx2.MockTransport(handler))


def groq_reply(content: str) -> httpx2.Response:
    return httpx2.Response(200, json={"choices": [{"message": {"content": content}}]})


GROQ_ONLY = LlmConfig("gsk_test", "qwen/test", None, "qwen3:8b")
BOTH = LlmConfig("gsk_test", "qwen/test", "http://ollama.test", "qwen3:8b")


# --- The LLM client ------------------------------------------------------------


def test_llm_answer_is_checked_and_thinking_removed():
    reply = "<think>let me think</think>" + json.dumps(GUIDE)

    async def go():
        async with client(lambda request: groq_reply(reply)) as http:
            return await ask_json(http, GROQ_ONLY, "system", "prompt", exercise_guide.Guide)

    answer = run(go())
    assert answer.model == "groq:qwen/test"
    assert answer.value.form_cues[0] == "Heels stay down"  # tidied


def test_ollama_is_the_backup_when_groq_fails():
    def handler(request):
        if "groq" in request.url.host:
            return httpx2.Response(503)
        return httpx2.Response(200, json={"message": {"content": json.dumps(GUIDE)}})

    async def go():
        async with client(handler) as http:
            return await ask_json(http, BOTH, "s", "p", exercise_guide.Guide)

    assert run(go()).model == "ollama:qwen3:8b"


def test_no_usable_answer_fails_the_attempt():
    async def go():
        async with client(lambda request: groq_reply('{"about": "too short"}')) as http:
            await ask_json(http, GROQ_ONLY, "s", "p", exercise_guide.Guide)

    with pytest.raises(LlmError):
        run(go())
    with pytest.raises(LlmError):
        run(ask_json(None, LlmConfig(None, "x", None, "y"), "s", "p", exercise_guide.Guide))  # type: ignore[arg-type]


# --- Writing a guide -------------------------------------------------------------


def test_guide_lines_must_be_short_and_enough():
    with pytest.raises(ValidationError):
        exercise_guide.Guide(**{**GUIDE, "form_cues": ["One"]})
    with pytest.raises(ValidationError):
        exercise_guide.Guide(**{**GUIDE, "precautions": ["x" * 200, "ok"]})


def test_prompt_describes_the_exercise():
    prompt = exercise_guide.build_prompt(SQUAT)
    assert "Barbell Squat" in prompt and "quadriceps" in prompt and "- Squat down." in prompt


def test_guide_job_saves_on_the_exercise():
    db = FakeDb([SQUAT])

    async def go():
        async with client(lambda request: groq_reply(json.dumps(GUIDE))) as http:
            ctx = JobContext("mac", 1, http, db=db, llm=GROQ_ONLY)
            return await exercise_guide.run({"exercise_id": "Barbell_Squat"}, ctx)

    assert run(go())["model"] == "groq:qwen/test"
    [saved] = db.updates
    assert saved["about"].startswith("A compound") and saved["guide_written_at"]


def test_guide_job_refuses_bad_input_and_vercel():
    ctx = JobContext("vercel", 1, None)  # type: ignore[arg-type]
    with pytest.raises(PermanentJobError):
        run(exercise_guide.run({"exercise_id": "Barbell_Squat"}, ctx))
    ctx = JobContext("mac", 1, None, db=FakeDb([]), llm=GROQ_ONLY)  # type: ignore[arg-type]
    with pytest.raises(PermanentJobError):
        run(exercise_guide.run({"exercise_id": "No_Such"}, ctx))
    with pytest.raises(ValidationError):
        run(exercise_guide.run({"exercise_id": "bad id; drop"}, ctx))


# --- Choosing a video --------------------------------------------------------------


def test_durations():
    assert exercise_video.parse_duration("PT1M30S") == 90
    assert exercise_video.parse_duration("PT45S") == 45
    assert exercise_video.parse_duration("PT1H") == 3600
    assert exercise_video.parse_duration("P0D") is None
    assert exercise_video.parse_duration(None) is None


def test_score_prefers_short_then_views_then_comments():
    short = exercise_video.score(40, 100_000, 3000, 0.5)
    long = exercise_video.score(170, 100_000, 3000, 0.5)
    assert short > long
    popular = exercise_video.score(60, 2_000_000, 50_000, 0.5)
    assert popular > exercise_video.score(60, 2_000, 50, 0.5)
    assert exercise_video.score(60, 1000, 10, 0.9) > exercise_video.score(60, 1000, 10, 0.1)


def youtube(request):
    path = request.url.path
    if path.endswith("/search"):
        return httpx2.Response(
            200,
            json={
                "items": [
                    {"id": {"videoId": v}} for v in ("vidShort01", "vidLong001", "vidQuiet01")
                ]
            },
        )
    if path.endswith("/videos"):

        def item(vid, duration, views, likes=None):
            stats = {"viewCount": str(views), **({"likeCount": str(likes)} if likes else {})}
            return {
                "id": vid,
                "snippet": {"title": f"How to {vid}", "channelTitle": "Coach"},
                "contentDetails": {"duration": duration},
                "statistics": stats,
            }

        everything = [
            item("vidShort01", "PT50S", 900_000, 40_000),
            item("vidLong001", "PT3M30S", 5_000_000, 90_000),  # over 3 minutes
            item("vidQuiet01", "PT2M10S", 1_200, 10),
        ]
        # Like YouTube: only the videos asked for.
        asked = request.url.params["id"].split(",")
        return httpx2.Response(200, json={"items": [i for i in everything if i["id"] in asked]})
    if path.endswith("/commentThreads"):
        if request.url.params["videoId"] == "vidQuiet01":
            return httpx2.Response(
                403, json={"error": {"errors": [{"reason": "commentsDisabled"}]}}
            )
        text = {"snippet": {"topLevelComment": {"snippet": {"textDisplay": "This fixed my form!"}}}}
        return httpx2.Response(200, json={"items": [text]})
    if "groq" in request.url.host:
        ratings = {
            "ratings": [
                {"video_id": "vidShort01", "relevance": 0.95, "positive": 0.9},
                {"video_id": "vidQuiet01", "relevance": 0.9, "positive": 0.5},
            ]
        }
        return groq_reply(json.dumps(ratings))
    return httpx2.Response(404)


def test_video_job_picks_the_best_short_video_and_saves_it():
    db = FakeDb([{"id": "Barbell_Squat", "name": "Barbell Squat"}])

    async def go():
        async with client(youtube) as http:
            ctx = JobContext("mac", 1, http, db=db, llm=GROQ_ONLY, youtube_api_key="yt")
            return await exercise_video.run({"exercise_id": "Barbell_Squat"}, ctx)

    result = run(go())
    assert (result["video_id"], result["considered"]) == ("vidShort01", 2)
    [saved] = db.updates
    assert saved["video_id"] == "vidShort01" and saved["video_duration_seconds"] == 50
    assert saved["video_checked_at"]


def test_no_suitable_video_is_remembered_so_it_isnt_searched_daily():
    db = FakeDb([{"id": "X", "name": "Obscure Move"}])

    async def go():
        async with client(lambda request: httpx2.Response(200, json={"items": []})) as http:
            ctx = JobContext("mac", 1, http, db=db, llm=GROQ_ONLY, youtube_api_key="yt")
            return await exercise_video.run({"exercise_id": "X"}, ctx)

    assert run(go())["video_id"] is None
    [saved] = db.updates
    assert saved["video_checked_at"] and saved["video_id"] is None


def test_used_up_quota_is_retried_later_and_missing_key_is_permanent():
    def quota(request):
        return httpx2.Response(403, text='{"error": {"errors": [{"reason": "quotaExceeded"}]}}')

    async def go(key):
        async with client(quota) as http:
            ctx = JobContext(
                "mac", 1, http, db=FakeDb([{"id": "X", "name": "X"}]), youtube_api_key=key
            )
            await exercise_video.run({"exercise_id": "X"}, ctx)

    with pytest.raises(RuntimeError, match="quota"):
        run(go("yt"))
    with pytest.raises(PermanentJobError):
        run(go(None))


# --- What the page shows ----------------------------------------------------------


def test_status_of_guide_and_video():
    row = {**SQUAT, "images": [], "level": None, "force": None, "mechanic": None}
    fresh = exercises.to_detail(row, exercises.JobState())
    assert (fresh.guide_status, fresh.video_status) == ("missing", "missing")
    queued = exercises.to_detail(
        row, exercises.JobState(queued={"write_exercise_guide", "find_exercise_video"})
    )
    assert (queued.guide_status, queued.video_status) == ("preparing", "preparing")
    done = exercises.to_detail(
        {
            **row,
            **GUIDE,
            "guide_written_at": NOW.isoformat(),
            "video_id": "vidShort01",
            "video_checked_at": NOW.isoformat(),
        },
        exercises.JobState(),
    )
    assert (done.guide_status, done.video_status) == ("ready", "ready")
    assert done.video.url == "https://www.youtube.com/watch?v=vidShort01"
    nothing = exercises.to_detail(
        {**row, "video_checked_at": NOW.isoformat()}, exercises.JobState()
    )
    assert nothing.video_status == "none_found"


def test_videos_are_refreshed_monthly():
    assert exercises.video_due({}, NOW)
    assert not exercises.video_due({"video_checked_at": (NOW - timedelta(days=5)).isoformat()}, NOW)
    assert exercises.video_due({"video_checked_at": (NOW - timedelta(days=31)).isoformat()}, NOW)


def test_search_text_cant_break_the_filter():
    assert exercises._search_term("squat),name.eq.x*") == "squatnameeqx"
    assert exercises._search_term("  Push-up ") == "Push-up"


class FakeSupabase:
    def __init__(self, row, queued_types=(), failed_jobs=(), feedback=()):
        self.row = row
        self.queued_types = list(queued_types)
        self.failed_jobs = list(failed_jobs)
        self.feedback = list(feedback)
        self.feedback_saved = []
        self.inserted = []

    async def select(self, table, params, token):
        if table == "exercises":
            return [self.row]
        if table == "video_feedback":
            return self.feedback
        return [{"type": t, "status": "pending"} for t in self.queued_types] + self.failed_jobs

    async def insert(self, table, values, token, returning="*"):
        if table == "video_feedback":
            self.feedback_saved.append(values)
            self.feedback.insert(0, values)
            return [{"id": "f"}]
        self.inserted.append(values["type"])
        return [{"id": "j", "status": "pending", "attempts": 0, **values}]


def test_prepare_queues_only_whats_missing_and_not_twice():
    row = {**SQUAT, "images": [], "guide_written_at": None, "video_checked_at": None}
    supabase = FakeSupabase(row)
    detail = run(exercises.prepare(supabase, "t", "profile", "Barbell_Squat"))
    assert supabase.inserted == ["write_exercise_guide", "find_exercise_video"]
    assert detail.guide_status == detail.video_status == "preparing"

    already = FakeSupabase(row, queued_types=["write_exercise_guide", "find_exercise_video"])
    run(exercises.prepare(already, "t", "profile", "Barbell_Squat"))
    assert already.inserted == []

    ready = FakeSupabase(
        {
            **row,
            "guide_written_at": NOW.isoformat(),
            "video_checked_at": datetime.now(UTC).isoformat(),
        }
    )
    run(exercises.prepare(ready, "t", "profile", "Barbell_Squat"))
    assert ready.inserted == []


def test_a_failed_job_is_shown_and_not_requeued_for_a_day():
    row = {**SQUAT, "images": [], "guide_written_at": NOW.isoformat(), "video_checked_at": None}
    recent = datetime.now(UTC).isoformat()
    failed = {
        "type": "find_exercise_video",
        "status": "failed",
        "last_error": "No key",
        "finished_at": recent,
    }
    supabase = FakeSupabase(row, failed_jobs=[failed])
    detail = run(exercises.prepare(supabase, "t", "profile", "Barbell_Squat"))
    assert supabase.inserted == []
    assert detail.video_status == "failed" and detail.video_error == "No key"

    old = {**failed, "finished_at": (datetime.now(UTC) - timedelta(days=2)).isoformat()}
    later = FakeSupabase(row, failed_jobs=[old])
    run(exercises.prepare(later, "t", "profile", "Barbell_Squat"))
    assert later.inserted == ["find_exercise_video"]


# --- "Is this the right video?" ------------------------------------------------------

REJECTED = {
    "video_id": "vidShort01",
    "video_title": "How to vidShort01",
    "reason": "This is a front squat, not a back squat",
}


def feedback_world(searched: list, rating_prompt: list, relevance: dict[str, float]):
    """YouTube and Groq stand-ins that record what the job asked for."""

    def handler(request):
        if "groq" in request.url.host:
            body = json.loads(request.content)
            prompt = body["messages"][1]["content"]
            if "Write a better YouTube search query" in prompt:
                plan = {
                    "query": "barbell back squat high bar tutorial",
                    "requirements": ["Bar on the upper back"],
                }
                return groq_reply(json.dumps(plan))
            rating_prompt.append(prompt)
            ratings = [
                {"video_id": vid, "relevance": rel, "positive": 0.5}
                for vid, rel in relevance.items()
            ]
            return groq_reply(json.dumps({"ratings": ratings}))
        if request.url.path.endswith("/search"):
            searched.append(request.url.params["q"])
        return youtube(request)

    return handler


def test_a_rejected_video_is_never_chosen_again_and_the_reason_shapes_the_search():
    db = FakeDb([{"id": "Barbell_Squat", "name": "Barbell Squat"}], feedback=[REJECTED])
    searched, prompts = [], []

    async def go():
        handler = feedback_world(searched, prompts, {"vidQuiet01": 0.9})
        async with client(handler) as http:
            ctx = JobContext("mac", 1, http, db=db, llm=GROQ_ONLY, youtube_api_key="yt")
            return await exercise_video.run({"exercise_id": "Barbell_Squat"}, ctx)

    result = run(go())
    assert searched == ["barbell back squat high bar tutorial"]
    assert "Bar on the upper back" in prompts[0]
    assert result["video_id"] == "vidQuiet01" and result["rejected_before"] == 1
    assert db.updates[0]["video_id"] == "vidQuiet01"


def test_videos_that_dont_teach_the_exercise_are_dropped():
    db = FakeDb([{"id": "Barbell_Squat", "name": "Barbell Squat"}])

    async def go():
        handler = feedback_world([], [], {"vidShort01": 0.2, "vidQuiet01": 0.3})
        async with client(handler) as http:
            ctx = JobContext("mac", 1, http, db=db, llm=GROQ_ONLY, youtube_api_key="yt")
            return await exercise_video.run({"exercise_id": "Barbell_Squat"}, ctx)

    assert run(go())["video_id"] is None
    assert db.updates[0]["video_id"] is None  # the old (maybe rejected) video is cleared


def test_without_an_llm_the_reasons_still_become_requirements():
    plan = run(
        exercise_video.plan_search(
            JobContext("mac", 1, None),  # type: ignore[arg-type]
            {"name": "Barbell Squat"},
            [REJECTED],
        )
    )
    assert plan.query == "Barbell Squat exercise how to proper form"
    assert plan.requirements == ["This is a front squat, not a back squat"]


def squat_with_video(**extra):
    return {
        **SQUAT,
        "images": [],
        "guide_written_at": NOW.isoformat(),
        "video_id": "vidShort01",
        "video_title": "How to vidShort01",
        "video_checked_at": datetime.now(UTC).isoformat(),
        **extra,
    }


def test_wrong_video_needs_a_reason():
    with pytest.raises(ValidationError, match="Say why"):
        exercises.VideoFeedback(video_id="vidShort01", verdict="wrong", reason="  ")
    ok = exercises.VideoFeedback(video_id="vidShort01", verdict="right", reason="")
    assert ok.reason is None


def test_wrong_video_feedback_is_saved_and_searches_again_straight_away():
    failed = {
        "type": "find_exercise_video",
        "status": "failed",
        "last_error": "x",
        "finished_at": datetime.now(UTC).isoformat(),
    }
    supabase = FakeSupabase(squat_with_video(), failed_jobs=[failed])
    body = exercises.VideoFeedback(
        video_id="vidShort01", verdict="wrong", reason="Front squat, not back"
    )
    detail = run(exercises.give_video_feedback(supabase, "t", "profile", "Barbell_Squat", body))
    assert supabase.feedback_saved[0]["reason"] == "Front squat, not back"
    assert supabase.feedback_saved[0]["video_title"] == "How to vidShort01"
    assert supabase.inserted == ["find_exercise_video"]  # even though one failed today
    assert detail.video_status == "preparing" and detail.videos_rejected == 1


def test_right_video_is_confirmed_and_not_refreshed_monthly():
    supabase = FakeSupabase(squat_with_video())
    body = exercises.VideoFeedback(video_id="vidShort01", verdict="right")
    detail = run(exercises.give_video_feedback(supabase, "t", "profile", "Barbell_Squat", body))
    assert detail.video.confirmed and supabase.inserted == []
    old = (datetime.now(UTC) - timedelta(days=40)).isoformat()
    stale = FakeSupabase(squat_with_video(video_checked_at=old), feedback=supabase.feedback)
    run(exercises.prepare(stale, "t", "profile", "Barbell_Squat"))
    assert stale.inserted == []  # confirmed: no monthly search


def test_feedback_on_a_video_that_has_since_changed_is_refused():
    supabase = FakeSupabase(squat_with_video(video_id="vidQuiet01"))
    body = exercises.VideoFeedback(video_id="vidShort01", verdict="right")
    with pytest.raises(exercises.VideoChangedError):
        run(exercises.give_video_feedback(supabase, "t", "profile", "Barbell_Squat", body))


class SearchSupabase:
    def __init__(self, rows, suggestions=()):
        self.rows = rows
        self.suggestions = list(suggestions)
        self.params = None
        self.rpc_args = None

    async def select(self, table, params, token):
        self.params = params
        return self.rows

    async def rpc(self, function, args, token=None):
        self.rpc_args = args
        return self.suggestions


def test_search_words_match_in_any_order():
    supabase = SearchSupabase([{"id": "Barbell_Squat", "name": "Barbell Squat", "images": []}])
    run(exercises.list_exercises(supabase, "t", "squat  barbell", None, None, 0))
    assert supabase.params["and"] == "(name.ilike.*squat*,name.ilike.*barbell*)"


def test_no_results_shows_the_5_closest_names_instead():
    close = [
        {"id": "Barbell_Squat", "name": "Barbell Squat", "images": ["a.jpg"], "similarity": 0.4}
    ]
    supabase = SearchSupabase([], suggestions=close)
    result = run(exercises.list_exercises(supabase, "t", "sqaut", "quadriceps", None, 0))
    assert result.items == [] and result.suggestions[0].name == "Barbell Squat"
    assert result.suggestions[0].image == "a.jpg"
    assert supabase.rpc_args["p_query"] == "sqaut" and supabase.rpc_args["p_muscle"] == "quadriceps"
    assert supabase.rpc_args["p_limit"] == 5
