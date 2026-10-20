"""Direct connectors (core/connectors/, core/connections.py) without real services.

Each service's replies are shaped like its API docs; the real APIs are checked
once each developer app is set up (context/data-sources.md).
"""

import asyncio
from datetime import UTC, date, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import httpx2
import pytest
from cryptography.fernet import Fernet

from core import connections
from core.config import Settings
from core.connectors import CONNECTORS, oura, polar, preferred, whoop, withings
from core.connectors import keys as connector_keys
from core.connectors.base import ServiceAuthError, Tokens, sign_in_address

KEY = Fernet.generate_key().decode()
PROFILE = "11111111-1111-1111-1111-111111111111"


def settings(**overrides) -> Settings:
    values = {
        "supabase_url": "https://example.supabase.co",
        "supabase_publishable_key": "sb_publishable_test",
        "cors_origins": "https://site.example,http://localhost:8081",
        "connector_encryption_key": KEY,
        "withings_client_id": "wid",
        "withings_client_secret": "wsecret",
        "oura_client_id": "oid",
        "oura_client_secret": "osecret",
        **overrides,
    }
    return Settings(**values)


# --- Keys and state --------------------------------------------------------------


def test_keys_are_encrypted_and_only_our_key_decrypts_them():
    stored = connector_keys.encrypt(KEY, "access-123")
    assert "access-123" not in stored
    assert connector_keys.decrypt(KEY, stored) == "access-123"
    with pytest.raises(ValueError):
        connector_keys.decrypt(Fernet.generate_key().decode(), stored)


def test_state_is_tied_to_person_service_and_time():
    state = connector_keys.sign_state(KEY, PROFILE, "oura", now=1000)
    connector_keys.check_state(KEY, state, PROFILE, "oura", now=1000 + 60)
    for profile, service, now in [
        ("someone-else", "oura", 1060),  # someone else finishing my sign-in
        (PROFILE, "whoop", 1060),  # a different service
        (PROFILE, "oura", 1000 + 11 * 60),  # older than 10 minutes
    ]:
        with pytest.raises(connector_keys.InvalidStateError):
            connector_keys.check_state(KEY, state, profile, service, now=now)
    body, signature = state.split(".")
    for forged in (f"{body}.x{signature[1:]}", "nonsense", ""):
        with pytest.raises(connector_keys.InvalidStateError):
            connector_keys.check_state(KEY, forged, PROFILE, "oura", now=1060)


def test_only_our_websites_connect_pages_may_receive_the_code():
    s = settings()
    connections.check_redirect(s, "oura", "https://site.example/connect/oura")
    connections.check_redirect(s, "oura", "http://localhost:8081/connect/oura")
    for bad in (
        "https://evil.example/connect/oura",
        "https://site.example/connect/whoop",
        "https://site.example/connect/oura?next=/x",
        "https://site.example.evil.example/connect/oura",
    ):
        with pytest.raises(connections.BadRedirectError):
            connections.check_redirect(s, "oura", bad)


def test_services_without_developer_keys_are_not_available():
    s = settings(whoop_client_id=None)
    assert s.connector_credentials("oura") == ("oid", "osecret")
    assert s.connector_credentials("whoop") is None
    assert settings(connector_encryption_key=None).connector_credentials("oura") is None
    with pytest.raises(connections.ServiceNotAvailableError):
        connections.start(s, PROFILE, "whoop", "https://site.example/connect/whoop")


def test_sign_in_address_carries_the_return_address_and_state():
    started = connections.start(settings(), PROFILE, "oura", "https://site.example/connect/oura")
    query = parse_qs(urlsplit(started.url).query)
    assert started.url.startswith("https://cloud.ouraring.com/oauth/authorize?")
    assert query["client_id"] == ["oid"]
    assert query["redirect_uri"] == ["https://site.example/connect/oura"]
    connector_keys.check_state(KEY, query["state"][0], PROFILE, "oura")
    whoop_url = sign_in_address(CONNECTORS["whoop"], "c", "https://site.example/connect/whoop", "s")
    assert "offline" in parse_qs(urlsplit(whoop_url).query)["scope"][0]


# --- When and what to fetch ------------------------------------------------------


def test_first_sync_fetches_30_days_then_from_shortly_before_the_last_sync():
    today = date(2026, 10, 20)
    assert connections.sync_window(today, None) == (date(2026, 9, 21), today)
    last = datetime(2026, 10, 19, 8, tzinfo=UTC)
    assert connections.sync_window(today, last) == (date(2026, 10, 17), today)
    long_ago = datetime(2026, 1, 1, tzinfo=UTC)
    assert connections.sync_window(today, long_ago) == (date(2026, 9, 21), today)


def test_sync_on_open_waits_3_hours_unless_forced():
    now = datetime(2026, 10, 20, 12, tzinfo=UTC)
    assert connections.is_due(None, now, force=False)
    assert not connections.is_due(now - timedelta(hours=2), now, force=False)
    assert connections.is_due(now - timedelta(hours=3), now, force=False)
    assert connections.is_due(now - timedelta(minutes=1), now, force=True)


def test_preferred_source_per_metric():
    rows = [{"source": "apple_health", "v": 1}, {"source": "withings", "v": 2}]
    assert preferred("weight_kg", rows)["v"] == 2
    assert preferred("steps", rows)["v"] == 1
    sleep = [{"source": "apple_health"}, {"source": "oura"}]
    assert preferred("sleep_asleep_minutes", sleep)["source"] == "oura"
    assert preferred("steps", []) is None


# --- Turning each service's data into measurements --------------------------------


def by_metric(samples):
    return {(s["metric"], s["date"]): s.get("value", s.get("at")) for s in samples}


def test_withings_weigh_ins_use_the_local_day_and_the_latest_reading():
    ist_morning = int(
        datetime(2026, 10, 19, 23, 30, tzinfo=UTC).timestamp()
    )  # 05:00 IST on the 20th
    earlier = ist_morning - 3600
    body = {
        "timezone": "Asia/Kolkata",
        "measuregrps": [
            {"date": earlier, "measures": [{"value": 78900, "type": 1, "unit": -3}]},
            {
                "date": ist_morning,
                "measures": [
                    {"value": 78400, "type": 1, "unit": -3},
                    {"value": 215, "type": 6, "unit": -1},
                    {"value": 120, "type": 10, "unit": 0},
                    {"value": 99, "type": 999, "unit": 0},  # a type we don't use
                ],
            },
        ],
    }
    samples = by_metric(withings.measure_samples(body))
    assert samples == {
        ("weight_kg", "2026-10-20"): 78.4,
        ("body_fat_pct", "2026-10-20"): 21.5,
        ("systolic_mmhg", "2026-10-20"): 120,
    }


def test_withings_activity_and_sleep():
    activity = withings.activity_samples(
        {"activities": [{"date": "2026-10-19", "steps": 8421, "distance": 6230.5, "calories": 410}]}
    )
    assert by_metric(activity) == {
        ("steps", "2026-10-19"): 8421,
        ("active_energy_kcal", "2026-10-19"): 410,
        ("walking_running_km", "2026-10-19"): 6.23,
    }
    start = int(datetime(2026, 10, 19, 17, 40, tzinfo=UTC).timestamp())  # 23:10 IST
    end = start + 7 * 3600
    nap = {
        "startdate": end + 4 * 3600,
        "enddate": end + 5 * 3600,
        "data": {"total_timeinbed": 3600},
    }
    night = {
        "startdate": start,
        "enddate": end,
        "timezone": "Asia/Kolkata",
        "data": {"total_timeinbed": 25200, "total_sleep_time": 23400, "deepsleepduration": 5400},
    }
    sleep = by_metric(withings.sleep_samples({"timezone": "Asia/Kolkata", "series": [nap, night]}))
    assert sleep[("sleep_in_bed_minutes", "2026-10-20")] == 420
    assert sleep[("sleep_asleep_minutes", "2026-10-20")] == 390
    assert sleep[("sleep_deep_minutes", "2026-10-20")] == 90
    assert sleep[("bedtime", "2026-10-20")].startswith("2026-10-19T23:10:00+05:30")


def test_oura_uses_the_main_sleep_and_daily_scores():
    periods = [
        {"day": "2026-10-20", "type": "sleep", "time_in_bed": 1800},  # a nap
        {
            "day": "2026-10-20",
            "type": "long_sleep",
            "bedtime_start": "2026-10-19T23:05:00+05:30",
            "bedtime_end": "2026-10-20T06:35:00+05:30",
            "time_in_bed": 27000,
            "total_sleep_duration": 24600,
            "rem_sleep_duration": 5400,
            "average_hrv": 48,
            "lowest_heart_rate": 52,
        },
    ]
    samples = by_metric(oura.sleep_samples(periods))
    assert samples[("sleep_in_bed_minutes", "2026-10-20")] == 450
    assert samples[("sleep_asleep_minutes", "2026-10-20")] == 410
    assert samples[("hrv_ms", "2026-10-20")] == 48
    assert samples[("resting_hr", "2026-10-20")] == 52
    assert samples[("wake_time", "2026-10-20")] == "2026-10-20T06:35:00+05:30"
    scores = oura.score_samples(
        [{"day": "2026-10-20", "score": 82}, {"day": "2026-10-21"}], "readiness_score"
    )
    assert scores == [{"metric": "readiness_score", "date": "2026-10-20", "value": 82}]


def test_whoop_dates_follow_each_records_timezone_and_skip_naps():
    sleeps = [
        {
            "id": "s1",
            "nap": False,
            "score_state": "SCORED",
            "start": "2026-10-19T17:30:00.000Z",
            "end": "2026-10-20T01:00:00.000Z",  # 06:30 IST on the 20th
            "timezone_offset": "+05:30",
            "score": {
                "stage_summary": {
                    "total_in_bed_time_milli": 27_000_000,
                    "total_awake_time_milli": 1_800_000,
                    "total_slow_wave_sleep_time_milli": 5_400_000,
                }
            },
        },
        {"id": "nap", "nap": True, "score_state": "SCORED", "end": "2026-10-20T10:00:00Z"},
    ]
    recoveries = [
        {
            "sleep_id": "s1",
            "score_state": "SCORED",
            "score": {"recovery_score": 67, "hrv_rmssd_milli": 55.2},
        },
        {"sleep_id": "unknown", "score_state": "SCORED", "score": {"recovery_score": 10}},
    ]
    cycles = [
        {
            "start": "2026-10-20T01:00:00Z",
            "timezone_offset": "+05:30",
            "score_state": "SCORED",
            "score": {"strain": 11.4},
        },
        {"start": "2026-10-21T01:00:00Z", "score_state": "PENDING_SCORE", "score": None},
    ]
    samples = by_metric(
        whoop.sleep_samples(sleeps)
        + whoop.recovery_samples(recoveries, sleeps)
        + whoop.cycle_samples(cycles)
    )
    assert samples[("sleep_in_bed_minutes", "2026-10-20")] == 450
    assert samples[("sleep_asleep_minutes", "2026-10-20")] == 420
    assert samples[("sleep_deep_minutes", "2026-10-20")] == 90
    assert samples[("recovery_score", "2026-10-20")] == 67
    assert samples[("hrv_ms", "2026-10-20")] == 55.2
    assert samples[("strain", "2026-10-20")] == 11.4
    assert len([k for k in samples if k[0] == "recovery_score"]) == 1


def test_polar_activity_sleep_and_hrv():
    activity = polar.activity_samples(
        [
            {
                "start_time": "2026-10-19T00:00:00",
                "steps": 9100,
                "active_calories": 380,
                "distance_from_steps": 7000,
            }
        ]
    )
    assert by_metric(activity)[("walking_running_km", "2026-10-19")] == 7.0
    nights = [
        {
            "date": "2026-10-20",
            "sleep_start_time": "2026-10-19T23:00:00+05:30",
            "sleep_end_time": "2026-10-20T06:30:00+05:30",
            "light_sleep": 14400,
            "deep_sleep": 5400,
            "rem_sleep": 4800,
            "sleep_score": 78,
        }
    ]
    sleep = by_metric(polar.sleep_samples(nights))
    assert sleep[("sleep_in_bed_minutes", "2026-10-20")] == 450
    assert sleep[("sleep_asleep_minutes", "2026-10-20")] == 410
    hrv = polar.recharge_samples([{"date": "2026-10-20", "heart_rate_variability_avg": 41}])
    assert hrv == [{"metric": "hrv_ms", "date": "2026-10-20", "value": 41}]


# --- Talking to a service (fake HTTP) ---------------------------------------------


def run(coroutine):
    return asyncio.run(coroutine)


def test_withings_reports_refused_keys_as_needing_a_reconnect():
    transport = httpx2.MockTransport(lambda request: httpx2.Response(200, json={"status": 401}))

    async def go():
        async with httpx2.AsyncClient(transport=transport) as http:
            await withings.WithingsConnector().fetch(
                http, Tokens("bad", None, None), date(2026, 10, 19), date(2026, 10, 20)
            )

    with pytest.raises(ServiceAuthError):
        run(go())


def test_oura_follows_pages_and_sends_the_access_key():
    seen = []

    def handler(request):
        seen.append(request)
        token = request.url.params.get("next_token")
        if request.url.path.endswith("/daily_activity") and not token:
            return httpx2.Response(
                200, json={"data": [{"day": "2026-10-19", "steps": 100}], "next_token": "p2"}
            )
        if request.url.path.endswith("/daily_activity"):
            return httpx2.Response(
                200, json={"data": [{"day": "2026-10-20", "steps": 200}], "next_token": None}
            )
        return httpx2.Response(200, json={"data": []})

    async def go():
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as http:
            return await oura.OuraConnector().fetch(
                http, Tokens("tok", "r", None), date(2026, 10, 19), date(2026, 10, 20)
            )

    samples = run(go())
    assert by_metric(samples) == {("steps", "2026-10-19"): 100, ("steps", "2026-10-20"): 200}
    assert all(r.headers["Authorization"] == "Bearer tok" for r in seen)


# --- The sync itself --------------------------------------------------------------


class FakeSupabase:
    def __init__(self, stored):
        self.stored = stored
        self.rpcs = []
        self.updates = []

    async def rpc(self, function, args, token=None):
        self.rpcs.append((function, args))
        if function == "my_service_connection_keys":
            return self.stored
        if function == "save_service_samples":
            return len(args["p_samples"])
        return None

    async def update(self, table, filters, values, token, returning="*"):
        self.updates.append(values)
        return [values]


class FakeConnector:
    service = "oura"
    label = "Oura"

    def __init__(self, fail=None):
        self.fail = fail
        self.refreshed = False
        self.window = None

    async def refresh(self, http, client, tokens):
        self.refreshed = True
        return Tokens("new-access", "new-refresh", datetime.now(UTC) + timedelta(hours=1))

    async def fetch(self, http, tokens, start, end):
        if self.fail:
            raise self.fail
        self.window = (start, end)
        return [
            {"metric": "steps", "date": "2026-10-20", "value": 5000},
            {"metric": "steps", "date": "2026-10-20", "value": -5},  # out of range: dropped
        ]


def stored_row(expires_at, last_synced_at=None):
    return {
        "service": "oura",
        "external_user_id": None,
        "access_token_enc": connector_keys.encrypt(KEY, "old-access"),
        "refresh_token_enc": connector_keys.encrypt(KEY, "old-refresh"),
        "expires_at": expires_at.isoformat(),
        "last_synced_at": last_synced_at.isoformat() if last_synced_at else None,
    }


def do_sync(supabase, connector, monkeypatch, force=False, only=None):
    monkeypatch.setitem(CONNECTORS, "oura", connector)
    return run(
        connections.sync(
            supabase, None, settings(), "user-token", PROFILE, date(2026, 10, 20), force, only
        )
    )


def test_sync_refreshes_expired_keys_saves_them_first_then_saves_valid_samples(monkeypatch):
    supabase = FakeSupabase([stored_row(datetime.now(UTC) - timedelta(minutes=1))])
    connector = FakeConnector()
    [result] = do_sync(supabase, connector, monkeypatch)
    assert connector.refreshed
    names = [name for name, _ in supabase.rpcs]
    assert names.index("save_service_connection") < names.index("save_service_samples")
    saved_keys = dict(supabase.rpcs)["save_service_connection"]
    assert "new-refresh" not in str(saved_keys)  # stored encrypted
    assert connector_keys.decrypt(KEY, saved_keys["p_refresh_token_enc"]) == "new-refresh"
    assert result.saved == 1 and result.error is None
    assert connector.window == (date(2026, 9, 21), date(2026, 10, 20))
    assert supabase.updates[-1]["last_sync_error"] is None


def test_sync_skips_connections_synced_recently(monkeypatch):
    recent = datetime.now(UTC) - timedelta(hours=1)
    supabase = FakeSupabase([stored_row(datetime.now(UTC) + timedelta(days=1), recent)])
    [result] = do_sync(supabase, FakeConnector(), monkeypatch)
    assert result.skipped
    [forced] = do_sync(supabase, FakeConnector(), monkeypatch, force=True)
    assert not forced.skipped


def test_refused_keys_mark_the_connection_for_reconnecting(monkeypatch):
    supabase = FakeSupabase([stored_row(datetime.now(UTC) + timedelta(days=1))])
    [result] = do_sync(supabase, FakeConnector(fail=ServiceAuthError("401")), monkeypatch)
    assert "Connect again" in result.error
    assert supabase.updates[-1]["needs_reconnect"] is True
    assert not any(name == "save_service_samples" for name, _ in supabase.rpcs)


def test_keys_from_a_changed_encryption_key_need_a_reconnect(monkeypatch):
    row = stored_row(datetime.now(UTC) + timedelta(days=1))
    row["access_token_enc"] = connector_keys.encrypt(Fernet.generate_key().decode(), "x")
    supabase = FakeSupabase([row])

    class NoRefresh(FakeConnector):
        async def refresh(self, http, client, tokens):
            raise ServiceAuthError("cannot")

    [result] = do_sync(supabase, NoRefresh(), monkeypatch)
    assert supabase.updates[-1]["needs_reconnect"] is True
    assert result.error


def test_sync_can_be_limited_to_one_service(monkeypatch):
    supabase = FakeSupabase([stored_row(datetime.now(UTC) + timedelta(days=1))])
    assert do_sync(supabase, FakeConnector(), monkeypatch, force=True, only="withings") == []
    [result] = do_sync(supabase, FakeConnector(), monkeypatch, force=True, only="oura")
    assert result.saved == 1
