"""Validated phase-one product, persona and run configuration data."""

import re
from datetime import datetime
from typing import Annotated, Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Text = Annotated[str, Field(min_length=1)]
Clock = Annotated[str, Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")]
Level = Literal["低", "中", "高"]
Motivation = Literal["随便看看", "有明确任务", "对比竞品", "付费决策"]
LIMITS = {"low": (15, 4), "normal": (40, 8), "high": (80, 12)}
# Persona IDs are p01..p99; the timeline length is the user's choice within a year.
MIN_PERSONAS, MAX_PERSONAS, MAX_DAYS = 2, 99, 365


class Data(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TestAccount(Data):
    role: Text
    description: Text


# Applied when a manual names no forbidden actions: a URL-only manual must still never pay, delete or send.
DEFAULT_FORBIDDEN = ["真实支付或下单", "删除账号或数据", "对外发送邮件、短信或消息", "提交真实的个人信息"]


class ManualMetadata(Data):
    """Only url and allowed_domains are required; the rest falls back to the product's host, a visitor and safe defaults."""
    name: Text | None = None
    url: Text
    allowed_domains: list[Text] = Field(min_length=1)
    test_accounts: list[TestAccount] = []
    forbidden_actions: list[Text] = Field(default_factory=lambda: list(DEFAULT_FORBIDDEN), min_length=1)

    @model_validator(mode="after")
    def default_name(self):
        if self.name is None:
            self.name = urlsplit(self.url).hostname or self.url
        return self


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
    target_age_min: int | None = Field(ge=1, le=110, strict=True)
    target_age_max: int | None = Field(ge=1, le=110, strict=True)

    @model_validator(mode="after")
    def valid_age_range(self):
        if (self.target_age_min is None) != (self.target_age_max is None):
            raise ValueError("Give both target ages or neither")
        if self.target_age_min is not None and self.target_age_min > self.target_age_max:
            raise ValueError("target_age_min must not exceed target_age_max")
        return self


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
    motivation: Motivation
    motivation_detail: Text
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


def asleep_hours(wake, sleep):
    """Hours whose whole 60 minutes fall inside the single sleep window."""
    start, length = minutes(sleep), (minutes(wake) - minutes(sleep)) % 1440
    return {hour for hour in range(24) if (hour * 60 - start) % 1440 + 60 <= length}


# The timeline does not model weekdays or dates, so the browse state must not name one.
CALENDAR_WORDS = re.compile(r"星期|礼拜|周[一二三四五六日天末]|工作日|双休|节假日|\d+\s*月\s*\d+\s*[日号]")


class Schedule(Data):
    wake: Clock
    sleep: Clock
    activity_by_hour: dict[int, float]
    browse_slot: Clock
    # Which day of the timeline the persona first uses the product (drafts before multi-day timelines: day 1).
    browse_day: int = Field(default=1, ge=1, le=MAX_DAYS, strict=True)
    state_at_browse: Text

    @field_validator("state_at_browse")
    @classmethod
    def no_calendar_day(cls, value):
        if CALENDAR_WORDS.search(value):
            raise ValueError("state_at_browse must not name a calendar day, weekday or weekend")
        return value

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
        asleep = sorted(hour for hour in asleep_hours(self.wake, self.sleep) if self.activity_by_hour.get(hour, 0) > 0)
        if asleep:
            raise ValueError(f"Activity must be 0 for hours spent fully asleep: {asleep}")
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


class Sampling(Data):
    """Per-persona sampling for the calls spoken in the persona's own voice (browsing, discussion, questionnaire, interview)."""
    temperature: float = Field(ge=0, le=2)
    top_p: float = Field(gt=0, le=1)
    presence_penalty: float = Field(ge=-2, le=2)


class Persona(Identity):
    persona_id: Annotated[str, Field(pattern=r"^p\d{2}$")]
    browsing_profile: BrowsingProfile
    schedule: Schedule
    participation: Literal["poster", "commenter", "reactor", "lurker"]
    disclosure: Disclosure
    # Drafts made before per-persona sampling have none: their calls keep the framework defaults.
    sampling: Sampling | None = None


class RunConfig(Data):
    start_time: datetime
    duration_days: int = Field(ge=1, le=MAX_DAYS, strict=True)
    time_slice_minutes: int = Field(ge=1, le=1440, strict=True)
    max_concurrency: int = Field(ge=1, le=10, strict=True)

    @model_validator(mode="after")
    def valid_clock(self):
        if self.start_time.tzinfo is None:
            raise ValueError("Timeline start_time must include a timezone")
        if 1440 * self.duration_days % self.time_slice_minutes:
            raise ValueError("Time slices must divide the timeline evenly")
        return self


class CohortSlot(Data):
    """One row of the main agent's dimension matrix; personas are filled in to match it."""
    persona_id: Annotated[str, Field(pattern=r"^p\d{2}$")]
    realname: Text
    profession: Text
    gender: Text
    age: int = Field(ge=1, le=110, strict=True)
    tech_level: Literal["novice", "normal", "developer"]
    device: Literal["mobile", "desktop"]
    patience: Literal["low", "normal", "high"]
    motivation: Motivation
    participation: Literal["poster", "commenter", "reactor", "lurker"]
    withhold_tendency: Level
    browse_slot: Clock
    browse_day: int = Field(ge=1, le=MAX_DAYS, strict=True)
    account_role: Text
    assignment: Assignment
    reason: Text


# The main agent plans the cohort ten slots per request, so large cohorts fit any provider's output limit.
PLAN_BATCH = 10


class CohortPlan(Data):
    """First batch: the overall rationale plus up to PLAN_BATCH slots."""
    rationale: Text
    slots: list[CohortSlot] = Field(min_length=1, max_length=PLAN_BATCH)


class CohortBatch(Data):
    slots: list[CohortSlot] = Field(min_length=1, max_length=PLAN_BATCH)


class Recommendation(Data):
    """The main agent's suggested cohort size and timeline length; the user may change both before generation."""
    persona_count: int = Field(ge=MIN_PERSONAS, le=MAX_PERSONAS, strict=True)
    duration_days: int = Field(ge=1, le=MAX_DAYS, strict=True)
    reason: Text


class Draft(Data):
    product: ProductSummary
    cohort_rationale: Text
    personas: list[Persona] = Field(min_length=MIN_PERSONAS, max_length=MAX_PERSONAS)
    run_config: RunConfig
