"""`write_exercise_guide`: the LLM writes an exercise's about-text, form cues and
precautions once; they're saved on the exercise and reused by everyone.

Spec: context/pages/exercise-guide.md. Worker only: it writes to the shared
exercise library, which only the worker's key may change.
"""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from core.jobs import JobContext, JobSpec, PermanentJobError, register
from core.llm import ask_json

SYSTEM = (
    "You are an experienced strength and conditioning coach writing short, practical "
    "exercise guides for adults training at home or in a gym. Be accurate and specific, "
    "use plain English, and never give medical diagnoses. Follow current evidence-based "
    "coaching, not outdated rules (for example, knees may travel past the toes in a squat "
    "if the heels stay down). Answer with JSON only."
)


class ExercisePayload(BaseModel):
    exercise_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,100}$")


class Guide(BaseModel):
    about: str = Field(min_length=20, max_length=600)
    form_cues: list[str] = Field(min_length=3, max_length=8)
    precautions: list[str] = Field(min_length=2, max_length=6)

    @field_validator("form_cues", "precautions")
    @classmethod
    def short_lines(cls, lines: list[str]) -> list[str]:
        cleaned = [line.strip().rstrip(".") for line in lines if line and line.strip()]
        if any(len(line) > 160 for line in cleaned):
            raise ValueError("Each line must be short")
        return cleaned


def build_prompt(exercise: dict[str, Any]) -> str:
    def listed(values: list[str] | None) -> str:
        return ", ".join(values or []) or "none listed"

    steps = "\n".join(f"- {step}" for step in exercise.get("instructions") or [])
    return f"""Write a guide for this exercise.

Exercise: {exercise["name"]}
Type: {exercise.get("category") or "unknown"}; equipment: {exercise.get("equipment") or "none"}
Primary muscles: {listed(exercise.get("primary_muscles"))}
Secondary muscles: {listed(exercise.get("secondary_muscles"))}
How it's done:
{steps or "- (no instructions)"}

Return JSON with exactly these keys:
- "about": 2 or 3 sentences: what the exercise is and what it's good for.
- "form_cues": 4 to 6 short cues a person can check while doing it, each one line
  (e.g. "Knees track over your toes", "Feel it in the glutes, not the lower back").
- "precautions": 2 to 4 short safety points: common mistakes and who should take care
  (e.g. "Stop if you feel sharp pain in the knee").
"""


async def run(payload: dict[str, Any], ctx: JobContext) -> dict[str, Any]:
    if ctx.db is None or ctx.llm is None:
        raise PermanentJobError("Runs on the Mac worker only")
    exercise_id = ExercisePayload.model_validate(payload).exercise_id
    rows = await ctx.db.select(
        "exercises",
        {
            "select": "id,name,category,equipment,primary_muscles,secondary_muscles,instructions",
            "id": f"eq.{exercise_id}",
        },
    )
    if not rows:
        raise PermanentJobError(f"No exercise {exercise_id}")

    answer = await ask_json(ctx.http, ctx.llm, SYSTEM, build_prompt(rows[0]), Guide)
    guide = answer.value
    await ctx.db.update(
        "exercises",
        {"id": f"eq.{exercise_id}"},
        {
            "about": guide.about,
            "form_cues": guide.form_cues,
            "precautions": guide.precautions,
            "guide_model": answer.model,
            "guide_written_at": datetime.now(UTC).isoformat(),
        },
    )
    return {"exercise_id": exercise_id, "model": answer.model}


SPEC = register(
    JobSpec(type="write_exercise_guide", handler=run, max_attempts=3, timeout_seconds=360)
)
