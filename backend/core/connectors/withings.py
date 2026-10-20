"""Withings (scales, blood pressure monitors, sleep analysers).

API reference: https://developer.withings.com/api-reference/
Every reply is HTTP 200 with a `status` field: 0 means success.
"""

from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import httpx2

from core.connectors.base import (
    Sample,
    ServiceAuthError,
    ServiceError,
    Tokens,
    expires_in,
    keep,
    minutes,
    number,
    time_sample,
    value_sample,
    zone,
)

API = "https://wbsapi.withings.net"
AUTH_FAILED = {100, 101, 102, 200, 401}

# Withings measure type → our metric.
MEASURE_TYPES = {
    1: "weight_kg",
    6: "body_fat_pct",
    9: "diastolic_mmhg",
    10: "systolic_mmhg",
    76: "muscle_mass_kg",
}


class WithingsConnector:
    service = "withings"
    label = "Withings"
    authorize_url = "https://account.withings.com/oauth2_user/authorize2"
    scopes = "user.info,user.metrics,user.activity"

    def authorize_params(self, client_id: str, redirect_uri: str, state: str) -> dict[str, str]:
        return {
            "response_type": "code",
            "client_id": client_id,
            "scope": self.scopes,
            "redirect_uri": redirect_uri,
            "state": state,
        }

    async def exchange_code(
        self, http: httpx2.AsyncClient, client: tuple[str, str], code: str, redirect_uri: str
    ) -> Tokens:
        return await self._token(
            http,
            {
                "grant_type": "authorization_code",
                "client_id": client[0],
                "client_secret": client[1],
                "code": code,
                "redirect_uri": redirect_uri,
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
                "client_id": client[0],
                "client_secret": client[1],
                "refresh_token": tokens.refresh_token,
            },
        )

    async def _token(self, http: httpx2.AsyncClient, data: dict[str, str]) -> Tokens:
        body = await _call(http, None, "v2/oauth2", {"action": "requesttoken", **data})
        return Tokens(
            access_token=body["access_token"],
            refresh_token=body.get("refresh_token"),
            expires_at=expires_in(body.get("expires_in")),
            external_user_id=str(body["userid"]) if body.get("userid") else None,
            scopes=body.get("scope"),
        )

    async def fetch(
        self, http: httpx2.AsyncClient, tokens: Tokens, start: date, end: date
    ) -> list[Sample]:
        token = tokens.access_token
        measures = await _pages(
            http,
            token,
            "measure",
            {
                "action": "getmeas",
                "meastypes": ",".join(str(t) for t in MEASURE_TYPES),
                "category": "1",  # real measurements, not goals
                # A day either side: the local day isn't known until the reply's timezone.
                "startdate": str(_unix(start - timedelta(days=1))),
                "enddate": str(_unix(end + timedelta(days=2))),
            },
            "measuregrps",
        )
        activities = await _pages(
            http,
            token,
            "v2/measure",
            {
                "action": "getactivity",
                "startdateymd": start.isoformat(),
                "enddateymd": end.isoformat(),
                "data_fields": "steps,distance,calories",
            },
            "activities",
        )
        sleeps = await _pages(
            http,
            token,
            "v2/sleep",
            {
                "action": "getsummary",
                "startdateymd": (start - timedelta(days=1)).isoformat(),
                "enddateymd": end.isoformat(),
                "data_fields": "total_timeinbed,total_sleep_time,deepsleepduration,"
                "remsleepduration,lightsleepduration,sleep_score",
            },
            "series",
        )
        samples = [
            *measure_samples(measures),
            *activity_samples(activities),
            *sleep_samples(sleeps),
        ]
        return [s for s in samples if start.isoformat() <= s["date"] <= end.isoformat()]

    async def revoke(
        self, http: httpx2.AsyncClient, client: tuple[str, str], tokens: Tokens
    ) -> None:
        # Withings' revoke needs request signing; the person can also remove
        # access in the Withings app. Deleting our copy of the keys is enough.
        return None


def _unix(day: date) -> int:
    return int(datetime.combine(day, time(), UTC).timestamp())


async def _call(
    http: httpx2.AsyncClient, token: str | None, path: str, data: dict[str, str]
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = await http.post(f"{API}/{path}", data=data, headers=headers)
    if response.status_code >= 500:
        raise ServiceError(f"HTTP {response.status_code}")
    try:
        reply = response.json()
    except ValueError as error:
        raise ServiceError("Not JSON") from error
    status = reply.get("status")
    if status in AUTH_FAILED:
        raise ServiceAuthError(f"status {status}")
    if status != 0:
        raise ServiceError(f"status {status}")
    return reply.get("body") or {}


async def _pages(
    http: httpx2.AsyncClient, token: str, path: str, data: dict[str, str], key: str
) -> dict[str, Any]:
    """Follow Withings' `more` / `offset` paging; returns the merged body."""
    merged: dict[str, Any] = {key: []}
    offset = None
    for _ in range(20):
        body = await _call(http, token, path, {**data, **({"offset": offset} if offset else {})})
        merged[key].extend(body.get(key) or [])
        merged.setdefault("timezone", body.get("timezone"))
        if not body.get("more") or not body.get("offset"):
            break
        offset = str(body["offset"])
    return merged


def measure_samples(body: dict[str, Any]) -> list[Sample]:
    """Weigh-ins and blood pressure: the latest reading of each type per local day."""
    tz = zone(body.get("timezone"))
    latest: dict[tuple[str, str], tuple[datetime, float]] = {}
    for group in body.get("measuregrps", []):
        taken = datetime.fromtimestamp(group["date"], UTC).astimezone(tz)
        for measure in group.get("measures", []):
            metric = MEASURE_TYPES.get(measure.get("type"))
            if metric is None:
                continue
            value = round(measure["value"] * 10 ** measure["unit"], 2)
            key = (metric, taken.date().isoformat())
            if key not in latest or taken > latest[key][0]:
                latest[key] = (taken, value)
    return [
        {"metric": metric, "date": day, "value": value, "at": taken.isoformat()}
        for (metric, day), (taken, value) in latest.items()
    ]


def activity_samples(body: dict[str, Any]) -> list[Sample]:
    samples: list[Sample] = []
    for day in body.get("activities", []):
        distance = number(day.get("distance"))
        samples += keep(
            value_sample("steps", day["date"], number(day.get("steps"))),
            value_sample("active_energy_kcal", day["date"], number(day.get("calories"))),
            value_sample(
                "walking_running_km", day["date"], round(distance / 1000, 2) if distance else None
            ),
        )
    return samples


def sleep_samples(body: dict[str, Any]) -> list[Sample]:
    """The main night per wake-up day (the longest, if there were naps)."""
    nights: dict[str, dict[str, Any]] = {}
    for night in body.get("series", []):
        tz = zone(night.get("timezone") or body.get("timezone"))
        woke = datetime.fromtimestamp(night["enddate"], UTC).astimezone(tz)
        day = woke.date().isoformat()
        in_bed = number((night.get("data") or {}).get("total_timeinbed")) or 0
        if day not in nights or in_bed > nights[day]["in_bed"]:
            nights[day] = {"night": night, "tz": tz, "in_bed": in_bed}
    samples: list[Sample] = []
    for day, chosen in nights.items():
        night, tz = chosen["night"], chosen["tz"]
        data = night.get("data") or {}
        samples += keep(
            time_sample(
                "bedtime", day, datetime.fromtimestamp(night["startdate"], UTC).astimezone(tz)
            ),
            time_sample(
                "wake_time", day, datetime.fromtimestamp(night["enddate"], UTC).astimezone(tz)
            ),
            value_sample("sleep_in_bed_minutes", day, minutes(data.get("total_timeinbed"))),
            value_sample("sleep_asleep_minutes", day, minutes(data.get("total_sleep_time"))),
            value_sample("sleep_deep_minutes", day, minutes(data.get("deepsleepduration"))),
            value_sample("sleep_rem_minutes", day, minutes(data.get("remsleepduration"))),
            value_sample("sleep_light_minutes", day, minutes(data.get("lightsleepduration"))),
            value_sample("sleep_score", day, number(data.get("sleep_score"))),
        )
    return samples
