"""`find_exercise_video`: pick the best short YouTube video for an exercise.

Spec: context/pages/exercise-guide.md ("Choosing the YouTube video"):
under 3 minutes (Shorts allowed), then most views, then positive comments.
Each exercise is searched once and refreshed monthly. Worker only.

YouTube Data API quota (10,000 units a day, free): a search costs 100 units,
video details and each comment list 1 unit, so about 105 per exercise.
"""

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
COMMENT_CANDIDATES = 5
COMMENTS_PER_VIDEO = 15


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


class CommentRating(BaseModel):
    video_id: str
    positive: float = Field(ge=0, le=1)


class CommentRatings(BaseModel):
    ratings: list[CommentRating]


async def _get(http: httpx2.AsyncClient, key: str, path: str, params: dict[str, Any]) -> dict:
    response = await http.get(f"{API}/{path}", params={**params, "key": key}, timeout=20)
    if response.status_code == 403 and "quota" in response.text.lower():
        raise YouTubeQuotaError
    response.raise_for_status()
    return response.json()


async def candidates(http: httpx2.AsyncClient, key: str, name: str) -> list[dict[str, Any]]:
    """Short, embeddable videos for the exercise, with duration and counts."""
    found = await _get(
        http,
        key,
        "search",
        {
            "part": "snippet",
            "q": f"{name} exercise how to proper form",
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
        if item.get("id", {}).get("videoId")
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
        if duration is None or duration >= MAX_SECONDS or "viewCount" not in stats:
            continue
        videos.append(
            {
                "id": item["id"],
                "title": item["snippet"]["title"],
                "channel": item["snippet"]["channelTitle"],
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


async def rate_comments(
    ctx: JobContext, name: str, by_video: dict[str, list[str]]
) -> dict[str, float]:
    """0..1 per video: do the comments say the video is clear and correct?
    Videos without comments, or if no LLM answers, count as neutral (0.5)."""
    with_comments = {vid: texts for vid, texts in by_video.items() if texts}
    neutral = dict.fromkeys(by_video, 0.5)
    if not with_comments or ctx.llm is None:
        return neutral
    blocks = "\n\n".join(
        f"Video {vid}:\n" + "\n".join(f"- {text}" for text in texts)
        for vid, texts in with_comments.items()
    )
    prompt = (
        f"These are top comments on YouTube videos teaching the exercise '{name}'. "
        "For each video, rate from 0 to 1 how much the comments say the video is clear, "
        "correct and helpful (e.g. 'fixed my form', 'great cues') versus wrong, confusing "
        "or unsafe. Ignore jokes and off-topic comments.\n\n"
        f"{blocks}\n\n"
        'Return JSON: {"ratings": [{"video_id": "...", "positive": 0.0}]}'
    )
    try:
        answer = await ask_json(
            ctx.http,
            ctx.llm,
            "You rate YouTube comments. Answer with JSON only.",
            prompt,
            CommentRatings,
        )
    except LlmError:
        return neutral
    return {
        **neutral,
        **{r.video_id: r.positive for r in answer.value.ratings if r.video_id in by_video},
    }


async def run(payload: dict[str, Any], ctx: JobContext) -> dict[str, Any]:
    if ctx.db is None:
        raise PermanentJobError("Runs on the Mac worker only")
    if not ctx.youtube_api_key:
        raise PermanentJobError("YOUTUBE_API_KEY isn't set on the worker")
    exercise_id = ExercisePayload.model_validate(payload).exercise_id
    rows = await ctx.db.select("exercises", {"select": "id,name", "id": f"eq.{exercise_id}"})
    if not rows:
        raise PermanentJobError(f"No exercise {exercise_id}")
    name = rows[0]["name"]
    key = ctx.youtube_api_key

    try:
        videos = await candidates(ctx.http, key, name)
        # Read comments only for the most likely winners, to save quota.
        videos.sort(key=lambda v: score(v["duration"], v["views"], v["likes"], 0.5), reverse=True)
        shortlist = videos[:COMMENT_CANDIDATES]
        by_video = {v["id"]: await comments(ctx.http, key, v["id"]) for v in shortlist}
    except YouTubeQuotaError as error:
        raise RuntimeError("YouTube's daily quota is used up; will try again later") from error

    ratings = await rate_comments(ctx, name, by_video)
    for video in shortlist:
        video["score"] = score(
            video["duration"], video["views"], video["likes"], ratings[video["id"]]
        )
    best = max(shortlist, key=lambda v: v["score"], default=None)

    values: dict[str, Any] = {"video_checked_at": datetime.now(UTC).isoformat()}
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
        "considered": len(videos),
    }


# Retries wait 1, 5, 25 minutes …; a used-up quota resets at midnight Pacific time.
SPEC = register(
    JobSpec(type="find_exercise_video", handler=run, max_attempts=4, timeout_seconds=300)
)
