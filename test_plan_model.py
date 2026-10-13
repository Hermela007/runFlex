from datetime import date, time
from plan_model import PlanRequest, Goal, validate_request, generate_plan, Effort


def test_rejects_too_few_available_days():
    request = PlanRequest(
        goal=Goal.C25K,
        start_date=date(2026, 10, 5),
        available_days={0: time(7, 0), 1: time(7, 0)},  # only Monday and Tuesday — 2 days, need 3
    )

    problems = validate_request(request)

    assert len(problems) > 0


def test_generates_27_sessions_on_available_days():
    request = PlanRequest(
        goal=Goal.C25K,
        start_date=date(2026, 10, 5),  # a Monday
        available_days={0: time(7, 0), 2: time(7, 0), 4: time(7, 0)},  # Mon/Wed/Fri
    )

    plan = generate_plan(request)

    assert len(plan.sessions) == 27  # 9 weeks x 3 sessions
    for session in plan.sessions:
        assert session.day.weekday() in request.available_days


def test_week_one_is_run_walk_intervals():
    request = PlanRequest(
        goal=Goal.C25K,
        start_date=date(2026, 10, 5),
        available_days={0: time(7, 0), 2: time(7, 0), 4: time(7, 0)},
    )

    plan = generate_plan(request)
    week_one_sessions = [s for s in plan.sessions if s.week == 1]

    assert len(week_one_sessions) == 3
    first_session = week_one_sessions[0]
    assert first_session.segments[0].effort == Effort.WALK  # warm-up
    assert first_session.segments[0].minutes == 5.0
    assert first_session.segments[1].effort == Effort.EASY  # first run
    assert first_session.segments[1].minutes == 1.0
    assert first_session.segments[-1].effort == Effort.WALK  # cool-down
    assert first_session.segments[-1].minutes == 5.0