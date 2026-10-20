from datetime import date

import pytest
from pydantic import ValidationError

from core.models.settings import (
    DietPreferencesUpdate,
    ProfileDetailsUpdate,
    TrainingPreferencesUpdate,
)
from core.settings import missing_for_onboarding, to_profile_settings

OWN_USER_ID = "user-amol"


def settings_row(**profile_overrides):
    """A profile row as Supabase returns it, with its three settings rows embedded."""
    row = {
        "id": "profile-amol",
        "user_id": OWN_USER_ID,
        "display_name": "Amol",
        "date_of_birth": "1990-05-01",
        "sex": "male",
        "height_cm": 178.0,
        "goals": ["lose_fat", "get_stronger"],
        "goals_notes": None,
        "goal_metric": "body_fat",
        "injuries_notes": None,
        "onboarded_at": None,
        "training_preferences": {
            "equipment": ["dumbbells"],
            "available_days": ["mon", "wed", "fri"],
            "minutes_per_session": 60,
            "location": "gym",
        },
        "diet_preferences": {
            "diet_type": "eggetarian",
            "cuisines": ["Indian"],
            "allergies": [],
            "dislikes": [],
            "meals_per_day": 4,
            "cooking_minutes": 30,
        },
        "display_settings": {
            "show_weight": False,
            "show_calorie_intake": False,
            "show_calories_burned": False,
        },
    }
    row.update(profile_overrides)
    return row


def test_own_profile_is_editable_and_others_are_view_only():
    assert to_profile_settings(settings_row(), OWN_USER_ID).can_edit is True
    assert to_profile_settings(settings_row(), "someone-else").can_edit is False


def test_complete_profile_has_nothing_missing():
    assert missing_for_onboarding(to_profile_settings(settings_row(), OWN_USER_ID)) == []


def test_missing_required_fields_are_listed():
    row = settings_row(height_cm=None, goals=[])
    row["training_preferences"]["available_days"] = []
    missing = missing_for_onboarding(to_profile_settings(row, OWN_USER_ID))
    assert missing == ["height_cm", "goals", "available_days"]


def test_optional_fields_are_not_required():
    row = settings_row(injuries_notes=None, goals_notes=None)
    row["training_preferences"]["equipment"] = []
    row["diet_preferences"]["cooking_minutes"] = None
    assert missing_for_onboarding(to_profile_settings(row, OWN_USER_ID)) == []


def test_days_are_deduplicated_and_put_in_week_order():
    update = TrainingPreferencesUpdate(available_days=["fri", "mon", "fri", "wed"])
    assert update.available_days == ["mon", "wed", "fri"]


def test_tags_are_trimmed_and_deduplicated():
    update = DietPreferencesUpdate(allergies=[" peanuts ", "peanuts", "", "shellfish"])
    assert update.allergies == ["peanuts", "shellfish"]


@pytest.mark.parametrize(
    "changes",
    [
        {"height_cm": 300},
        {"display_name": ""},
        {"goals": ["become_famous"]},
        {"date_of_birth": date.today().isoformat()},
    ],
)
def test_invalid_profile_values_are_rejected(changes):
    with pytest.raises(ValidationError):
        ProfileDetailsUpdate(**changes)


def test_invalid_training_values_are_rejected():
    with pytest.raises(ValidationError):
        TrainingPreferencesUpdate(available_days=["someday"])
    with pytest.raises(ValidationError):
        TrainingPreferencesUpdate(minutes_per_session=1)


def test_only_fields_sent_are_changed():
    update = ProfileDetailsUpdate(height_cm=180)
    assert update.model_dump(exclude_unset=True) == {"height_cm": 180}
