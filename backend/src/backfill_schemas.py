from datetime import date, datetime
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator, model_validator

from .schemas import Cohort, Input, TimeBand

LOCAL = ZoneInfo('Asia/Shanghai')


class BackfillStart(Input):
    batch_ref: str = Field(min_length=3, max_length=60, pattern=r'^[A-Za-z0-9][A-Za-z0-9._-]{2,59}$')
    expected_items: int | None = Field(default=None, ge=1, le=500)


class BackfillRecord(Input):
    offline_ref: str = Field(min_length=1, max_length=40, pattern=r'^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$')
    passenger_code: str = Field(min_length=4, max_length=40, pattern=r'^[A-Za-z0-9-]+$')
    cohort: Cohort
    trip_day: date
    filled_at: datetime
    time_band: TimeBand | None = None
    rating: int = Field(ge=1, le=5)

    @field_validator('filled_at')
    @classmethod
    def require_timezone(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError('填写时间须带时区，例如 2026-11-13T08:45:00+08:00')
        return value

    @model_validator(mode='after')
    def check_fill_day(self):
        if self.filled_at.astimezone(LOCAL).date() < self.trip_day:
            raise ValueError(f'{self.offline_ref} 的填写时间早于乘车日期')
        return self


class BackfillUpload(Input):
    items: list[BackfillRecord] = Field(min_length=1, max_length=25)


class BackfillClose(Input):
    note: str | None = Field(default=None, min_length=4, max_length=250)
