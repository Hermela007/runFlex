from datetime import date

import cli
from plan_model import Status
from test_plan_model import make_plan


def run_mark_flow(monkeypatch, tmp_path, answers):
    monkeypatch.chdir(tmp_path)  # save/export write next to the cwd
    replies = iter(answers)
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(replies))
    plan = make_plan()
    return plan, cli.mark_session_flow(plan)


def test_cli_refuses_to_log_sessions_out_of_order(monkeypatch, tmp_path):
    """Regression test: the CLI replans with `today` = the logged session's
    date. Logging session 2 before session 1 moved "today" backwards, which
    left session 1 stranded in the past and let later replans place repeat
    weeks around sessions that were already logged.
    """
    plan, result = run_mark_flow(monkeypatch, tmp_path, ["2", "m"])

    assert result is plan
    assert all(s.status == Status.PLANNED for s in plan.sessions)


def test_cli_rejects_session_number_zero(monkeypatch, tmp_path):
    """Regression test: entering "0" became index -1, which silently
    selected the *last* session in the plan instead of being rejected.
    """
    plan, result = run_mark_flow(monkeypatch, tmp_path, ["0", "m"])

    assert result is plan
    assert all(s.status == Status.PLANNED for s in plan.sessions)


def test_cli_logs_the_first_session(monkeypatch, tmp_path):
    plan, result = run_mark_flow(monkeypatch, tmp_path, ["1", "d"])

    first = min(result.sessions, key=lambda s: s.day)
    assert first.day == date(2026, 10, 5)
    assert first.status == Status.DONE
    assert (tmp_path / "plan.json").exists()
