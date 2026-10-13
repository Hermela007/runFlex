"""Data model sketch for the adaptive running plan generator.

Inputs, outputs and per-goal config only. The logic is deliberately left as
stubs so it can be built test-first.

The numbers below are rule-of-thumb placeholders to tune, not coaching or
medical advice.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time, timedelta
from enum import Enum


# ---------------------------------------------------------------- enums ----

class Goal(Enum):
    C25K = "c25k"
    TEN_K = "10k"
    FIFTEEN_K = "15k"
    HALF_MARATHON = "half"
    MARATHON = "marathon"


class SessionType(Enum):
    WALK_RUN = "walk_run"   # C25K only: fixed run/walk intervals
    RECOVERY = "recovery"   # short, easy
    SPEED = "speed"         # effort-based intervals (no pace targets in v1)
    LONG = "long"           # longest run of the week


class Effort(Enum):
    WALK = "walk"
    EASY = "easy"
    HARD = "hard"


class Status(Enum):
    PLANNED = "planned"
    DONE = "done"
    MISSED = "missed"


# --------------------------------------------------------------- output ----

@dataclass
class Segment:
    """One block inside a session, e.g. 3 min HARD, repeated 4 times."""
    effort: Effort
    minutes: float
    repeats: int = 1


@dataclass
class Session:
    day: date
    run_time: time                  # taken from the matching available_days entry
    week: int                       # 1-based week of the plan
    type: SessionType
    segments: list[Segment]
    distance_km: float | None = None  # None for C25K (time-based)
    status: Status = Status.PLANNED


# ---------------------------------------------------------------- input ----

@dataclass
class PlanRequest:
    goal: Goal
    start_date: date
    # Maps weekday (0 = Monday ... 6 = Sunday) to the preferred run time on
    # that day, so calendar events land at the right time around the user's
    # existing schedule rather than each day sharing one fixed time.
    # e.g. {1: time(7, 0), 5: time(18, 0)} = 7am Tuesdays, 6pm Saturdays.
    available_days: dict[int, time]
    max_session_minutes: int = 90
    current_weekly_km: float = 0.0  # ignored for C25K
    race_date: date | None = None   # anchors the taper for distance goals


# -------------------------------------------------------- per-goal config ---

@dataclass(frozen=True)
class GoalConfig:
    weeks: int
    sessions_per_week: int
    peak_weekly_km: float | None = None
    peak_long_km: float | None = None
    taper_weeks: int = 0
    min_weekly_km_to_start: float = 0.0   # prerequisite


# Placeholder numbers, to be tuned.
GOAL_CONFIGS: dict[Goal, GoalConfig] = {
    Goal.C25K:          GoalConfig(weeks=9,  sessions_per_week=3),
    Goal.TEN_K:         GoalConfig(weeks=10, sessions_per_week=3,
                                   peak_weekly_km=25, peak_long_km=11,
                                   taper_weeks=1, min_weekly_km_to_start=8),
    Goal.FIFTEEN_K:     GoalConfig(weeks=12, sessions_per_week=3,
                                   peak_weekly_km=32, peak_long_km=16,
                                   taper_weeks=1, min_weekly_km_to_start=12),
    Goal.HALF_MARATHON: GoalConfig(weeks=14, sessions_per_week=3,
                                   peak_weekly_km=40, peak_long_km=20,
                                   taper_weeks=2, min_weekly_km_to_start=16),
    Goal.MARATHON:      GoalConfig(weeks=18, sessions_per_week=3,
                                   peak_weekly_km=55, peak_long_km=32,
                                   taper_weeks=3, min_weekly_km_to_start=25),
}

# Shared rules the engine will enforce for distance goals.
MAX_WEEKLY_INCREASE = 0.10   # cap on week-over-week volume growth
CUTBACK_EVERY = 4            # every 4th week is lighter...
CUTBACK_FACTOR = 0.80        # ...at 80% of the previous week's volume
LONG_RUN_MAX_SHARE = 0.40    # long run <= 40% of weekly volume


@dataclass
class Plan:
    request: PlanRequest
    config: GoalConfig
    sessions: list[Session] = field(default_factory=list)


# ------------------------------------------------------------ the engine ----

def validate_request(req: PlanRequest) -> list[str]:
    """Return a list of problems (empty list = request is fine).

    Checks to write tests for:
    - fewer available days than sessions_per_week
    - current_weekly_km below the goal's prerequisite
    - race_date too soon for the plan length
    """
    problems: list[str] = []
    config = GOAL_CONFIGS[req.goal]

    if len(req.available_days) < config.sessions_per_week:
        problems.append(
            f"{req.goal.value} needs {config.sessions_per_week} available days "
            f"per week, but only {len(req.available_days)} were given."
        )

    return problems


def _walk(minutes: float) -> Segment:
    return Segment(Effort.WALK, minutes)

def _run(minutes: float) -> Segment:
    return Segment(Effort.EASY, minutes)

# NHS Couch to 5K plan: https://www.nhs.uk/better-health/get-active/
# get-running-with-couch-to-5k/couch-to-5k-running-plan/
# Each week maps to exactly 3 run structures (one per session that week).
# Most weeks repeat the same structure 3 times; weeks 5 and 6 do not.
WEEK_STRUCTURES: dict[int, list[list[Segment]]] = {
    1: [[_walk(5), *([_run(1), _walk(1.5)] * 7), _run(1), _walk(5)]] * 3,
    2: [[_walk(5), *([_run(1.5), _walk(2)] * 5), _run(1.5), _walk(5)]] * 3,
    3: [[_walk(5), _run(1.5), _walk(1.5), _run(3), _walk(3),
         _run(1.5), _walk(1.5), _run(3), _walk(5)]] * 3,
    4: [[_walk(5), _run(3), _walk(1.5), _run(5), _walk(2.5),
         _run(3), _walk(1.5), _run(5), _walk(5)]] * 3,
    5: [
        [_walk(5), _run(5), _walk(3), _run(5), _walk(3), _run(5), _walk(5)],
        [_walk(5), _run(8), _walk(5), _run(8), _walk(5)],
        [_walk(5), _run(20), _walk(5)],
    ],
    6: [
        [_walk(5), _run(5), _walk(3), _run(8), _walk(3), _run(5), _walk(5)],
        [_walk(5), _run(10), _walk(3), _run(10), _walk(5)],
        [_walk(5), _run(25), _walk(5)],
    ],
    7: [[_walk(5), _run(25), _walk(5)]] * 3,
    8: [[_walk(5), _run(28), _walk(5)]] * 3,
    9: [[_walk(5), _run(30), _walk(5)]] * 3,
}


def generate_plan(req: PlanRequest) -> Plan:
    """Build a full plan from a valid request. Pure: no I/O, no clock."""
    config = GOAL_CONFIGS[req.goal]
    total_sessions = config.weeks * config.sessions_per_week

    sessions: list[Session] = []
    current_date = req.start_date

    while len(sessions) < total_sessions:
        weekday = current_date.weekday()
        if weekday in req.available_days:
            week_number = (len(sessions) // config.sessions_per_week) + 1
            run_index_in_week = len(sessions) % config.sessions_per_week
            sessions.append(Session(
                day=current_date,
                run_time=req.available_days[weekday],
                week=week_number,
                type=SessionType.WALK_RUN,
                segments=WEEK_STRUCTURES[week_number][run_index_in_week],
            ))
        current_date += timedelta(days=1)

    return Plan(request=req, config=config, sessions=sessions)
