# runFlex

A personalised Couch-to-5K training plan generator — built because I wanted
a Runna/NHS-style running app, but one that actually plans around *my*
real weekly schedule rather than handing me a fixed template, and without
a subscription.

The interesting part is the scheduling engine, not the UI. It's deliberately
built so the logic (plan generation, rescheduling after a missed run) is a
small set of pure, fully-tested Python functions with no framework,
database, or UI dependency.

## What it does

- Generates a 9-week Couch-to-5K plan (sourced from the
  [NHS's official Couch to 5K programme](https://www.nhs.uk/better-health/get-active/get-running-with-couch-to-5k/couch-to-5k-running-plan/)),
  placed onto the specific weekdays and times you say you're free —
  not a generic Monday/Wednesday/Friday assumption.
- Tracks each session as `planned`, `done`, or `missed`, and
  **re-plans itself** when you miss a run, following three escalation
  tiers (see below) rather than just silently dropping the miss.
- Exports your plan to a standard `.ics` calendar file you can import
  into Google Calendar, Apple Calendar, or Outlook — with run times
  correctly handled across the BST/GMT clock change.
- A simple interactive CLI to create a plan, mark sessions done/missed,
  and re-export the calendar, with your plan persisted to disk between
  runs.

## Why

Most beginner running apps (NHS Couch to 5K, Runna, etc.) assume a fixed
weekly rhythm and don't really adapt when real life gets in the way of a
training week. I wanted to build the scheduling logic myself, working
around my own availability rather than a generic template.

## The missed-session logic

This is the part of the project I'd point to first. Based loosely on how
Runna's "Plan Realignment" feature behaves, missed sessions are handled
in three tiers rather than one blanket rule:

| Situation | What happens |
|---|---|
| **1 session missed** in a week | The rest of that week's sessions shift onto the next available days. The week isn't extended. |
| **2 sessions missed** in a week | Same shift as above, but the week is flagged "at risk." |
| **A miss in the week right after an at-risk week** | If that week's *first* session was the one missed, the earlier at-risk week repeats, followed by a fresh restart of this week (plan grows by 2 weeks). Otherwise, this week alone repeats (plan grows by 1 week). |
| **3+ sessions missed** in any single week | That week repeats immediately, regardless of what happened before or after it. |

A few design choices worth calling out:

- **The engine is a pure function.** `generate_plan()` and `replan()`
  take a request/plan and return a new one — no hidden state, no I/O, no
  wall-clock reads. This makes the whole thing trivially testable and
  means calling `replan()` twice with nothing new to react to is a
  no-op (verified by a dedicated idempotency test).
- **Sessions that haven't happened yet are dropped, not duplicated,**
  when a week repeats — you don't end up doing a missed week's leftover
  runs *and* the full repeat back to back.
- **Calendar-date collisions are explicitly guarded against.** An
  earlier version of the rescheduling logic picked a free weekday
  without checking whether that *exact date* was already taken by
  another session in the plan — which caused a real, reproducible bug
  when replanning on the same day a session was marked missed. Fixed
  by passing an explicit set of "taken" dates into the date-picker and
  covered by a regression test (`test_replan_on_the_missed_days_own_date_does_not_collide`).
- **Sessions are logged one at a time, in date order.** The CLI enforces
  this because `replan()` uses the logged session's own date as "today" —
  logging out of order would move that reference point backwards and
  misplace repeat weeks around sessions that are already logged.

## Project structure

```
plan_model.py       # the engine: data model, generate_plan, replan, .ics export, JSON persistence
cli.py               # interactive terminal front end built on top of plan_model.py
test_plan_model.py   # pytest suite covering generation, every replan tier, export, and persistence
test_cli.py          # pytest suite covering the CLI's session-logging rules
```

`plan_model.py` has no dependency on `cli.py` or the terminal at all — it
could sit behind a web API or a different front end without changes.

## Getting started

```bash
git clone https://github.com/Hermela007/runFlex.git
cd runFlex
python3 -m venv venv
source venv/bin/activate        # on Windows: venv\Scripts\activate
pip install pytest ics
```

Run the tests:

```bash
pytest -v
```

Run the CLI:

```bash
python3 cli.py
```

The CLI will walk you through creating a plan (start date, which
weekdays you're free and at what time), then lets you mark sessions
done or missed and re-export the calendar at any point.

## Example

```
> 1
--- New C25K plan ---
Start date (YYYY-MM-DD): 2026-10-05
Which days can you run? 0,2,4
  Time on Monday: 07:00
  Time on Wednesday: 07:00
  Time on Friday: 07:00

Plan created: 27 sessions over 9 weeks.
Saved to plan.json and exported to c25k_plan.ics.
```

Importing the resulting `c25k_plan.ics` into a calendar app gives you a
run of correctly-timed events, each with the week's walk/run structure
in the description.

## Tech stack

- **Python** — the whole engine, CLI, and tests.
- **pytest** — the entire logic (plan generation, all three replan
  tiers, calendar export, JSON round-tripping) is covered by automated
  tests, not just manually checked.
- **[`ics`](https://pypi.org/project/ics/)** — RFC 5545 calendar file
  generation, rather than hand-rolling the `.ics` format.
- **Standard library only otherwise** — `dataclasses`, `enum`,
  `datetime`/`zoneinfo`, and `json` for persistence. No framework, no
  database.

## Roadmap

- Read availability directly from Google Calendar instead of manual input
- Distance-based plans beyond C25K (10K, half marathon, marathon)
