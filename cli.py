"""Interactive command-line front end for the C25K plan engine.

Generates a plan, lets you mark sessions as done/missed (replanning
automatically), and exports the current plan to an .ics file. All the
real logic lives in plan_model.py — this file is just the terminal menu.
"""

from datetime import date, time

from plan_model import (
    PlanRequest, Goal, Status, validate_request, generate_plan, replan,
    plan_to_ics, export_plan, save_plan, load_plan,
)

PLAN_FILE = "plan.json"
ICS_FILE = "c25k_plan.ics"

WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday",
                 "Friday", "Saturday", "Sunday"]


def prompt_date(label: str) -> date:
    while True:
        raw = input(f"{label} (YYYY-MM-DD): ").strip()
        try:
            return date.fromisoformat(raw)
        except ValueError:
            print("  Please enter a date like 2026-10-05.")


def prompt_time(label: str) -> time:
    while True:
        raw = input(f"{label} (HH:MM, 24-hour): ").strip()
        try:
            hour, minute = (int(x) for x in raw.split(":"))
            return time(hour, minute)
        except ValueError:
            print("  Please enter a time like 07:00 or 18:30.")


def prompt_available_days() -> dict[int, time]:
    print("\nWhich days can you run? Enter day numbers separated by")
    print("commas (0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun).")
    print("C25K needs at least 3 days a week.")
    while True:
        raw = input("Days: ").strip()
        try:
            day_numbers = sorted({int(x) for x in raw.split(",")})
        except ValueError:
            print("  Please enter numbers like: 0,2,4")
            continue
        if any(d < 0 or d > 6 for d in day_numbers):
            print("  Day numbers must be 0 through 6.")
            continue
        break

    available_days: dict[int, time] = {}
    for d in day_numbers:
        run_time = prompt_time(f"  Time on {WEEKDAY_NAMES[d]}")
        available_days[d] = run_time
    return available_days


def new_plan_flow() -> None:
    print("\n--- New C25K plan ---")
    start = prompt_date("Start date")
    available_days = prompt_available_days()

    request = PlanRequest(goal=Goal.C25K, start_date=start,
                          available_days=available_days)
    problems = validate_request(request)
    if problems:
        print("\nCan't build this plan:")
        for p in problems:
            print(f"  - {p}")
        return

    plan = generate_plan(request)
    save_plan(plan, PLAN_FILE)
    export_plan(plan, ICS_FILE)
    print(f"\nPlan created: {len(plan.sessions)} sessions over "
          f"{plan.config.weeks} weeks.")
    print(f"Saved to {PLAN_FILE} and exported to {ICS_FILE}.")


def list_upcoming(plan) -> None:
    upcoming = [s for s in plan.sessions if s.status == Status.PLANNED]
    upcoming.sort(key=lambda s: s.day)
    if not upcoming:
        print("\nNo upcoming sessions.")
        return
    print("\nUpcoming sessions:")
    for i, s in enumerate(upcoming, 1):
        print(f"  {i}. {s.day} ({WEEKDAY_NAMES[s.day.weekday()]}) "
              f"{s.run_time.strftime('%H:%M')} — Week {s.week}")


def mark_session_flow(plan):
    upcoming = [s for s in plan.sessions if s.status == Status.PLANNED]
    upcoming.sort(key=lambda s: s.day)
    if not upcoming:
        print("\nNo upcoming sessions to mark.")
        return plan

    list_upcoming(plan)
    raw = input("\nWhich session number did you run or miss? ").strip()
    try:
        index = int(raw) - 1
        if index < 0:  # "0" or "-1" would otherwise wrap to the end of the list
            raise IndexError
        session = upcoming[index]
    except (ValueError, IndexError):
        print("  Not a valid session number.")
        return plan
    # replan uses the logged session's date as "today", so logging out of
    # order would move "today" backwards and place repeats around sessions
    # that are already logged.
    if index != 0:
        first = upcoming[0]
        print(f"  Please log session 1 ({first.day}) first — sessions are "
              f"logged in date order.")
        return plan

    outcome = input("Mark as (d)one or (m)issed? ").strip().lower()
    if outcome not in ("d", "m"):
        print("  Please enter 'd' or 'm'.")
        return plan
    session.status = Status.DONE if outcome == "d" else Status.MISSED

    today = session.day
    plan = replan(plan, today=today)
    save_plan(plan, PLAN_FILE)
    export_plan(plan, ICS_FILE)
    print(f"\nUpdated. Plan re-exported to {ICS_FILE}.")
    return plan


def main() -> None:
    print("=== C25K Plan Generator ===")
    plan = load_plan(PLAN_FILE)
    if plan:
        print(f"Loaded existing plan ({len(plan.sessions)} sessions).")

    while True:
        print("\n1. New plan")
        print("2. View upcoming sessions")
        print("3. Mark a session done/missed")
        print("4. Export calendar (.ics) again")
        print("5. Quit")
        choice = input("> ").strip()

        if choice == "1":
            new_plan_flow()
            plan = load_plan(PLAN_FILE)
        elif choice == "2":
            if plan:
                list_upcoming(plan)
            else:
                print("\nNo plan yet — start with option 1.")
        elif choice == "3":
            if plan:
                plan = mark_session_flow(plan)
            else:
                print("\nNo plan yet — start with option 1.")
        elif choice == "4":
            if plan:
                export_plan(plan, ICS_FILE)
                print(f"\nExported to {ICS_FILE}.")
            else:
                print("\nNo plan yet — start with option 1.")
        elif choice == "5":
            print("Bye — good luck with the training.")
            break
        else:
            print("  Please choose 1-5.")


if __name__ == "__main__":
    main()