from datetime import date, time
from plan_model import (PlanRequest, Goal, validate_request, generate_plan,
                        Effort, Status, replan, plan_to_ics, export_plan)

DAYS = {0: time(7, 0), 2: time(7, 0), 4: time(7, 0)}  # Mon/Wed/Fri


def make_plan():
    return generate_plan(PlanRequest(
        goal=Goal.C25K, start_date=date(2026, 10, 5), available_days=dict(DAYS)))


def test_rejects_too_few_available_days():
    request = PlanRequest(goal=Goal.C25K, start_date=date(2026, 10, 5),
                          available_days={0: time(7, 0), 1: time(7, 0)})
    assert len(validate_request(request)) > 0


def test_generates_27_sessions_on_available_days():
    plan = make_plan()
    assert len(plan.sessions) == 27
    for s in plan.sessions:
        assert s.day.weekday() in plan.request.available_days


def test_week_one_is_run_walk_intervals():
    plan = make_plan()
    week_one = [s for s in plan.sessions if s.week == 1]
    assert len(week_one) == 3
    first = week_one[0]
    assert first.segments[0].effort == Effort.WALK
    assert first.segments[0].minutes == 5.0
    assert first.segments[1].effort == Effort.EASY
    assert first.segments[1].minutes == 1.0
    assert first.segments[-1].effort == Effort.WALK
    assert first.segments[-1].minutes == 5.0


def test_single_miss_shifts_remaining_sessions_in_week():
    plan = make_plan()
    week_one = [s for s in plan.sessions if s.week == 1]
    week_one[0].status = Status.MISSED
    updated_plan = replan(plan, today=date(2026, 10, 6))
    assert plan.sessions[0].status == Status.MISSED
    new_week_one = [s for s in updated_plan.sessions if s.week == 1]
    remaining = [s for s in new_week_one if s.status == Status.PLANNED]
    assert remaining[0].day == date(2026, 10, 7)
    assert remaining[1].day == date(2026, 10, 9)


def test_three_misses_repeats_the_week():
    plan = make_plan()
    for s in [s for s in plan.sessions if s.week == 1]:
        s.status = Status.MISSED
    updated_plan = replan(plan, today=date(2026, 10, 12))
    assert sorted(set(s.week for s in updated_plan.sessions)) == list(range(1, 11))
    assert len(updated_plan.sessions) == 30
    history = [s for s in updated_plan.sessions if s.week == 1]
    assert all(s.status == Status.MISSED for s in history)
    repeated = [s for s in updated_plan.sessions if s.week == 2]
    assert all(s.status == Status.PLANNED for s in repeated)
    assert repeated[0].day == date(2026, 10, 12)
    assert repeated[0].segments == history[0].segments


def test_two_misses_then_another_miss_repeats_latest_week():
    plan = make_plan()
    week_one = [s for s in plan.sessions if s.week == 1]
    week_one[0].status = Status.MISSED
    week_one[1].status = Status.MISSED
    week_one[2].status = Status.DONE
    week_two_before = [s for s in plan.sessions if s.week == 2]
    week_two_before[0].status = Status.DONE
    week_two_before[1].status = Status.MISSED

    updated = replan(plan, today=date(2026, 10, 15))

    assert sorted(set(s.week for s in updated.sessions)) == list(range(1, 11))
    assert len(updated.sessions) == 29
    week_two = [s for s in updated.sessions if s.week == 2]
    assert [s.status for s in week_two] == [Status.DONE, Status.MISSED]
    repeated = [s for s in updated.sessions if s.week == 3]
    assert len(repeated) == 3
    assert all(s.status == Status.PLANNED for s in repeated)
    assert repeated[0].day == date(2026, 10, 16)
    assert repeated[0].segments == week_two[0].segments


def test_two_misses_then_missed_first_session_repeats_earlier_week():
    plan = make_plan()
    week_one = [s for s in plan.sessions if s.week == 1]
    week_one[0].status = Status.MISSED
    week_one[1].status = Status.MISSED
    week_one[2].status = Status.DONE
    week_two_before = [s for s in plan.sessions if s.week == 2]
    week_two_before[0].status = Status.MISSED  # Mon 10/12 missed; 10/14, 10/16 unrun

    updated = replan(plan, today=date(2026, 10, 13))  # Tuesday

    # Two extra weeks: week 1 again, then week 2 again
    assert sorted(set(s.week for s in updated.sessions)) == list(range(1, 12))
    assert len(updated.sessions) == 31  # 27 - 2 dropped + 6 repeated

    week_two = [s for s in updated.sessions if s.week == 2]
    assert [s.status for s in week_two] == [Status.MISSED]

    week_three = [s for s in updated.sessions if s.week == 3]  # repeat of week 1
    assert all(s.status == Status.PLANNED for s in week_three)
    assert week_three[0].day == date(2026, 10, 14)
    assert week_three[0].segments == week_one[0].segments

    week_four = [s for s in updated.sessions if s.week == 4]  # week 2 from scratch
    assert len(week_four) == 3
    assert week_four[0].segments == week_two[0].segments


def test_replan_is_idempotent():
    plan = make_plan()
    week_one = [s for s in plan.sessions if s.week == 1]
    week_one[0].status = Status.MISSED
    week_one[1].status = Status.MISSED
    week_one[2].status = Status.DONE
    plan.sessions[3].status = Status.DONE
    plan.sessions[4].status = Status.MISSED
    once = replan(plan, today=date(2026, 10, 15))
    twice = replan(once, today=date(2026, 10, 15))
    assert once == twice


def test_export_produces_valid_ics_for_planned_sessions_only():
    from ics import Calendar

    plan = make_plan()
    # Mark the very first session as done -> it should NOT appear in the export
    plan.sessions[0].status = Status.DONE

    ics_text = plan_to_ics(plan)

    # It's valid .ics text the `ics` library can parse back
    parsed = Calendar(ics_text)

    planned_count = sum(1 for s in plan.sessions if s.status == Status.PLANNED)
    assert len(parsed.events) == planned_count

    titles = {e.name for e in parsed.events}
    assert "C25K \u2014 Week 1" in titles

    # Spot-check one event's timing and duration
    first_planned = next(s for s in plan.sessions if s.status == Status.PLANNED)
    matching = [e for e in parsed.events if e.begin.to('Europe/London').date() == first_planned.day]
    assert len(matching) == 1
    event = matching[0]
    assert event.begin.to('Europe/London').time().hour == first_planned.run_time.hour
    expected_minutes = sum(seg.minutes for seg in first_planned.segments)
    assert event.duration.total_seconds() / 60 == expected_minutes


def test_export_times_are_correct_in_utc_across_bst_and_gmt():
    from ics import Calendar

    # 5 Oct 2026 is BST (UTC+1); week 9 lands in late Nov/Dec, GMT (UTC+0)
    request = PlanRequest(
        goal=Goal.C25K,
        start_date=date(2026, 10, 5),
        available_days={0: time(7, 0), 2: time(7, 0), 4: time(7, 0)},
    )
    plan = generate_plan(request)
    parsed = Calendar(plan_to_ics(plan))

    week_one_event = next(
        e for e in parsed.events if e.begin.date() == date(2026, 10, 5)
    )
    # 7am BST (UTC+1) on 5 Oct 2026 -> 6am UTC
    assert week_one_event.begin.to('utc').hour == 6

    late_session = next(s for s in plan.sessions if s.week == 9)
    late_event = next(
        e for e in parsed.events if e.begin.date() == late_session.day
    )
    # Late in the plan the UK has switched to GMT (UTC+0) -> 7am UTC
    assert late_event.begin.to('utc').hour == 7