"""Oura (ring): activity, sleep, readiness.

API reference: https://cloud.ouraring.com/v2/docs
Refresh keys are single-use: the new one must be saved after every refresh.
"""

from datetime import date, timedelta
from typing import Any

import httpx2

from core.connectors.base import (
    Sample,
    ServiceAuthError,
    Tokens,
    check_response,
    expires_in,
    keep,
    minutes,
    number,
    parse_time,
    time_sample,
    value_sample,
)

API = "https://api.ouraring.com"
TOKEN_URL = f"{API}/oauth/token"


class OuraConnector:
    service = "oura"
    label = "Oura"
    authorize_url = "https://cloud.ouraring.com/oauth/authorize"
    scopes = "daily heartrate personal"

    def authorize_params(self, client_id: str, redirect_uri: str, state: str) -> dict[str, str]:
        return {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": self.scopes,
            "state": state,
        }

    async def exchange_code(
        self, http: httpx2.AsyncClient, client: tuple[str, str], code: str, redirect_uri: str
    ) -> Tokens:
        return await self._token(
            http,
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client[0],
                "client_secret": client[1],
            },
        )

    async def refresh(
        self, http: httpx2.AsyncClient, client: tuple[str, str], tokens: Tokens
    ) -> Tokens:
        if not tokens.refresh_token:
            raise ServiceAuthError("No refresh key")
        return await self._token(
            http,
            {
                "grant_type": "refresh_token",
                "refresh_token": tokens.refresh_token,
                "client_id": client[0],
                "client_secret": client[1],
            },
        )

    async def _token(self, http: httpx2.AsyncClient, data: dict[str, str]) -> Tokens:
        body = check_response(await http.post(TOKEN_URL, data=data))
        return Tokens(
            access_token=body["access_token"],
            refresh_token=body.get("refresh_token"),
            expires_at=expires_in(body.get("expires_in")),
            scopes=body.get("scope"),
        )

    async def fetch(
        self, http: httpx2.AsyncClient, tokens: Tokens, start: date, end: date
    ) -> list[Sample]:
        async def collection(name: str) -> list[dict[str, Any]]:
            # end_date is exclusive for some collections: ask for one more day.
            params = {
                "start_date": start.isoformat(),
                "end_date": (end + timedelta(days=1)).isoformat(),
            }
            return await _pages(http, tokens.access_token, f"/v2/usercollection/{name}", params)

        samples = [
            *activity_samples(await collection("daily_activity")),
            *score_samples(await collection("daily_readiness"), "readiness_score"),
            *score_samples(await collection("daily_sleep"), "sleep_score"),
            *sleep_samples(await collection("sleep")),
        ]
        return [s for s in samples if start.isoformat() <= s["date"] <= end.isoformat()]

    async def revoke(
        self, http: httpx2.AsyncClient, client: tuple[str, str], tokens: Tokens
    ) -> None:
        await http.get(f"{API}/oauth/revoke", params={"access_token": tokens.access_token})


async def _pages(
    http: httpx2.AsyncClient, token: str, path: str, params: dict[str, str]
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    next_token = None
    for _ in range(20):
        query = {**params, **({"next_token": next_token} if next_token else {})}
        body = check_response(
            await http.get(
                f"{API}{path}", params=query, headers={"Authorization": f"Bearer {token}"}
            )
        )
        records.extend(body.get("data") or [])
        next_token = body.get("next_token")
        if not next_token:
            break
    return records


def activity_samples(days: list[dict[str, Any]]) -> list[Sample]:
    samples: list[Sample] = []
    for day in days:
        samples += keep(
            value_sample("steps", day["day"], number(day.get("steps"))),
            value_sample("active_energy_kcal", day["day"], number(day.get("active_calories"))),
        )
    return samples


def score_samples(days: list[dict[str, Any]], metric: str) -> list[Sample]:
    return keep(*(value_sample(metric, day["day"], number(day.get("score"))) for day in days))


def sleep_samples(periods: list[dict[str, Any]]) -> list[Sample]:
    """The main sleep of each day (Oura's `long_sleep`; the longest if several)."""
    nights: dict[str, dict[str, Any]] = {}
    for period in periods:
        if period.get("type") != "long_sleep":
            continue
        day = period["day"]
        if day not in nights or (period.get("time_in_bed") or 0) > (
            nights[day].get("time_in_bed") or 0
        ):
            nights[day] = period
    samples: list[Sample] = []
    for day, night in nights.items():
        samples += keep(
            time_sample("bedtime", day, parse_time(night.get("bedtime_start"))),
            time_sample("wake_time", day, parse_time(night.get("bedtime_end"))),
            value_sample("sleep_in_bed_minutes", day, minutes(night.get("time_in_bed"))),
            value_sample("sleep_asleep_minutes", day, minutes(night.get("total_sleep_duration"))),
            value_sample("sleep_deep_minutes", day, minutes(night.get("deep_sleep_duration"))),
            value_sample("sleep_rem_minutes", day, minutes(night.get("rem_sleep_duration"))),
            value_sample("sleep_light_minutes", day, minutes(night.get("light_sleep_duration"))),
            value_sample("hrv_ms", day, number(night.get("average_hrv"))),
            value_sample("resting_hr", day, number(night.get("lowest_heart_rate"))),
        )
    return samples
