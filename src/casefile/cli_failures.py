"""Issue 14: what kind of failure a terminal call had, read from the reason
and the CLI's own text. Plumbing only: it routes the Case (wait, stop, retry),
it never judges title content.

- login: no subscription login, or the official CLI is missing;
- limit: the subscription's usage or rate limit;
- invalid_output: the CLI answered, but not in the contract;
- crash: anything else, timeouts included.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

CLASSES = ("login", "limit", "invalid_output", "crash")
DEFAULT_WAIT = timedelta(minutes=30)
MAX_WAIT = timedelta(hours=12)

_LOGIN = re.compile(
    r"terminal_subscription_login_required|terminal_not_installed|provider_not_called|"
    r"not logged in|please run /login|login required|authentication[_ ](error|failed)|"
    r"unauthori[sz]ed|invalid api key|oauth token|\b401\b", re.I)
_LIMIT = re.compile(
    r"usage limit|rate[_ ]limit|limit reached|hit your (usage )?limit|quota|"
    r"too many requests|overloaded|\b429\b|\b529\b", re.I)
_INVALID = re.compile(
    r"terminal_output_invalid|terminal_tool_contract_invalid|"
    r"terminal_unexpected_native_tool|error_max_turns", re.I)


def classify(reason: str, text: str = "") -> str:
    blob = f"{reason}\n{text}"
    if _LOGIN.search(blob):
        return "login"
    if _LIMIT.search(blob):
        return "limit"
    if _INVALID.search(blob):
        return "invalid_output"
    return "crash"


def resume_at(text: str, now: datetime | None = None) -> datetime:
    """When a limited subscription can be tried again: the reset the CLI
    printed (an epoch after '|', or 'try again in N hours M minutes'), else
    30 minutes; never more than 12 hours ahead."""
    now = now or datetime.now(timezone.utc)
    found = None
    epoch = re.search(r"\|(\d{10})\b", text)
    if epoch:
        found = datetime.fromtimestamp(int(epoch.group(1)), timezone.utc)
    else:
        relative = re.search(r"try again in\s+(?:(\d+)\s*hours?)?\s*(?:(\d+)\s*min)?", text, re.I)
        if relative and (relative.group(1) or relative.group(2)):
            found = now + timedelta(hours=int(relative.group(1) or 0),
                                    minutes=int(relative.group(2) or 0))
    if found is None or found <= now:
        found = now + DEFAULT_WAIT
    return min(found, now + MAX_WAIT)
