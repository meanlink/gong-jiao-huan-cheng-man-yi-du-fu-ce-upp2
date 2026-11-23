from enum import StrEnum

from pydantic import Field, StrictBool

from .schemas import Input


class Desk(StrEnum):
    ACCESS = 'access'
    STATION = 'station'
    DISPATCH = 'dispatch'


class Category(StrEnum):
    STEP_FREE = 'step_free'
    WAYFINDING = 'wayfinding'
    MISSED_CONNECTION = 'missed_connection'


class DeskSettings(Input):
    location: str = Field(min_length=2, max_length=100)
    capacity: int = Field(strict=True, ge=1, le=30)
    available: StrictBool


class NoticeText(Input):
    meeting_point: str = Field(min_length=2, max_length=100)
    directions: str = Field(min_length=8, max_length=280)
    previous_edition: int = Field(strict=True, ge=0)


class TransferRequest(Input):
    category: Category
    landmark: str = Field(min_length=2, max_length=100)
    description: str = Field(min_length=4, max_length=240)
    notice_edition: int = Field(strict=True, gt=0)


class Resolution(Input):
    note: str = Field(min_length=8, max_length=240)
