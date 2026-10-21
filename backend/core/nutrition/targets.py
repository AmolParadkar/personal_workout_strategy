"""Daily targets with a one-line reason each: calories from body size, everyday
activity and training (from the workout plan), adjusted for the person's goals;
protein from body weight; fat as a share of calories; carbs the rest; fibre and
micronutrients from the recommended daily amounts (US Dietary Reference Intakes).
Spec: context/pages/nutrition-plan.md ("Daily targets with the reasoning")."""

from dataclasses import dataclass, field

# Extra energy per minute of training, per kg of body weight: about 5 METs of work
# (a mixed strength and cardio session) minus the 1 MET already counted at rest.
TRAINING_KCAL_PER_KG_MIN = 4 / 60
FAT_SHARE = 0.27
MIN_FAT_G_PER_KG = 0.6
MIN_CARBS_G = 80
FIBRE_G_PER_1000_KCAL = 14
# Never plan below these, whatever the goal.
KCAL_FLOOR = {"male": 1500, "female": 1200}
KCAL_FLOOR_OTHER = 1350


@dataclass(frozen=True)
class Body:
    weight_kg: float
    height_cm: float
    age: int
    sex: str | None
    goals: list[str] = field(default_factory=list)
    # Average daily steps over the last two weeks, if known.
    avg_steps: int | None = None


@dataclass
class Targets:
    kcal: int
    protein_g: int
    carbs_g: int
    fat_g: int
    fibre_g: int
    micros: dict[str, float]
    reasons: dict[str, str]
    training_minutes: int = 0

    def as_json(self) -> dict:
        return {
            "kcal": self.kcal,
            "protein_g": self.protein_g,
            "carbs_g": self.carbs_g,
            "fat_g": self.fat_g,
            "fibre_g": self.fibre_g,
            "micros": self.micros,
            "reasons": self.reasons,
            "training_minutes": self.training_minutes,
        }


def bmr(body: Body) -> float:
    """Resting energy (Mifflin-St Jeor)."""
    base = 10 * body.weight_kg + 6.25 * body.height_cm - 5 * body.age
    return base + {"male": 5, "female": -161}.get(body.sex or "", -78)


def activity(avg_steps: int | None) -> tuple[float, str]:
    if avg_steps is None:
        return 1.3, "light everyday activity; no step counts yet"
    if avg_steps < 5000:
        return 1.25, f"about {avg_steps:,} steps a day"
    if avg_steps < 7500:
        return 1.35, f"about {avg_steps:,} steps a day"
    if avg_steps < 10000:
        return 1.45, f"about {avg_steps:,} steps a day"
    return 1.55, f"about {avg_steps:,} steps a day"


def goal_adjustment(goals: list[str], maintenance: float) -> tuple[float, str]:
    """Calories to add (negative: take away) for the goals, and why."""
    lose, build = "lose_fat" in goals, "build_muscle" in goals
    if lose and build:
        return -0.10 * maintenance, "minus 10% to lose fat slowly while building muscle"
    if lose:
        cut = min(0.20 * maintenance, 600)
        return -cut, f"minus {round(cut, -1):.0f} to lose fat (about 0.5 kg a week)"
    if build:
        extra = min(0.10 * maintenance, 300)
        return extra, f"plus {round(extra, -1):.0f} to build muscle"
    return 0.0, "kept at maintenance for your goals"


def protein_per_kg(goals: list[str]) -> tuple[float, str]:
    if {"build_muscle", "lose_fat", "get_stronger"} & set(goals):
        # Around 1.6 g/kg is where extra protein stops adding muscle (Morton et al., 2018).
        why = (
            "to keep muscle while losing fat"
            if "lose_fat" in goals and "build_muscle" not in goals
            else "to build and keep muscle"
        )
        return 1.6, why
    if "endurance" in goals:
        return 1.4, "for recovery from endurance training"
    return 1.2, "for general health"


def micronutrients(sex: str | None, age: int) -> dict[str, float]:
    male, female = sex == "male", sex == "female"

    def pick(m: float, f: float) -> float:
        return m if male else f if female else round((m + f) / 2)

    return {
        "iron_mg": 8 if male or (female and age > 50) else (18 if female else 13),
        "calcium_mg": 1200 if (female and age > 50) or (male and age > 70) else 1000,
        "magnesium_mg": pick(400 if age <= 30 else 420, 310 if age <= 30 else 320),
        "potassium_mg": pick(3400, 2600),
        "zinc_mg": pick(11, 8),
        "vitamin_c_mg": pick(90, 75),
        "vitamin_d_ug": 20 if age > 70 else 15,
        "vitamin_a_ug": pick(900, 700),
        "folate_ug": 400,
        "sodium_mg_max": 2300,
    }


def daily_targets(body: Body, training_minutes: int = 0) -> Targets:
    resting = bmr(body)
    factor, activity_note = activity(body.avg_steps)
    maintenance = resting * factor
    training = round(TRAINING_KCAL_PER_KG_MIN * body.weight_kg * training_minutes, -1)
    adjust, goal_note = goal_adjustment(body.goals, maintenance + training)
    floor = KCAL_FLOOR.get(body.sex or "", KCAL_FLOOR_OTHER)
    kcal = max(maintenance + training + adjust, floor, resting)
    kcal = int(round(kcal, -1))

    # Protein from body weight; above a BMI of 30, from the weight at a BMI of 27,
    # so the target stays reachable.
    per_kg, protein_note = protein_per_kg(body.goals)
    reference = min(body.weight_kg, 27 * (body.height_cm / 100) ** 2)
    protein = round(per_kg * reference)
    fat = round(max(FAT_SHARE * kcal / 9, MIN_FAT_G_PER_KG * body.weight_kg))
    carbs = round(max((kcal - 4 * protein - 9 * fat) / 4, MIN_CARBS_G))
    fibre = round(FIBRE_G_PER_1000_KCAL * kcal / 1000)

    session = (
        f" plus {training:.0f} for today's {training_minutes}-minute session"
        if training_minutes
        else " (a rest day)"
    )
    reasons = {
        "kcal": (
            f"About {round(maintenance, -1):,.0f} to maintain your weight ({activity_note})"
            f"{session}, {goal_note}." + (" Kept at a safe minimum." if kcal == floor else "")
        ),
        "protein_g": f"{per_kg:g} g per kg of body weight ({reference:.0f} kg) {protein_note}.",
        "fat_g": "About a quarter of your calories, for hormones and vitamin absorption.",
        "carbs_g": (
            "The rest of your calories after protein and fat"
            + ("; more on training days to fuel the session." if training_minutes else ".")
        ),
        "fibre_g": f"{FIBRE_G_PER_1000_KCAL} g per 1,000 kcal, for digestion and fullness.",
        "micros": (
            "Recommended daily amounts for your age and sex (US Dietary Reference "
            "Intakes); sodium is an upper limit."
        ),
    }
    return Targets(
        kcal=kcal,
        protein_g=protein,
        carbs_g=carbs,
        fat_g=fat,
        fibre_g=fibre,
        micros=micronutrients(body.sex, body.age),
        reasons=reasons,
        training_minutes=training_minutes,
    )
