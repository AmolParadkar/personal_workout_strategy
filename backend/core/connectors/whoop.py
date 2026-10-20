"""Whoop (band): recovery, strain, sleep.

API reference: https://developer.whoop.com/api/
Needs the `offline` scope to get a refresh key; access keys last about an hour.
"""

from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import httpx2

from core.connectors.base import (
    Sample,
    ServiceAuthError,
    Tokens,
    check_response,
    expires_in,
    keep,
    number,
    offset_zone,
    parse_time,
    time_sample,
    value_sample,
)

API = "https://api.prod.whoop.com"
TOKEN_URL = f"{API}/oauth/oauth2/token"


class WhoopConnector:
    service = "whoop"
    label = "Whoop"
    authorize_url = f"{API}/oauth/oauth2/auth"
    scopes = "offline read:recovery read:cycles read:sleep"

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
                "scope": "offline",
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
        # A day either side, in UTC: the local day comes from each record's offset.
        params = {
            "start": datetime.combine(start - timedelta(days=1), time(), UTC).isoformat(),
            "end": datetime.combine(end + timedelta(days=2), time(), UTC).isoformat(),
        }
        token = tokens.access_token
        sleeps = await _pages(http, token, "/developer/v2/activity/sleep", params)
        recoveries = await _pages(http, token, "/developer/v2/recovery", params)
        cycles = await _pages(http, token, "/developer/v2/cycle", params)
        # Whoop's body weight is a typed-in profile value, not a weigh-in: not fetched.
        samples = [
            *sleep_samples(sleeps),
            *recovery_samples(recoveries, sleeps),
            *cycle_samples(cycles),
        ]
        return [s for s in samples if start.isoformat() <= s["date"] <= end.isoformat()]

    async def revoke(
        self, http: httpx2.AsyncClient, client: tuple[str, str], tokens: Tokens
    ) -> None:
        await http.delete(
            f"{API}/developer/v2/user/access",
            headers={"Authorization": f"Bearer {tokens.access_token}"},
        )


async def _pages(
    http: httpx2.AsyncClient, token: str, path: str, params: dict[str, str]
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    next_token = None
    for _ in range(40):
        query = {**params, "limit": "25", **({"nextToken": next_token} if next_token else {})}
        body = check_response(
            await http.get(
                f"{API}{path}", params=query, headers={"Authorization": f"Bearer {token}"}
            )
        )
        records.extend(body.get("records") or [])
        next_token = body.get("next_token")
        if not next_token:
            break
    return records


def _local(record: dict[str, Any], field: str) -> datetime | None:
    moment = parse_time(record.get(field))
    return moment.astimezone(offset_zone(record.get("timezone_offset"))) if moment else None


def _wake_day(sleep: dict[str, Any]) -> str | None:
    woke = _local(sleep, "end")
    return woke.date().isoformat() if woke else None


def _main_sleeps(sleeps: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Scored, non-nap sleeps by wake-up day (the longest if several)."""
    nights: dict[str, dict[str, Any]] = {}
    for sleep in sleeps:
        day = _wake_day(sleep)
        if sleep.get("nap") or sleep.get("score_state") != "SCORED" or day is None:
            continue
        in_bed = ((sleep.get("score") or {}).get("stage_summary") or {}).get(
            "total_in_bed_time_milli"
        ) or 0
        current = ((nights.get(day) or {}).get("score") or {}).get("stage_summary") or {}
        if day not in nights or in_bed > (current.get("total_in_bed_time_milli") or 0):
            nights[day] = sleep
    return nights


def _ms_to_minutes(value: Any) -> float | None:
    ms = number(value)
    return round(ms / 60_000) if ms is not None else None


def sleep_samples(sleeps: list[dict[str, Any]]) -> list[Sample]:
    samples: list[Sample] = []
    for day, sleep in _main_sleeps(sleeps).items():
        stages = (sleep.get("score") or {}).get("stage_summary") or {}
        in_bed = number(stages.get("total_in_bed_time_milli"))
        awake = number(stages.get("total_awake_time_milli")) or 0
        samples += keep(
            time_sample("bedtime", day, _local(sleep, "start")),
            time_sample("wake_time", day, _local(sleep, "end")),
            value_sample("sleep_in_bed_minutes", day, _ms_to_minutes(in_bed)),
            value_sample(
                "sleep_asleep_minutes", day, _ms_to_minutes(in_bed - awake) if in_bed else None
            ),
            value_sample(
                "sleep_deep_minutes",
                day,
                _ms_to_minutes(stages.get("total_slow_wave_sleep_time_milli")),
            ),
            value_sample(
                "sleep_rem_minutes", day, _ms_to_minutes(stages.get("total_rem_sleep_time_milli"))
            ),
            value_sample(
                "sleep_light_minutes",
                day,
                _ms_to_minutes(stages.get("total_light_sleep_time_milli")),
            ),
        )
    return samples


def recovery_samples(
    recoveries: list[dict[str, Any]], sleeps: list[dict[str, Any]]
) -> list[Sample]:
    """Recovery belongs to the morning of the sleep it was measured in."""
    wake_days = {sleep.get("id"): _wake_day(sleep) for sleep in sleeps}
    samples: list[Sample] = []
    for recovery in recoveries:
        day = wake_days.get(recovery.get("sleep_id"))
        if recovery.get("score_state") != "SCORED" or day is None:
            continue
        score = recovery.get("score") or {}
        samples += keep(
            value_sample("recovery_score", day, number(score.get("recovery_score"))),
            value_sample("resting_hr", day, number(score.get("resting_heart_rate"))),
            value_sample("hrv_ms", day, number(score.get("hrv_rmssd_milli"))),
        )
    return samples


def cycle_samples(cycles: list[dict[str, Any]]) -> list[Sample]:
    """A cycle runs from waking to the next sleep; its strain belongs to the day it started."""
    samples: list[Sample] = []
    for cycle in cycles:
        started = _local(cycle, "start")
        if cycle.get("score_state") != "SCORED" or started is None:
            continue
        day = started.date().isoformat()
        samples += keep(
            value_sample("strain", day, number((cycle.get("score") or {}).get("strain"))),
            value_sample("steps", day, number(cycle.get("step_count"))),
        )
    return samples
