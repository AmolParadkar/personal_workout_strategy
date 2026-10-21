"""Weekly workout plans (core/workouts/): the rules, checking the LLM's answer,
and the Vercel-first flow, with a small made-up library and the LLM faked."""

import asyncio
import json
from datetime import date

import httpx2
import pytest

from core.llm import LlmConfig, LlmError
from core.workouts import generate, plans, rules
from core.workouts.generate import PlanInputs


def ex(
    id_,
    category="strength",
    equipment="body only",
    level="beginner",
    mechanic="compound",
    force="push",
    primary=("chest",),
    secondary=(),
):
    return {
        "id": id_,
        "name": id_.replace("_", " "),
        "category": category,
        "equipment": equipment,
        "level": level,
        "mechanic": mechanic,
        "force": force,
        "primary_muscles": list(primary),
        "secondary_muscles": list(secondary),
    }


LIBRARY = [
    # Cardio
    ex("Fast_Skipping", "plyometrics", primary=("quadriceps",)),
    ex("Star_Jump", "plyometrics", primary=("quadriceps",)),
    ex("Double_Leg_Butt_Kick", "plyometrics", primary=("hamstrings",)),
    ex("Jogging,_Treadmill", "cardio", equipment="machine", primary=("quadriceps",)),
    # Stretches: moving and held
    *[ex(f"Arm_Circles_{m}", "stretching", primary=(m,)) for m in rules.FOCUS_MUSCLES["full_body"]],
    *[
        ex(f"Lying_{m}_Stretch", "stretching", primary=(m,))
        for m in rules.FOCUS_MUSCLES["full_body"]
    ],
    # Activation (bodyweight isolation, one hold)
    ex("Glute_Bridge", mechanic="isolation", primary=("glutes",)),
    ex("Side_Bridge", mechanic="isolation", force="static", primary=("abdominals",)),
    ex("Band_Pull_Apart", equipment="bands", mechanic="isolation", primary=("middle back",)),
    # Main
    ex("Pushups", primary=("chest",), secondary=("triceps",)),
    ex("Dumbbell_Bench_Press", equipment="dumbbell", primary=("chest",)),
    ex("Goblet_Squat", equipment="dumbbell", primary=("quadriceps",), secondary=("glutes",)),
    ex("Dumbbell_Row", equipment="dumbbell", force="pull", primary=("middle back",)),
    ex("Pullups", force="pull", primary=("lats",)),
    ex("Romanian_Deadlift", equipment="dumbbell", primary=("hamstrings",)),
    ex("Dumbbell_Shoulder_Press", equipment="dumbbell", primary=("shoulders",)),
    ex("Barbell_Squat", equipment="barbell", primary=("quadriceps",)),
    ex(
        "Snatch",
        "olympic weightlifting",
        equipment="barbell",
        level="expert",
        primary=("quadriceps",),
    ),
    ex("Cable_Fly", equipment="cable", mechanic="isolation", primary=("chest",)),
]


def inputs(**overrides) -> PlanInputs:
    values = dict(
        profile_id="p1",
        week_start=date(2026, 10, 19),
        today=date(2026, 10, 19),
        goals=["build_muscle"],
        experience="beginner",
        available_days=["mon", "wed", "fri"],
        minutes_per_session=45,
        equipment=["dumbbells", "resistance_bands"],
        location="home",
        sex="female",
        age=34,
        injuries=None,
        library=LIBRARY,
    )
    return PlanInputs(**{**values, **overrides})


def run(coroutine):
    return asyncio.run(coroutine)


# --- Rules ---------------------------------------------------------------------------


def test_kit_matches_settings_equipment_to_the_library():
    kit = rules.kit_for(["dumbbells", "resistance_bands"], "home")
    assert kit.equipment == {"dumbbell", "bands"} and not kit.has_bar
    gym = rules.kit_for([], "gym")
    assert gym.full_gym and gym.has_bar and "machine" in gym.equipment
    assert "Jogging, Treadmill" in rules.kit_for(["treadmill"], "home").cardio_names


def test_only_doable_exercises_are_used():
    kit = rules.kit_for(["dumbbells"], "home")
    by_id = {e["id"]: e for e in LIBRARY}
    assert rules.usable(by_id["Goblet_Squat"], kit, "beginner")
    assert not rules.usable(by_id["Barbell_Squat"], kit, "beginner")  # no barbell
    assert not rules.usable(by_id["Pullups"], kit, "beginner")  # no pull-up bar
    assert rules.usable(by_id["Pullups"], rules.kit_for(["pull_up_bar"], "home"), "beginner")
    gym = rules.kit_for(["full_gym"], "gym")
    assert not rules.usable(by_id["Snatch"], gym, "intermediate")  # expert + olympic
    assert rules.usable(by_id["Snatch"], gym, "advanced")


def test_training_days_skip_the_past_and_keep_a_rest_day():
    monday = date(2026, 10, 19)
    days = rules.training_days(monday, date(2026, 10, 21), ["mon", "wed", "fri"])
    assert days == [date(2026, 10, 21), date(2026, 10, 23)]
    every_day = rules.training_days(monday, monday, rules.DAY_CODES)
    assert len(every_day) == 6
    assert rules.split_for(4) == ["upper", "lower", "upper", "lower"]
    assert rules.split_for(0) == []


def test_phase_minutes_add_up_and_follow_goals():
    for total in (20, 45, 90):
        m = rules.phase_minutes(total, ["build_muscle"])
        assert m.cardio + m.mobility + m.activation + m.main + m.cooldown == total
    assert (
        rules.phase_minutes(60, ["lose_fat"]).cardio
        > rules.phase_minutes(60, ["build_muscle"]).cardio
    )
    assert rules.phase_minutes(60, ["mobility"]).mobility > rules.phase_minutes(60, []).mobility


def test_sets_and_reps_follow_goals_and_experience():
    assert rules.main_prescription(["get_stronger"], "advanced").reps_max == 6
    assert rules.main_prescription(["build_muscle"], "beginner").sets == 3
    assert rules.main_prescription(["lose_fat"], "beginner").reps_min == 12


# --- Rules-only plan -------------------------------------------------------------------


def phases(session):
    return [item["phase"] for item in session["items"]]


def test_rules_only_plan_has_all_five_phases_every_day():
    plan = run(generate.build_plan(inputs(), None, None, "new_week"))
    assert plan["made_by"] == "rules" and len(plan["sessions"]) == 3
    by_id = {e["id"]: e for e in LIBRARY}
    for session in plan["sessions"]:
        assert set(phases(session)) == {"cardio", "mobility", "activation", "main", "cooldown"}
        cooldown = [
            by_id[i["exercise_id"]]["name"] for i in session["items"] if i["phase"] == "cooldown"
        ]
        assert all("Stretch" in name for name in cooldown)  # held stretches after
        mobility = [
            by_id[i["exercise_id"]]["name"] for i in session["items"] if i["phase"] == "mobility"
        ]
        assert all("Circles" in name for name in mobility)  # moving stretches before
        for item in session["items"]:
            assert rules.usable(
                by_id[item["exercise_id"]],
                rules.kit_for(["dumbbells", "resistance_bands"], "home"),
                "beginner",
            )


def test_no_machine_warm_up_is_rounds_of_short_drills():
    plan = run(generate.build_plan(inputs(goals=["lose_fat"]), None, None, "new_week"))
    cardio = [i for i in plan["sessions"][0]["items"] if i["phase"] == "cardio"]
    assert len(cardio) == 3 and all(i["duration_seconds"] == 60 for i in cardio)
    with_treadmill = run(
        generate.build_plan(inputs(equipment=["treadmill", "dumbbells"]), None, None, "new_week")
    )
    [machine] = [i for i in with_treadmill["sessions"][0]["items"] if i["phase"] == "cardio"]
    assert machine["exercise_id"] == "Jogging,_Treadmill" and machine["duration_seconds"] >= 180


def test_holds_are_timed_not_counted():
    plan = run(generate.build_plan(inputs(available_days=rules.DAY_CODES), None, None, "new_week"))
    holds = [i for s in plan["sessions"] for i in s["items"] if i["exercise_id"] == "Side_Bridge"]
    assert holds and all(i.get("duration_seconds") and not i.get("reps_min") for i in holds)


def test_plans_are_repeatable_for_a_week_and_vary_between_weeks():
    def mains(plan):
        return [
            [i["exercise_id"] for i in s["items"] if i["phase"] == "main"] for s in plan["sessions"]
        ]

    a = run(generate.build_plan(inputs(), None, None, "new_week"))
    b = run(generate.build_plan(inputs(), None, None, "new_week"))
    assert mains(a) == mains(b)


def test_no_training_days_left_explains_why():
    plan = run(generate.build_plan(inputs(today=date(2026, 10, 25)), None, None, "new_week"))
    assert plan["sessions"] == [] and "Settings" in plan["rationale"]


# --- The LLM's answer -------------------------------------------------------------------

GROQ = LlmConfig("gsk_test", "qwen/test", None, "")


def groq_answer(sessions_fn):
    def handler(request):
        prompt = json.loads(request.content)["messages"][1]["content"]
        return httpx2.Response(
            200, json={"choices": [{"message": {"content": json.dumps(sessions_fn(prompt))}}]}
        )

    return httpx2.AsyncClient(transport=httpx2.MockTransport(handler))


def llm_week(sessions, main_ids):
    return {
        "rationale": "Three full-body sessions to build muscle safely.",
        "sessions": [
            {
                "day": s.day.isoformat(),
                "title": "Full body A",
                "explanation": "Squat, push and pull patterns for the whole body.",
                "main": [[i, 3, 12, 8, 90] for i in main_ids(s)],
            }
            for s in sessions
        ],
    }


def test_valid_llm_choices_are_used_with_its_words():
    plan_inputs = inputs()
    sessions = generate.skeleton(plan_inputs)

    async def go():
        async with groq_answer(
            lambda p: llm_week(sessions, lambda s: [e["id"] for e in s.candidates[:3]])
        ) as http:
            return await generate.build_plan(plan_inputs, http, GROQ, "requested")

    plan = run(go())
    assert plan["made_by"] == "groq:qwen/test"
    assert plan["sessions"][0]["title"] == "Full body A"
    main = [i for i in plan["sessions"][0]["items"] if i["phase"] == "main"]
    assert (main[0]["reps_min"], main[0]["reps_max"]) == (8, 12)  # swapped into order


def test_llm_choices_outside_the_list_fall_back_to_rules():
    plan_inputs = inputs()
    sessions = generate.skeleton(plan_inputs)

    async def go():
        async with groq_answer(
            lambda p: llm_week(sessions, lambda s: ["Snatch", "Made_Up"])
        ) as http:
            return await generate.build_plan(plan_inputs, http, GROQ, "requested")

    plan = run(go())
    assert plan["made_by"] == "rules"
    assert plan["sessions"][0]["title"] == rules.FOCUS_TITLES["full_body"]


def test_the_prompt_lists_injuries_and_only_allowed_exercises():
    plan_inputs = inputs(injuries="Sore left knee")
    sessions = generate.skeleton(plan_inputs)
    prompt = generate.build_prompt(plan_inputs, sessions)
    assert "Sore left knee" in prompt and "Barbell_Squat" not in prompt
    assert all(e["id"] in prompt for e in sessions[0].candidates)


def test_without_an_answer_the_api_can_hand_over_to_the_worker():
    async def go():
        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(lambda r: httpx2.Response(503))
        ) as http:
            await generate.build_plan(
                inputs(), http, GROQ, "requested", rules_only_if_llm_fails=False
            )

    with pytest.raises(LlmError):
        run(go())


# --- Coverage ------------------------------------------------------------------------------


def test_coverage_counts_working_sets_per_muscle():
    sessions = [
        {
            "session_items": [
                {
                    "phase": "main",
                    "sets": 3,
                    "exercises": {"primary_muscles": ["chest"], "secondary_muscles": ["triceps"]},
                },
                {
                    "phase": "activation",
                    "sets": 2,
                    "exercises": {"primary_muscles": ["glutes"], "secondary_muscles": []},
                },
                {
                    "phase": "cooldown",
                    "sets": 1,
                    "exercises": {"primary_muscles": ["chest"], "secondary_muscles": []},
                },
            ]
        }
    ]
    assert {c.muscle: c.sets for c in plans.coverage(sessions)} == {
        "chest": 3,
        "glutes": 2,
        "triceps": 1.5,
    }


# --- Vercel first, then the Mac worker ---------------------------------------------------------


class FakeSupabase:
    def __init__(self, active=False, generating=False):
        self.active = active
        self.generating = generating
        self.saved = []
        self.queued = []

    async def select(self, table, params, token):
        if table == "workout_plans":
            if self.saved or self.active:
                status = "active" if self.active else self.saved[-1]["p_status"]
                return [
                    {
                        "id": "plan",
                        "week_start": "2026-10-19",
                        "status": status,
                        "rationale": None,
                        "made_by": None,
                        "reason": None,
                        "created_at": "2026-10-19T08:00:00Z",
                        "workout_sessions": [],
                    }
                ]
            return []
        if table == "jobs":
            return [{"id": "j"}] if self.generating or self.queued else []
        if table == "profiles":
            return [
                {
                    "sex": "female",
                    "date_of_birth": "1992-01-01",
                    "goals": ["build_muscle"],
                    "injuries_notes": None,
                }
            ]
        if table == "training_preferences":
            return [
                {
                    "equipment": ["dumbbells"],
                    "available_days": ["mon", "wed"],
                    "minutes_per_session": 40,
                    "location": "home",
                    "experience": None,
                }
            ]
        if table == "exercises":
            return LIBRARY
        raise AssertionError(table)

    async def rpc(self, function, args, token=None):
        assert function == "save_workout_plan"
        self.saved.append(args)
        return "plan"

    async def insert(self, table, values, token, returning="*"):
        self.queued.append(values)
        return [{"id": "j", "status": "pending", "attempts": 0, **values}]


def generate_with(supabase, http_handler, llm=GROQ, reason="requested"):
    async def go():
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(http_handler)) as http:
            return await plans.generate(supabase, http, llm, "t", "p1", date(2026, 10, 19), reason)

    return run(go())


def answer_for_whatever(request):
    prompt = json.loads(request.content)["messages"][1]["content"]
    ids = [
        line.split(":")[0].strip("- ").strip()
        for line in prompt.splitlines()
        if line.startswith("  - ")
    ]
    days = sorted({line[:10] for line in prompt.splitlines() if line[:4] == "2026"})
    week = {
        "rationale": "Two full-body days.",
        "sessions": [
            {
                "day": d,
                "title": "Full body",
                "explanation": "Whole-body strength work.",
                "main": [
                    {"exercise_id": i, "sets": 3, "reps_min": 8, "reps_max": 12, "rest_seconds": 90}
                    for i in ids[:3]
                ],
            }
            for d in days
        ],
    }
    return httpx2.Response(200, json={"choices": [{"message": {"content": json.dumps(week)}}]})


def test_first_plan_of_the_week_is_made_straight_away_and_active():
    supabase = FakeSupabase()
    week = generate_with(supabase, answer_for_whatever)
    [saved] = supabase.saved
    assert saved["p_status"] == "active" and saved["p_plan"]["made_by"] == "groq:qwen/test"
    assert week.active is not None and not supabase.queued


def test_a_new_plan_when_one_exists_is_a_draft_to_preview():
    supabase = FakeSupabase(active=True)
    generate_with(supabase, answer_for_whatever)
    assert supabase.saved[0]["p_status"] == "draft"


def test_new_week_does_nothing_if_the_week_has_a_plan_or_one_is_coming():
    for supabase in (FakeSupabase(active=True), FakeSupabase(generating=True)):
        generate_with(supabase, answer_for_whatever, reason="new_week")
        assert not supabase.saved and not supabase.queued


def test_slow_or_failing_llm_hands_the_plan_to_the_mac_worker():
    supabase = FakeSupabase()
    week = generate_with(supabase, lambda r: httpx2.Response(503))
    assert not supabase.saved
    [job] = supabase.queued
    assert job["type"] == "generate_workout_plan"
    assert job["payload"]["status"] == "active" and job["payload"]["week_start"] == "2026-10-19"
    assert week.generating
    no_key = FakeSupabase()
    generate_with(no_key, answer_for_whatever, llm=LlmConfig(None, "x", None, ""))
    assert no_key.queued and not no_key.saved


# --- The Mac worker's job -----------------------------------------------------------------


def test_worker_job_makes_and_saves_the_plan_even_without_an_llm():
    from core.jobs import JobContext, workout_plan

    class FakeWorkerDb:
        def __init__(self):
            self.saved = None

        async def select(self, table, params):
            return run_fake(table)

        async def rpc(self, function, args):
            self.saved = (function, args)
            return "new-plan"

    def run_fake(table):
        return {
            "workout_plans": [],
            "profiles": [
                {
                    "sex": "male",
                    "date_of_birth": "1990-05-01",
                    "goals": ["get_stronger"],
                    "injuries_notes": None,
                }
            ],
            "training_preferences": [
                {
                    "equipment": ["dumbbells"],
                    "available_days": ["tue", "thu"],
                    "minutes_per_session": 50,
                    "location": "home",
                    "experience": "advanced",
                }
            ],
            "exercises": LIBRARY,
        }[table]

    db = FakeWorkerDb()
    ctx = JobContext("mac", 1, None, db=db, llm=None)  # type: ignore[arg-type]
    payload = {
        "profile_id": "p1",
        "week_start": "2026-10-19",
        "today": "2026-10-19",
        "status": "active",
        "reason": "new_week",
    }
    result = run(workout_plan.run(payload, ctx))
    function, args = db.saved
    assert function == "save_workout_plan" and args["p_status"] == "active"
    assert result == {"plan_id": "new-plan", "status": "active", "made_by": "rules", "sessions": 2}
    main = [i for i in args["p_plan"]["sessions"][0]["items"] if i["phase"] == "main"]
    assert main[0]["reps_max"] == 6  # get_stronger, advanced


def test_a_plan_made_meanwhile_is_never_silently_replaced():
    from core.workouts.inputs import status_to_save

    async def with_active(table, params):
        return [{"id": "existing"}]

    async def without(table, params):
        return []

    monday = date(2026, 10, 19)
    assert run(status_to_save(without, "p1", monday, "active", "new_week")) == "active"
    # Another request (a page reload, the worker) made one meanwhile:
    assert run(status_to_save(with_active, "p1", monday, "active", "new_week")) is None
    assert run(status_to_save(with_active, "p1", monday, "active", "requested")) == "draft"
