from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Response of the health-check endpoint, used to confirm the API is up."""

    status: Literal["ok"]
    version: str
