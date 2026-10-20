"""Rules for health data intake (core/models/health_data.py, core/health_data.py)."""

import hashlib
from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from core.health_data import (
    DateOutOfRangeError,
    check_local_date,
    hash_token,
    new_token,
    validate_samples,
)
from core.models.health_data import AddWater, IngestRequest, IngestSample, LogWeight


def test_number_metrics_need_a_value_in_range():
    assert IngestSample(metric="steps", date="2026-10-20", value=8421).value == 8421
    with pytest.raises(ValidationError, match="needs a 'value'"):
        IngestSample(metric="steps", date="2026-10-20")
    with pytest.raises(ValidationError, match="between 20 and 400"):
        IngestSample(metric="weight_kg", date="2026-10-20", value=4)
    with pytest.raises(ValidationError, match="between 0 and 1440"):
        IngestSample(metric="sleep_in_bed_minutes", date="2026-10-20", value=2000)


def test_bedtime_and_wake_time_need_a_time():
    sample = IngestSample(metric="bedtime", date="2026-10-20", at="2026-10-19T23:40:00+05:30")
    assert sample.at.hour == 23
    with pytest.raises(ValidationError, match="needs 'at'"):
        IngestSample(metric="wake_time", date="2026-10-20")


def test_unknown_metric_is_rejected():
    with pytest.raises(ValidationError):
        IngestSample(metric="happiness", date="2026-10-20", value=10)


def test_numbers_formatted_by_shortcuts_are_accepted():
    assert IngestSample(metric="steps", date="2026-10-20", value="8,421").value == 8421
    assert IngestSample(metric="weight_kg", date="2026-10-20", value="78.5").value == 78.5
    assert IngestSample(metric="weight_kg", date="2026-10-20", value="78.4 kg").value == 78.4
    assert IngestSample(metric="steps", date="2026-10-20", value="8,421 steps").value == 8421
    with pytest.raises(ValidationError):
        IngestSample(metric="steps", date="2026-10-20", value="lots")


def test_bad_samples_are_skipped_without_losing_the_good_ones():
    valid, skipped = validate_samples(
        [
            {"metric": "steps", "date": "2026-10-19", "value": "8,421"},
            {"metric": "weight_kg", "date": "2026-10-19", "value": 0},  # no weigh-in
            {"metric": "happiness", "date": "2026-10-19", "value": 1},
            "not a sample",
        ]
    )
    assert [s.metric for s in valid] == ["steps"]
    assert [(s.index, s.metric) for s in skipped] == [
        (1, "weight_kg"),
        (2, "happiness"),
        (3, None),
    ]
    assert "between 20 and 400" in skipped[0].reason


def test_a_batch_needs_between_1_and_500_samples():
    with pytest.raises(ValidationError):
        IngestRequest(samples=[])
    one = {"metric": "steps", "date": "2026-10-20", "value": 1}
    with pytest.raises(ValidationError):
        IngestRequest(samples=[one] * 501)


def test_tokens_are_random_and_hashed_like_the_database_does():
    token = new_token()
    assert token.startswith("wst_") and len(token) > 40
    assert new_token() != token
    assert hash_token(token) == hashlib.sha256(token.encode()).hexdigest()
    assert len(hash_token(token)) == 64


def test_local_date_must_be_within_a_day_of_utc():
    now = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
    for day in (date(2026, 10, 19), date(2026, 10, 20), date(2026, 10, 21)):
        check_local_date(day, now)
    for day in (date(2026, 10, 18), date(2026, 10, 22)):
        with pytest.raises(DateOutOfRangeError):
            check_local_date(day, now)


def test_water_and_weight_amounts_are_checked():
    with pytest.raises(ValidationError):
        AddWater(ml=0, date="2026-10-20")
    with pytest.raises(ValidationError):
        AddWater(ml=5000, date="2026-10-20")
    with pytest.raises(ValidationError):
        LogWeight(kg=900, date="2026-10-20")
