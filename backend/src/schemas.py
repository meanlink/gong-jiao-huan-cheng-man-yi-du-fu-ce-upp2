from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Cohort(StrEnum):
    BASELINE = 'baseline'
    TRIAL = 'trial'


class TimeBand(StrEnum):
    PEAK = 'peak'
    OFFPEAK = 'offpeak'


class Stage(StrEnum):
    DRAFT = 'draft'
    SURVEYING = 'surveying'
    SEALED = 'sealed'
    DECIDED = 'decided'


class SampleState(StrEnum):
    ELIGIBLE = 'eligible'
    QUEUE = 'queue'
    EXCLUDED = 'excluded'


class Decision(StrEnum):
    ADOPT = 'adopt'
    RETAIN = 'retain'
    EXTEND = 'extend'


class Input(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')


class Credentials(Input):
    email: str = Field(max_length=160)
    password: str = Field(min_length=1, max_length=128)


class PlanFields(Input):
    hub: str = Field(min_length=2, max_length=40)
    feeder: str = Field(min_length=1, max_length=20)
    connection: str = Field(min_length=1, max_length=20)
    baseline_path: str = Field(min_length=4, max_length=180)
    trial_path: str = Field(min_length=4, max_length=180)
    baseline_from: date
    baseline_to: date
    trial_from: date
    trial_to: date

    @model_validator(mode='after')
    def check_comparison(self):
        if not self.baseline_from <= self.baseline_to < self.trial_from <= self.trial_to:
            raise ValueError('基线和复测的日期须依次排列，且不能重叠')
        if self.baseline_path == self.trial_path:
            raise ValueError('请写明改线前后不同的换乘路径')
        return self


class NewPlan(PlanFields):
    code: str = Field(pattern=r'^[A-Z0-9][A-Z0-9-]{2,19}$')


class SurveyInput(Input):
    passenger_code: str = Field(min_length=4, max_length=40, pattern=r'^[A-Za-z0-9-]+$')
    cohort: Cohort
    trip_day: date
    time_band: TimeBand | None = None
    rating: int = Field(ge=1, le=5)


class CleanupInput(Input):
    time_band: TimeBand | None = None
    note: str = Field(min_length=4, max_length=250)


class DecisionInput(Input):
    decision: Decision
    note: str = Field(min_length=8, max_length=350)
