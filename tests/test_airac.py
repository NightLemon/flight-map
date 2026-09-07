from datetime import UTC, datetime

from flightmap_schema import airac_period_at


def test_current_airac_2609() -> None:
    period = airac_period_at(datetime(2026, 9, 7, 12, tzinfo=UTC))

    assert period.identifier == "2609"
    assert period.valid_from == datetime(2026, 9, 3, tzinfo=UTC)
    assert period.valid_to == datetime(2026, 10, 1, tzinfo=UTC)


def test_airac_boundary_is_left_closed_right_open() -> None:
    before = airac_period_at(datetime(2026, 9, 30, 23, 59, 59, tzinfo=UTC))
    after = airac_period_at(datetime(2026, 10, 1, tzinfo=UTC))

    assert before.identifier == "2609"
    assert before.contains(datetime(2026, 9, 3, tzinfo=UTC))
    assert not before.contains(datetime(2026, 10, 1, tzinfo=UTC))
    assert after.identifier == "2610"
