"""ICAO AIRAC 28 天周期计算。

周期标识按生效日期所在公历年的序号生成。有效区间采用左闭右开语义。
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from pydantic import BaseModel, ConfigDict

# ICAO AIRAC 生效日期的已知锚点；之后和之前均严格相隔 28 天。
_AIRAC_ANCHOR = date(2020, 1, 2)
_CYCLE_DAYS = 28


class AiracPeriod(BaseModel):
    """一个 AIRAC 周期，`valid_to` 是下一周期起点（不包含）。"""

    model_config = ConfigDict(frozen=True)

    identifier: str
    valid_from: datetime
    valid_to: datetime

    def contains(self, instant: datetime) -> bool:
        instant = _as_utc(instant)
        return self.valid_from <= instant < self.valid_to


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("时间必须包含时区")
    return value.astimezone(UTC)


def _effective_date_at(day: date) -> date:
    delta_days = (day - _AIRAC_ANCHOR).days
    cycle_offset = delta_days // _CYCLE_DAYS
    return _AIRAC_ANCHOR + timedelta(days=cycle_offset * _CYCLE_DAYS)


def _cycle_number(effective: date) -> int:
    first = _effective_date_at(date(effective.year, 1, 1))
    if first.year < effective.year:
        first += timedelta(days=_CYCLE_DAYS)
    return ((effective - first).days // _CYCLE_DAYS) + 1


def airac_period_at(instant: datetime | None = None) -> AiracPeriod:
    """返回给定时刻生效的 AIRAC 周期。"""

    instant = _as_utc(instant or datetime.now(UTC))
    effective = _effective_date_at(instant.date())
    expires = effective + timedelta(days=_CYCLE_DAYS)
    identifier = f"{effective.year % 100:02d}{_cycle_number(effective):02d}"
    return AiracPeriod(
        identifier=identifier,
        valid_from=datetime.combine(effective, datetime.min.time(), tzinfo=UTC),
        valid_to=datetime.combine(expires, datetime.min.time(), tzinfo=UTC),
    )
