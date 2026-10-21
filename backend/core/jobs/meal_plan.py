"""`generate_meal_plan`: make a person's weekly meal plan on the Mac worker, when
the API's quick attempt (Groq on Vercel) was too slow or failed. Here it tries
Groq, then Ollama, then the rules alone, so a plan is always made.
Spec: context/pages/nutrition-plan.md."""

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel

from core.jobs import JobContext, JobSpec, PermanentJobError, register
from core.nutrition.generate import build_plan
from core.nutrition.inputs import (
    MissingDetailsError,
    kept_days,
    load_inputs,
    merge_kept,
    status_to_save,
)


class MealPlanPayload(BaseModel):
    profile_id: str
    week_start: date
    today: date
    status: Literal["draft", "active"]
    reason: str
    # Varies the dishes for "Make a new plan".
    seed: str = ""


async def run(payload: dict[str, Any], ctx: JobContext) -> dict[str, Any]:
    if ctx.db is None:
        raise PermanentJobError("Runs on the Mac worker only")
    job = MealPlanPayload.model_validate(payload)
    try:
        inputs = await load_inputs(
            ctx.db.select, job.profile_id, job.week_start, job.today, job.seed
        )
    except MissingDetailsError as error:
        raise PermanentJobError(f"Missing: {error}") from error
    status = await status_to_save(
        ctx.db.select, job.profile_id, job.week_start, job.status, job.reason
    )
    if status is None:
        return {"skipped": "The week already has a plan"}
    plan = await build_plan(inputs, ctx.http, ctx.llm, job.reason)
    plan = merge_kept(
        await kept_days(ctx.db.select, job.profile_id, job.week_start, job.today), plan
    )
    plan_id = await ctx.db.rpc(
        "save_meal_plan",
        {
            "p_profile_id": job.profile_id,
            "p_week_start": job.week_start.isoformat(),
            "p_status": status,
            "p_plan": plan,
        },
    )
    return {"plan_id": plan_id, "status": status, "made_by": plan["made_by"]}


SPEC = register(
    JobSpec(type="generate_meal_plan", handler=run, max_attempts=3, timeout_seconds=600)
)
