"""Polar (watches): daily activity, sleep, overnight HRV.

API reference: https://www.polar.com/accesslink-api/
Access keys last about a year and there's no refresh: the person reconnects
when one expires. A new user must be registered once before data can be read.
Daily data only goes back 28 days.
"""

import base64
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

API = "https://www.polaraccesslink.com/v3"
TOKEN_URL = "https://polarremote.com/v2/oauth2/token"
MAX_DAYS = 28


class PolarConnector:
    service = "polar"
    label = "Polar"
    authorize_url = "https://flow.polar.com/oauth2/authorization"
    scopes = "accesslink.read_all"

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
        basic = base64.b64encode(f"{client[0]}:{client[1]}".encode()).decode()
        body = check_response(
            await http.post(
                TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
                headers={"Authorization": f"Basic {basic}", "Accept": "application/json"},
            )
        )
        user_id = str(body["x_user_id"])
        # Register the person with our Polar app (409 = already registered).
        response = await http.post(
            f"{API}/users",
            json={"member-id": user_id},
            headers={"Authorization": f"Bearer {body['access_token']}"},
        )
        if response.status_code != 409:
            check_response(response)
        return Tokens(
            access_token=body["access_token"],
            refresh_token=None,
            expires_at=expires_in(body.get("expires_in")),
            external_user_id=user_id,
            scopes=self.scopes,
        )

    async def refresh(
        self, http: httpx2.AsyncClient, client: tuple[str, str], tokens: Tokens
    ) -> Tokens:
        raise ServiceAuthError("Polar keys can't be refreshed")

    async def fetch(
        self, http: httpx2.AsyncClient, tokens: Tokens, start: date, end: date
    ) -> list[Sample]:
        start = max(start, end - timedelta(days=MAX_DAYS - 1))
        headers = {"Authorization": f"Bearer {tokens.access_token}", "Accept": "application/json"}
        activities = check_response(
            await http.get(
                f"{API}/users/activities",
                params={"from": start.isoformat(), "to": end.isoformat()},
                headers=headers,
            )
        )
        nights = check_response(await http.get(f"{API}/users/sleep", headers=headers))
        recharges = check_response(await http.get(f"{API}/users/nightly-recharge", headers=headers))
        samples = [
            *activity_samples(activities),
            *sleep_samples(nights.get("nights") or []),
            *recharge_samples(recharges.get("recharges") or []),
        ]
        return [s for s in samples if start.isoformat() <= s["date"] <= end.isoformat()]

    async def revoke(
        self, http: httpx2.AsyncClient, client: tuple[str, str], tokens: Tokens
    ) -> None:
        if tokens.external_user_id:
            await http.delete(
                f"{API}/users/{tokens.external_user_id}",
                headers={"Authorization": f"Bearer {tokens.access_token}"},
            )


def activity_samples(body: Any) -> list[Sample]:
    days = body if isinstance(body, list) else (body.get("activities") or [])
    samples: list[Sample] = []
    for day in days:
        on = (day.get("start_time") or day.get("date") or "")[:10]
        if not on:
            continue
        distance = number(day.get("distance_from_steps"))
        samples += keep(
            value_sample("steps", on, number(day.get("steps"))),
            value_sample("active_energy_kcal", on, number(day.get("active_calories"))),
            value_sample("walking_running_km", on, round(distance / 1000, 2) if distance else None),
        )
    return samples


def sleep_samples(nights: list[dict[str, Any]]) -> list[Sample]:
    samples: list[Sample] = []
    for night in nights:
        day = night.get("date")
        start = parse_time(night.get("sleep_start_time"))
        end = parse_time(night.get("sleep_end_time"))
        if not day:
            continue
        stages = [number(night.get(k)) for k in ("light_sleep", "deep_sleep", "rem_sleep")]
        asleep = (
            sum(s for s in stages if s is not None) if any(s is not None for s in stages) else None
        )
        samples += keep(
            time_sample("bedtime", day, start),
            time_sample("wake_time", day, end),
            value_sample(
                "sleep_in_bed_minutes",
                day,
                round((end - start).total_seconds() / 60) if start and end else None,
            ),
            value_sample("sleep_asleep_minutes", day, minutes(asleep)),
            value_sample("sleep_deep_minutes", day, minutes(night.get("deep_sleep"))),
            value_sample("sleep_rem_minutes", day, minutes(night.get("rem_sleep"))),
            value_sample("sleep_light_minutes", day, minutes(night.get("light_sleep"))),
            value_sample("sleep_score", day, number(night.get("sleep_score"))),
        )
    return samples


def recharge_samples(recharges: list[dict[str, Any]]) -> list[Sample]:
    return keep(
        *(
            value_sample("hrv_ms", r["date"], number(r.get("heart_rate_variability_avg")))
            for r in recharges
            if r.get("date")
        )
    )
