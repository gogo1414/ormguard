"""Webhook notification: message shape, dual Slack/Discord payload, best-effort."""

from __future__ import annotations

import json

from ormguard.model import COLUMN_MISSING, Finding, Severity, ValidationReport
from ormguard.notify import build_message, notify_webhook


def _report():
    return ValidationReport(
        findings=[Finding(Severity.ERROR, COLUMN_MISSING, "users", column="nickname")]
    )


def test_build_message_has_counts_and_body():
    msg = build_message(_report())
    assert "1 error(s)" in msg
    assert "column_missing" in msg


def test_notify_webhook_sends_slack_and_discord_keys(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["body"] = request.data
        return object()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    assert notify_webhook("https://hooks.example/abc", _report()) is True
    payload = json.loads(captured["body"])
    assert "text" in payload and "content" in payload      # Slack + Discord
    assert payload["text"] == payload["content"]
    assert captured["url"] == "https://hooks.example/abc"


def test_notify_webhook_never_raises(monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("network down")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    assert notify_webhook("https://bad.example", ValidationReport()) is False
