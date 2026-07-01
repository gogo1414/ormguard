"""Best-effort webhook notification, compatible with Slack and Discord.

One payload carries both ``text`` (Slack) and ``content`` (Discord); each
service reads its own key and ignores the other, so a single URL works for both.
"""

from __future__ import annotations

import json
import urllib.request

from .model import ValidationReport

_MAX_BODY = 1500


def build_message(report: ValidationReport) -> str:
    label = f"[{report.label}] " if report.label else ""
    head = (
        f":rotating_light: ormguard {label}found "
        f"{len(report.errors)} error(s), {len(report.warnings)} warning(s)"
    )
    body = report.format_text()
    if len(body) > _MAX_BODY:
        body = body[:_MAX_BODY] + "\n… (truncated)"
    return f"{head}\n```\n{body}\n```"


def notify_webhook(url: str, report: ValidationReport, *, timeout: float = 10.0) -> bool:
    """POST the report to a Slack- or Discord-style incoming webhook.

    Returns True on success. Never raises — notification is a side effect and
    must not fail the validation run.
    """
    message = build_message(report)
    payload = json.dumps({"text": message, "content": message}).encode("utf-8")
    request = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        urllib.request.urlopen(request, timeout=timeout)
        return True
    except Exception:
        return False
