"""Validated phase-one product, persona and run configuration data."""

from datetime import datetime
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Text = Annotated[str, Field(min_length=1)]
Clock = Annotated[str, Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")]
Level = Literal["低", "中", "高"]
LIMITS = {"low": (15, 4), "normal": (40, 8), "high": (80, 12)}


class Data(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TestAccount(Data):
    role: Text
    description: Text


class ManualMetadata(Data):
    name: Text
    url: Text
    allowed_domains: list[Text] = Field(min_length=1)
    test_accounts: list[TestAccount] = Field(min_length=1)
    forbidden_actions: list[Text] = Field(min_length=1)


class Flow(Data):
    name: Text
    account_role: Text
    entry: Text
    steps: Text
    expected_result: Text
    success_criteria: Text


class ProductSummary(Data):
    positioning: Text
    target_users: Text
    features: list[Text] = Field(min_length=1)
    assumptions: list[Text]


class BigFive(Data):
    openness: Level
    conscientiousness: Level
    extraversion: Level
    agreeableness: Level
    neuroticism: Level


class Identity(Data):
    realname: Text
    username: Text
    gender: Text
    age: int = Field(ge=1, le=110, strict=True)
    city: Text
    timezone: Text
    profession: Text
    industry: Text
    education: Text
    income_level: Level
    life_context: Text
    product_history: Text
    bio: Text
    persona: Text
    mbti: Annotated[str, Field(pattern=r"^[IE][NS][FT][JP]$")]
    big_five: BigFive
    communication_style: Text
    interested_topics: list[Text] = Field(min_length=1)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (KeyError, ValueError) as error:
            raise ValueError("Use an IANA timezone such as Asia/Shanghai") from error
        return value


class HourActivity(Data):
    hour: int = Field(ge=0, le=23, strict=True)
    probability: float = Field(ge=0, le=1)


class PersonaDetails(Identity):
    wake: Clock
    sleep: Clock
    activity: list[HourActivity] = Field(min_length=1, max_length=24)
    state_at_browse: Text
    motivation: Text
    candor: Level
    withhold_reasons: list[Text]


class Assignment(Data):
    type: Literal["task", "explore"]
    flow: Text | None

    @model_validator(mode="after")
    def flow_required(self):
        if (self.type == "task") != (self.flow is not None):
            raise ValueError("A task needs a flow; exploration must have flow=null")
        return self


class BrowsingProfile(Data):
    device: Literal["mobile", "desktop"]
    tech_level: Literal["novice", "normal", "developer"]
    patience: Literal["low", "normal", "high"]
    max_steps: int = Field(ge=1, le=80, strict=True)
    stall_limit: int = Field(ge=1, le=12, strict=True)
    motivation: Text
    account_role: Text
    tools: list[Literal["read_console", "list_failed_requests"]]
    assignment: Assignment

    @model_validator(mode="after")
    def enforce_constraints(self):
        max_steps, stall_limit = LIMITS[self.patience]
        if self.max_steps > max_steps or self.stall_limit > min(stall_limit, self.max_steps):
            raise ValueError("Step and stall limits must fit the patience level")
        expected = {"read_console", "list_failed_requests"} if self.tech_level == "developer" else set()
        if set(self.tools) != expected or len(self.tools) != len(expected):
            raise ValueError("Only developers receive console/network tools")
        return self


def minutes(clock):
    hour, minute = map(int, clock.split(":"))
    return hour * 60 + minute


class Schedule(Data):
    wake: Clock
    sleep: Clock
    activity_by_hour: dict[int, float]
    browse_slot: Clock
    state_at_browse: Text

    @model_validator(mode="after")
    def coherent_schedule(self):
        wake, sleep, browse = map(minutes, [self.wake, self.sleep, self.browse_slot])
        awake = wake <= browse < sleep if wake < sleep else browse >= wake or browse < sleep
        if wake == sleep or not awake:
            raise ValueError("Browse slot must fall within awake hours, including overnight schedules")
        if not 240 <= (wake - sleep) % 1440 <= 720:
            raise ValueError("The single sleep window must last 4..12 hours for this synthetic persona")
        if not self.activity_by_hour or any(not 0 <= hour <= 23 or not 0 <= value <= 1
                                           for hour, value in self.activity_by_hour.items()):
            raise ValueError("Activity needs hours 0..23 and probabilities 0..1")
        return self


class Disclosure(Data):
    candor: Level
    withhold_tendency: Level
    withhold_reasons: list[Text]

    @model_validator(mode="after")
    def reasons_for_withholding(self):
        if self.withhold_tendency == "高" and not self.withhold_reasons:
            raise ValueError("High withholding tendency needs at least one reason")
        return self


class Persona(Identity):
    persona_id: Annotated[str, Field(pattern=r"^p\d{2}$")]
    browsing_profile: BrowsingProfile
    schedule: Schedule
    participation: Literal["poster", "commenter", "reactor", "lurker"]
    disclosure: Disclosure


class RunConfig(Data):
    start_time: datetime
    duration_days: int = Field(ge=1, le=30, strict=True)
    time_slice_minutes: int = Field(ge=1, le=1440, strict=True)
    max_concurrency: int = Field(ge=1, le=10, strict=True)

    @model_validator(mode="after")
    def valid_clock(self):
        if self.start_time.tzinfo is None:
            raise ValueError("Timeline start_time must include a timezone")
        if 1440 * self.duration_days % self.time_slice_minutes:
            raise ValueError("Time slices must divide the timeline evenly")
        return self


class Draft(Data):
    product: ProductSummary
    personas: list[Persona] = Field(min_length=10, max_length=10)
    run_config: RunConfig
