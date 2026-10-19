"""Issue 14: the class of a failed terminal call is read from its reason and
the CLI's text. Synthetic texts only; plumbing, not title."""
from datetime import datetime, timedelta, timezone

import pytest

from src.casefile import cli_failures


@pytest.mark.parametrize("reason,text,kind", [
    ("terminal_subscription_login_required:A", "", "login"),
    ("terminal_not_installed:B", "", "login"),
    ("terminal_failed_requires_review:A", '{"result": "Not logged in · Please run /login"}', "login"),
    ("terminal_failed_requires_review:A", '{"result": "Claude AI usage limit reached|1760000000"}', "limit"),
    ("terminal_failed_requires_review:B", '{"type": "turn.failed", "error": {"message": "You\'ve hit your usage limit"}}', "limit"),
    ("terminal_failed_requires_review:B", "stream error: 429 Too Many Requests", "limit"),
    ("terminal_output_invalid", "", "invalid_output"),
    ("terminal_failed_requires_review:A", '{"subtype": "error_max_turns", "is_error": true}', "invalid_output"),
    ("terminal_timeout_requires_review", "", "crash"),
    ("terminal_failed_requires_review:A", "segmentation fault (core dumped); 4290 tokens", "crash"),
])
def test_failure_class_from_reason_and_cli_text(reason, text, kind):
    assert cli_failures.classify(reason, text) == kind


def test_resume_time_from_the_cli_text_or_a_bounded_default():
    now = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
    reset = now + timedelta(hours=2)
    assert cli_failures.resume_at(f"usage limit reached|{int(reset.timestamp())}", now) == reset
    assert cli_failures.resume_at("Try again in 1 hour 15 minutes.", now) == now + timedelta(minutes=75)
    assert cli_failures.resume_at("rate limit", now) == now + cli_failures.DEFAULT_WAIT
    far = now + timedelta(days=3)
    assert cli_failures.resume_at(f"limit|{int(far.timestamp())}", now) == now + cli_failures.MAX_WAIT
