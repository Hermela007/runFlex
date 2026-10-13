"""Data model sketch for the adaptive running plan generator.

Inputs, outputs and per-goal config only. The logic is deliberately left as
stubs so it can be built test-first.

The numbers below are rule-of-thumb placeholders to tune, not coaching or
medical advice.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta
from enum import Enum
from itertools import combinations


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
    is_repeat: bool = False         # True if replan inserted this as a repeated week


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


def _training_weekdays(req: PlanRequest) -> tuple[int, ...]:
    """The weekdays to actually run on, picked from req.available_days.

    When more days are available than sessions_per_week, picks the most
    spread-out set so there are rest days between runs: e.g. Mon-Fri gives
    Mon/Wed/Fri, not Mon/Tue/Wed. The week is treated as a loop (Sunday's
    run is followed by next Monday's), and options are ranked by their
    smallest gap first, then the next smallest, and so on; ties go to the
    earliest days. With exactly sessions_per_week days available there is
    nothing to choose, so those days are used as-is — even if consecutive.
    """
    per_week = GOAL_CONFIGS[req.goal].sessions_per_week

    def spread(days: tuple[int, ...]) -> tuple:
        gaps = [b - a for a, b in zip(days, days[1:])] + [days[0] + 7 - days[-1]]
        return tuple(sorted(gaps)), tuple(-d for d in days)

    return max(combinations(sorted(req.available_days), per_week), key=spread)


def generate_plan(req: PlanRequest) -> Plan:
    """Build a full plan from a valid request. Pure: no I/O, no clock.

    Plan week n is the nth Monday-Sunday calendar week, with its sessions on
    the training weekdays. If the start date's own week has too few of those
    days left, the plan starts the following Monday instead.
    """
    config = GOAL_CONFIGS[req.goal]
    weekdays = _training_weekdays(req)

    monday = req.start_date - timedelta(days=req.start_date.weekday())
    if sum(1 for d in weekdays if d >= req.start_date.weekday()) < config.sessions_per_week:
        monday += timedelta(weeks=1)

    sessions: list[Session] = []
    for week_number in range(1, config.weeks + 1):
        week_start = monday + timedelta(weeks=week_number - 1)
        for run_index_in_week, weekday in enumerate(weekdays):
            sessions.append(Session(
                day=week_start + timedelta(days=weekday),
                run_time=req.available_days[weekday],
                week=week_number,
                type=SessionType.WALK_RUN,
                segments=WEEK_STRUCTURES[week_number][run_index_in_week],
            ))

    return Plan(request=req, config=config, sessions=sessions)


# ---------------------------------------------------------------- replan ----

def _next_available_dates(
    req: PlanRequest, start: date, count: int, exclude: frozenset[date] = frozenset()
) -> list[date]:
    """The next `count` dates on or after `start` that fall on a training
    weekday (see _training_weekdays) and are not in `exclude`.

    `exclude` must hold every date already used by a session that is staying
    where it is — otherwise a newly picked date can collide with one of
    those, double-booking the day. This matters even when `start` is itself
    the date of a just-missed session: that weekday is still "available" in
    general, but that specific date is already taken.

    Assumes a validated request (enough available days), otherwise this
    would loop forever.
    """
    weekdays = _training_weekdays(req)
    dates: list[date] = []
    cursor = start
    while len(dates) < count:
        if cursor.weekday() in weekdays and cursor not in exclude:
            dates.append(cursor)
        cursor += timedelta(days=1)
    return dates


def _sessions_by_week(plan: Plan) -> dict[int, list[Session]]:
    """Sessions grouped by week number, each week in date order."""
    grouped: dict[int, list[Session]] = {}
    for s in plan.sessions:
        grouped.setdefault(s.week, []).append(s)
    for sessions in grouped.values():
        sessions.sort(key=lambda s: s.day)
    return grouped


def _find_repeat(plan: Plan) -> tuple[int, list[int]] | None:
    """Decide whether some week needs repeating.

    Returns (after_week, weeks_to_copy) or None. The copies are inserted
    right after `after_week`.

    Rules:
    - Every session in a week missed -> repeat that week.
    - A week with 2 misses, then a miss in the following week (B):
        * B's first session missed -> repeat the 2-miss week, then redo B
        * otherwise -> repeat B
    A trigger is skipped if the week after `after_week` was already inserted
    by an earlier replan, so calling replan twice changes nothing.

    A trigger is also skipped if any session after `after_week` has already
    been logged (done/missed): the user has moved past that point, and those
    sessions keep their week numbers, so inserting copies there would put two
    different weeks under one number. This only happens when several sessions
    are logged in one replan call; a later trigger then takes over. Without
    this, two overlapping 2-miss triggers undo each other forever.
    """
    per_week = plan.config.sessions_per_week
    weeks = _sessions_by_week(plan)

    def already_repeated(after_week: int) -> bool:
        return any(s.is_repeat for s in weeks.get(after_week + 1, []))

    def overtaken(after_week: int) -> bool:
        return any(
            s.status != Status.PLANNED
            for w, sessions in weeks.items() if w > after_week
            for s in sessions
        )

    for week in sorted(weeks):
        sessions = weeks[week]
        missed = sum(1 for s in sessions if s.status == Status.MISSED)

        if missed >= per_week:
            if not already_repeated(week) and not overtaken(week):
                return week, [week]
            continue

        following = weeks.get(week + 1)
        if missed >= 2 and following and any(
            s.status == Status.MISSED for s in following
        ):
            if already_repeated(week + 1) or overtaken(week + 1):
                continue
            if following[0].status == Status.MISSED:
                return week + 1, [week, week + 1]
            return week + 1, [week + 1]

    return None


def _insert_repeats(
    plan: Plan, after_week: int, copy_weeks: list[int], today: date
) -> Plan:
    """Insert fresh copies of `copy_weeks` after `after_week`.

    - Sessions in `after_week` that haven't happened yet are dropped; the
      repeat replaces them.
    - Every later planned session moves back by len(copy_weeks) weeks.
    """
    req = plan.request
    weeks = _sessions_by_week(plan)

    dropped_ids = {id(s) for s in weeks[after_week] if s.status == Status.PLANNED}
    later = sorted(
        (s for s in plan.sessions if s.week > after_week and s.status == Status.PLANNED),
        key=lambda s: (s.week, s.day),
    )
    later_ids = {id(s) for s in later}
    kept = [
        s for s in plan.sessions
        if id(s) not in dropped_ids and id(s) not in later_ids
    ]

    templates = [(offset, s) for offset, w in enumerate(copy_weeks) for s in weeks[w]]
    taken = frozenset(s.day for s in kept)
    new_dates = _next_available_dates(req, today, len(templates) + len(later), exclude=taken)

    repeats = [
        replace(
            s,
            day=d,
            run_time=req.available_days[d.weekday()],
            week=after_week + 1 + offset,
            status=Status.PLANNED,
            is_repeat=True,
        )
        for (offset, s), d in zip(templates, new_dates)
    ]
    shifted = [
        replace(
            s,
            day=d,
            run_time=req.available_days[d.weekday()],
            week=s.week + len(copy_weeks),
        )
        for s, d in zip(later, new_dates[len(templates):])
    ]
    return replace(plan, sessions=kept + repeats + shifted)


def replan(plan: Plan, today: date) -> Plan:
    """Rebuild the remaining sessions after some were missed.

    - Repeat weeks as described in _find_repeat.
    - Otherwise, what's left of the current week shifts onto the next
      available days.
    Returns a new Plan; the input is never modified.
    """
    req = plan.request

    while True:
        found = _find_repeat(plan)
        if found is None:
            break
        after_week, copy_weeks = found
        plan = _insert_repeats(plan, after_week, copy_weeks, today)

    upcoming = [s for s in plan.sessions if s.day >= today]
    if not upcoming:
        return plan

    target_week = min(s.week for s in upcoming)
    still_planned = [
        s for s in plan.sessions
        if s.week == target_week and s.status == Status.PLANNED and s.day >= today
    ]
    still_planned_ids = {id(s) for s in still_planned}
    taken = frozenset(
        s.day for s in plan.sessions if id(s) not in still_planned_ids
    )
    new_dates = _next_available_dates(req, today, len(still_planned), exclude=taken)
    updates = {id(s): d for s, d in zip(still_planned, new_dates)}

    new_sessions = []
    for s in plan.sessions:
        if id(s) in updates:
            d = updates[id(s)]
            new_sessions.append(
                replace(s, day=d, run_time=req.available_days[d.weekday()])
            )
        else:
            new_sessions.append(s)

    return replace(plan, sessions=new_sessions)


# ------------------------------------------------------------- export -----

def _format_segment(seg: Segment) -> str:
    label = "Walk" if seg.effort == Effort.WALK else "Run"
    minutes = int(seg.minutes) if seg.minutes == int(seg.minutes) else seg.minutes
    return f"{label} {minutes} min"


def plan_to_ics(plan: Plan, timezone: str = "Europe/London") -> str:
    """Render the plan's upcoming sessions as .ics calendar text.

    Only sessions still marked PLANNED are exported — done/missed sessions
    are history, not something to add to a calendar. Times are attached to
    `timezone` (and correctly converted to UTC on serialisation) so sessions
    land at the right local time year-round, including across BST/GMT
    changes, rather than being written out as naive/UTC times.
    """
    from zoneinfo import ZoneInfo
    from ics import Calendar, Event

    tz = ZoneInfo(timezone)
    cal = Calendar()
    for s in plan.sessions:
        if s.status != Status.PLANNED:
            continue

        start = datetime.combine(s.day, s.run_time, tzinfo=tz)
        duration_minutes = sum(seg.minutes for seg in s.segments)

        event = Event()
        event.name = f"C25K \u2014 Week {s.week}"
        event.begin = start
        event.duration = timedelta(minutes=duration_minutes)
        event.description = ", ".join(_format_segment(seg) for seg in s.segments)
        cal.events.add(event)

    return cal.serialize()


def export_plan(plan: Plan, path: str) -> None:
    """Write the plan's upcoming sessions to an .ics file at `path`."""
    with open(path, "w") as f:
        f.write(plan_to_ics(plan))


# --------------------------------------------------------- serialization ----
# Converts a Plan to/from plain JSON-safe dicts, so it can be saved to a
# file between CLI runs. GoalConfig is not stored — it's small and fully
# derived from the goal, so it's just looked up again from GOAL_CONFIGS.

import json
import os


def _segment_to_dict(seg: Segment) -> dict:
    return {"effort": seg.effort.value, "minutes": seg.minutes, "repeats": seg.repeats}


def _segment_from_dict(d: dict) -> Segment:
    return Segment(Effort(d["effort"]), d["minutes"], d.get("repeats", 1))


def _session_to_dict(s: Session) -> dict:
    return {
        "day": s.day.isoformat(),
        "run_time": s.run_time.isoformat(),
        "week": s.week,
        "type": s.type.value,
        "segments": [_segment_to_dict(seg) for seg in s.segments],
        "distance_km": s.distance_km,
        "status": s.status.value,
        "is_repeat": s.is_repeat,
    }


def _session_from_dict(d: dict) -> Session:
    return Session(
        day=date.fromisoformat(d["day"]),
        run_time=time.fromisoformat(d["run_time"]),
        week=d["week"],
        type=SessionType(d["type"]),
        segments=[_segment_from_dict(sd) for sd in d["segments"]],
        distance_km=d.get("distance_km"),
        status=Status(d["status"]),
        is_repeat=d.get("is_repeat", False),
    )


def _request_to_dict(req: PlanRequest) -> dict:
    return {
        "goal": req.goal.value,
        "start_date": req.start_date.isoformat(),
        "available_days": {str(k): v.isoformat() for k, v in req.available_days.items()},
        "max_session_minutes": req.max_session_minutes,
        "current_weekly_km": req.current_weekly_km,
        "race_date": req.race_date.isoformat() if req.race_date else None,
    }


def _request_from_dict(d: dict) -> PlanRequest:
    return PlanRequest(
        goal=Goal(d["goal"]),
        start_date=date.fromisoformat(d["start_date"]),
        available_days={int(k): time.fromisoformat(v) for k, v in d["available_days"].items()},
        max_session_minutes=d.get("max_session_minutes", 90),
        current_weekly_km=d.get("current_weekly_km", 0.0),
        race_date=date.fromisoformat(d["race_date"]) if d.get("race_date") else None,
    )


def plan_to_dict(plan: Plan) -> dict:
    return {
        "request": _request_to_dict(plan.request),
        "sessions": [_session_to_dict(s) for s in plan.sessions],
    }


def plan_from_dict(d: dict) -> Plan:
    req = _request_from_dict(d["request"])
    config = GOAL_CONFIGS[req.goal]
    sessions = [_session_from_dict(sd) for sd in d["sessions"]]
    return Plan(request=req, config=config, sessions=sessions)


def save_plan(plan: Plan, path: str = "plan.json") -> None:
    with open(path, "w") as f:
        json.dump(plan_to_dict(plan), f, indent=2)


def load_plan(path: str = "plan.json") -> Plan | None:
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return plan_from_dict(json.load(f))