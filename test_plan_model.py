from datetime import date, time
from plan_model import PlanRequest, Goal, validate_request, generate_plan, Effort, Status, replan


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


def test_single_miss_shifts_remaining_sessions_in_week():
    request = PlanRequest(
        goal=Goal.C25K,
        start_date=date(2026, 10, 5),  # Monday
        available_days={0: time(7, 0), 2: time(7, 0), 4: time(7, 0)},  # Mon/Wed/Fri
    )
    plan = generate_plan(request)

    # Week 1 sessions: Mon 10/5, Wed 10/7, Fri 10/9
    week_one = [s for s in plan.sessions if s.week == 1]
    week_one[0].status = Status.MISSED  # missed Monday's run

    updated_plan = replan(plan, today=date(2026, 10, 6))  # Tuesday

    new_week_one = [s for s in updated_plan.sessions if s.week == 1]
    remaining_planned = [s for s in new_week_one if s.status == Status.PLANNED]

    # The two remaining sessions should now be on the next two available
    # days from today onward: Wed 10/7 and Fri 10/9 stay as-is here, since
    # they were already the next two available slots.
    assert remaining_planned[0].day == date(2026, 10, 7)
    assert remaining_planned[1].day == date(2026, 10, 9)