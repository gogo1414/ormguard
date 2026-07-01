"""CLI smoke tests (no external DB required)."""

from __future__ import annotations

from ormguard.cli import main


def test_selfcheck_warn_only_exits_zero(capsys):
    # --selfcheck deliberately finds drift; --warn-only keeps the exit code 0.
    assert main(["--selfcheck", "--warn-only"]) == 0
    out = capsys.readouterr().out
    assert "selfcheck" in out


def test_force_utf8_output_is_safe_when_unsupported():
    # Should never raise, even if the stream can't be reconfigured.
    from ormguard.cli import _force_utf8_output

    _force_utf8_output()
