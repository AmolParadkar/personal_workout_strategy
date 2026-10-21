"""`find_exercise_video`: pick the best short YouTube video for an exercise.

Spec: context/pages/exercise-guide.md ("Choosing the YouTube video", "Video
feedback"): under 3 minutes (Shorts allowed), then most views, then positive
comments, and it must actually teach this exercise. Each exercise is searched
once and refreshed monthly. When someone says a video is wrong (with a reason),
the job runs again: the LLM turns the reasons into a better search and
requirements, rejected videos are never chosen again, and candidates that
don't meet the requirements are dropped. Worker only.

YouTube Data API quota (10,000 units a day, free): a search costs 100 units,
video details and each comment list 1 unit, so about 105 per exercise.
"""

import asyncio
import math
import re
from datetime import UTC, datetime
from typing import Any

import httpx2
from pydantic import BaseModel, Field

from core.jobs import JobContext, JobSpec, PermanentJobError, register
from core.jobs.exercise_guide import ExercisePayload
from core.llm import LlmError, ask_json

API = "https://www.googleapis.com/youtube/v3"
MAX_SECONDS = 180
SEARCH_RESULTS = 15
SHORTLIST = 5
# After a rejection, look at more candidates closely.
SHORTLIST_AFTER_FEEDBACK = 8
COMMENTS_PER_VIDEO = 15
# Below this, the LLM thinks the video doesn't teach this exercise (or breaks a requirement).
MIN_RELEVANCE = 0.5


class YouTubeQuotaError(Exception):
    """Today's YouTube quota is used up: try again tomorrow."""


def parse_duration(iso: str | None) -> int | None:
    """'PT1M30S' → 90 seconds (None if it isn't a plain duration)."""
    match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not match or not any(match.groups()):
        return None
    hours, mins, secs = (int(part or 0) for part in match.groups())
    return hours * 3600 + mins * 60 + secs


def score(duration: int, views: int, likes: int | None, comment_score: float) -> float:
    """Shorter first, then views, then positive comments (each 0..1, weighted)."""
    shortness = max(0.0, 1 - duration / MAX_SECONDS)
    reach = min(1.0, math.log10(views + 1) / 7)  # 10 million views → 1
    liked = min(1.0, (likes or 0) / views * 20) if views else 0.0  # 5% likes → 1
    return round(0.35 * shortness + 0.35 * reach + 0.1 * liked + 0.2 * comment_score, 4)


async def _get(http: httpx2.AsyncClient, key: str, path: str, params: dict[str, Any]) -> dict:
    response = await http.get(f"{API}/{path}", params={**params, "key": key}, timeout=20)
    if response.status_code == 403 and "quota" in response.text.lower():
        raise YouTubeQuotaError
    response.raise_for_status()
    return response.json()


def default_query(name: str) -> str:
    return f"{name} exercise how to proper form"


async def candidates(
    http: httpx2.AsyncClient, key: str, query: str, exclude: frozenset[str] | set[str] = frozenset()
) -> list[dict[str, Any]]:
    """Short, embeddable videos for a search, with duration and counts (minus `exclude`)."""
    found = await _get(
        http,
        key,
        "search",
        {
            "part": "snippet",
            "q": query,
            "type": "video",
            "videoDuration": "short",  # YouTube's "short" is under 4 minutes
            "videoEmbeddable": "true",
            "safeSearch": "strict",
            "relevanceLanguage": "en",
            "maxResults": SEARCH_RESULTS,
        },
    )
    ids = [
        item["id"]["videoId"]
        for item in found.get("items", [])
        if item.get("id", {}).get("videoId") and item["id"]["videoId"] not in exclude
    ]
    if not ids:
        return []
    details = await _get(
        http, key, "videos", {"part": "snippet,contentDetails,statistics", "id": ",".join(ids)}
    )
    videos = []
    for item in details.get("items", []):
        duration = parse_duration(item.get("contentDetails", {}).get("duration"))
        stats = item.get("statistics", {})
        if (
            item["id"] in exclude
            or duration is None
            or duration >= MAX_SECONDS
            or "viewCount" not in stats
        ):
            continue
        videos.append(
            {
                "id": item["id"],
                "title": item["snippet"]["title"],
                "channel": item["snippet"]["channelTitle"],
                "description": (item["snippet"].get("description") or "")[:300],
                "duration": duration,
                "views": int(stats["viewCount"]),
                "likes": int(stats["likeCount"]) if "likeCount" in stats else None,
            }
        )
    return videos


async def comments(http: httpx2.AsyncClient, key: str, video_id: str) -> list[str]:
    try:
        data = await _get(
            http,
            key,
            "commentThreads",
            {
                "part": "snippet",
                "videoId": video_id,
                "maxResults": COMMENTS_PER_VIDEO,
                "order": "relevance",
                "textFormat": "plainText",
            },
        )
    except httpx2.HTTPStatusError:
        return []  # comments turned off
    return [
        item["snippet"]["topLevelComment"]["snippet"]["textDisplay"][:300]
        for item in data.get("items", [])
    ]


class SearchPlan(BaseModel):
    query: str = Field(min_length=5, max_length=120)
    # What the right video must show, learnt from the reasons (e.g. "bar on the upper back").
    requirements: list[str] = Field(default_factory=list, max_length=6)


class VideoRating(BaseModel):
    video_id: str
    # Does it teach exactly this exercise and meet the requirements?
    relevance: float = Field(ge=0, le=1)
    # Do the comments say it's clear and correct?
    positive: float = Field(ge=0, le=1)


class VideoRatings(BaseModel):
    ratings: list[VideoRating]


async def plan_search(
    ctx: JobContext, exercise: dict[str, Any], rejections: list[dict[str, Any]]
) -> SearchPlan:
    """The search to run. After rejections, the LLM rewrites it from the reasons."""
    fallback = SearchPlan(
        query=default_query(exercise["name"]),
        requirements=[r["reason"] for r in rejections][:6],
    )
    if not rejections or ctx.llm is None:
        return fallback
    rejected = "\n".join(
        f'- "{r.get("video_title") or r["video_id"]}": {r["reason"]}' for r in rejections
    )
    muscles = ", ".join(exercise.get("primary_muscles") or [])
    equipment = exercise.get("equipment") or "none"
    prompt = f"""We're choosing a short YouTube tutorial (under 3 minutes) for this exercise:
{exercise["name"]} (equipment: {equipment}; muscles: {muscles}).

People rejected these videos, with their reasons:
{rejected}

Write a better YouTube search query (a few words, in English) that finds a correct
tutorial for exactly this exercise, and list what the right video must show or avoid,
based on the reasons.

Return JSON: {{"query": "...", "requirements": ["...", "..."]}}"""
    try:
        answer = await ask_json(
            ctx.http,
            ctx.llm,
            "You help find correct YouTube exercise tutorials. Answer with JSON only.",
            prompt,
            SearchPlan,
        )
    except LlmError:
        return fallback
    return answer.value


async def rate_videos(
    ctx: JobContext,
    exercise: dict[str, Any],
    requirements: list[str],
    shortlist: list[dict[str, Any]],
    by_video: dict[str, list[str]],
) -> dict[str, VideoRating]:
    """Relevance and comment tone for each shortlisted video, in one LLM call.
    If no LLM answers: relevance 1 (trust the search) and neutral comments (0.5)."""
    neutral = {v["id"]: VideoRating(video_id=v["id"], relevance=1, positive=0.5) for v in shortlist}
    if not shortlist or ctx.llm is None:
        return neutral
    blocks = []
    for video in shortlist:
        comments_text = "\n".join(f"  - {t}" for t in by_video.get(video["id"], [])) or "  (none)"
        blocks.append(
            f"Video {video['id']}\nTitle: {video['title']}\nChannel: {video['channel']}\n"
            f"Description: {video.get('description') or '(none)'}\nTop comments:\n{comments_text}"
        )
    must = "\n".join(f"- {r}" for r in requirements) or "- (none beyond teaching this exercise)"
    prompt = f"""Exercise: {exercise["name"]} (equipment: {exercise.get("equipment") or "none"}).
The right video must:
{must}

For each video below, rate from 0 to 1:
- "relevance": does it teach exactly this exercise (not a different variation) and meet
  the requirements above? Judge from the title, description and comments.
- "positive": do the comments say it's clear, correct and helpful (e.g. "fixed my form")
  rather than wrong, confusing or unsafe? Use 0.5 if there are no useful comments.

{chr(10).join(blocks)}

Return JSON: {{"ratings": [{{"video_id": "...", "relevance": 0.0, "positive": 0.0}}]}}"""
    try:
        answer = await ask_json(
            ctx.http,
            ctx.llm,
            "You check whether YouTube videos teach a given exercise. Answer with JSON only.",
            prompt,
            VideoRatings,
        )
    except LlmError:
        return neutral
    rated = {r.video_id: r for r in answer.value.ratings if r.video_id in neutral}
    return {**neutral, **rated}


async def run(payload: dict[str, Any], ctx: JobContext) -> dict[str, Any]:
    if ctx.db is None:
        raise PermanentJobError("Runs on the Mac worker only")
    if not ctx.youtube_api_key:
        raise PermanentJobError("YOUTUBE_API_KEY isn't set on the worker")
    exercise_id = ExercisePayload.model_validate(payload).exercise_id
    rows = await ctx.db.select(
        "exercises",
        {"select": "id,name,equipment,primary_muscles", "id": f"eq.{exercise_id}"},
    )
    if not rows:
        raise PermanentJobError(f"No exercise {exercise_id}")
    exercise = rows[0]
    rejections = await ctx.db.select(
        "video_feedback",
        {
            "select": "video_id,video_title,reason",
            "exercise_id": f"eq.{exercise_id}",
            "verdict": "eq.wrong",
            "order": "created_at.desc",
            "limit": "20",
        },
    )
    rejected_ids = {r["video_id"] for r in rejections}
    plan = await plan_search(ctx, exercise, rejections)
    key = ctx.youtube_api_key

    try:
        videos = await candidates(ctx.http, key, plan.query, exclude=rejected_ids)
        # Look closely (comments, relevance) only at the most likely winners, to save quota.
        videos.sort(key=lambda v: score(v["duration"], v["views"], v["likes"], 0.5), reverse=True)
        shortlist = videos[: SHORTLIST_AFTER_FEEDBACK if rejections else SHORTLIST]
        # Fetched side by side rather than one after another.
        lists = await asyncio.gather(*(comments(ctx.http, key, v["id"]) for v in shortlist))
        by_video = {v["id"]: texts for v, texts in zip(shortlist, lists, strict=True)}
    except YouTubeQuotaError as error:
        raise RuntimeError("YouTube's daily quota is used up; will try again later") from error

    ratings = await rate_videos(ctx, exercise, plan.requirements, shortlist, by_video)
    eligible = []
    for video in shortlist:
        rating = ratings[video["id"]]
        if rating.relevance < MIN_RELEVANCE:
            continue
        base = score(video["duration"], video["views"], video["likes"], rating.positive)
        video["score"] = round(base * rating.relevance, 4)
        eligible.append(video)
    best = max(eligible, key=lambda v: v["score"], default=None)

    # Without a suitable video, clear the old one: it may be the one just rejected.
    values: dict[str, Any] = {
        "video_checked_at": datetime.now(UTC).isoformat(),
        "video_id": None,
        "video_title": None,
        "video_channel": None,
        "video_duration_seconds": None,
        "video_views": None,
        "video_score": None,
    }
    if best:
        values |= {
            "video_id": best["id"],
            "video_title": best["title"][:200],
            "video_channel": best["channel"][:100],
            "video_duration_seconds": best["duration"],
            "video_views": best["views"],
            "video_score": best["score"],
        }
    await ctx.db.update("exercises", {"id": f"eq.{exercise_id}"}, values)
    return {
        "exercise_id": exercise_id,
        "video_id": best["id"] if best else None,
        "query": plan.query,
        "considered": len(videos),
        "rejected_before": len(rejected_ids),
    }


# Retries wait 1, 5, 25 minutes …; a used-up quota resets at midnight Pacific time.
SPEC = register(
    JobSpec(type="find_exercise_video", handler=run, max_attempts=4, timeout_seconds=300)
)
