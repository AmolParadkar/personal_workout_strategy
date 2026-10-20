from fastapi import APIRouter, HTTPException, status

from api.deps import CurrentUserDep, SupabaseDep
from core import settings as settings_service
from core.models.settings import (
    DietPreferencesUpdate,
    DisplaySettingsUpdate,
    ProfileDetailsUpdate,
    ProfileSettings,
    TrainingPreferencesUpdate,
)

router = APIRouter(prefix="/api", tags=["settings"])


@router.get("/profiles/{profile_id}/settings")
async def profile_settings(
    profile_id: str, user: CurrentUserDep, supabase: SupabaseDep
) -> ProfileSettings:
    """Settings for any profile in the household; `can_edit` is true only for your own."""
    try:
        return await settings_service.get_profile_settings(
            supabase, user.access_token, user.id, profile_id
        )
    except settings_service.ProfileNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Profile not found") from error


@router.patch("/me/settings/profile")
async def update_profile(
    changes: ProfileDetailsUpdate, user: CurrentUserDep, supabase: SupabaseDep
) -> ProfileSettings:
    return await settings_service.update_own_section(
        supabase, user.access_token, user.id, "profile", changes
    )


@router.patch("/me/settings/training")
async def update_training(
    changes: TrainingPreferencesUpdate, user: CurrentUserDep, supabase: SupabaseDep
) -> ProfileSettings:
    return await settings_service.update_own_section(
        supabase, user.access_token, user.id, "training", changes
    )


@router.patch("/me/settings/diet")
async def update_diet(
    changes: DietPreferencesUpdate, user: CurrentUserDep, supabase: SupabaseDep
) -> ProfileSettings:
    return await settings_service.update_own_section(
        supabase, user.access_token, user.id, "diet", changes
    )


@router.patch("/me/settings/display")
async def update_display(
    changes: DisplaySettingsUpdate, user: CurrentUserDep, supabase: SupabaseDep
) -> ProfileSettings:
    return await settings_service.update_own_section(
        supabase, user.access_token, user.id, "display", changes
    )


@router.post("/me/onboarding/complete")
async def complete_onboarding(user: CurrentUserDep, supabase: SupabaseDep) -> ProfileSettings:
    """Mark the first-sign-in questions as done; refused until required fields are filled."""
    try:
        return await settings_service.complete_onboarding(supabase, user.access_token, user.id)
    except settings_service.OnboardingIncompleteError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            {"message": "Some required details are missing", "missing": error.missing},
        ) from error
