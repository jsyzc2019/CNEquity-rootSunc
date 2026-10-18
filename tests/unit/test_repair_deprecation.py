"""One-time migration repairs say they are going before they go.

Each is kept for two minor releases so a lake written by 0.17 or earlier can
still run it. The warning must reach stderr, never stdout: callers parse the
JSON report a repair prints.
"""

from __future__ import annotations

import json

from click.testing import CliRunner

from cnequity.cli import repair_cmds
from cnequity.cli.main import cli

MIGRATIONS = {
    "missing-values",
    "financial-announcements",
    "fund-factors",
    "daily-bar-coverage",
    "fund-listing-dates",
    "valuation-basis",
    "orphan-symbols",
    "stale-suspensions",
    "status-outages",
    "status-listing-window",
    "misdated-valuation",
}


def test_exactly_the_one_time_migrations_are_deprecated():
    deprecated = {
        name
        for name, command in repair_cmds.repair.commands.items()
        if isinstance(command, repair_cmds.DeprecatedMigration)
    }
    assert deprecated == MIGRATIONS


def test_help_marks_deprecated_commands_and_names_the_removal():
    listing = CliRunner().invoke(cli, ["repair", "--help"]).output
    rows = {line.split()[0]: line for line in listing.splitlines() if line.startswith("  ")}
    assert "[deprecated]" in rows["orphan-symbols"]
    assert "[deprecated]" not in rows["layout"]

    page = CliRunner().invoke(cli, ["repair", "orphan-symbols", "--help"]).output
    assert "removed in 0.20.0" in " ".join(page.split())


def test_run_warns_on_stderr_and_keeps_stdout_json(monkeypatch):
    import cnequity.storage.repairs.orphan_symbols as module

    monkeypatch.setattr(repair_cmds, "_cfg", lambda path: object())
    monkeypatch.setattr(module, "repair_orphan_symbols", lambda config, apply: {"applied": apply})

    result = CliRunner().invoke(cli, ["repair", "orphan-symbols"], prog_name="cne")

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {"applied": False}
    assert "`cne repair orphan-symbols` is deprecated" in result.stderr
    assert "0.20.0" in result.stderr
