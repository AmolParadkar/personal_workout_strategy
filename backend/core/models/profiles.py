from pydantic import BaseModel


class ProfileSummary(BaseModel):
    """One person in the household, as shown in the profile dropdown."""

    id: str
    display_name: str
    # True for the signed-in person's own profile; the other profile is view-only.
    is_own: bool


class HouseholdProfiles(BaseModel):
    """Everyone in the signed-in person's household, own profile first."""

    profiles: list[ProfileSummary]
