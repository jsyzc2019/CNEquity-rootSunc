"""Scheduled operation: `run maintain` and `schedule install|status|remove`.

One implementation of "keep this lake current" for every install. The timer is
the packaged one the dashboard already used (`cnequity.serve.ops.scheduled`:
launchd, cron or Task Scheduler for the current user, checked once a minute),
and the work after the day's update — checking it, backing up the metadata,
previewing expiry — is `cne run maintain` rather than a shell script only a
repository checkout had.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import click

from cnequity.cli._root import cli, run
from cnequity.cli._shared import _cfg, attach_log_file, config_option, resolve_config_path
from cnequity.domain.market_time import shanghai_today
from cnequity.i18n import N_, _

#: (label, `cne` arguments, whether a failure makes the day unhealthy).
#: Probes, SLO and run evidence are observations about sources and history,
#: not about today's data, so they report without failing the run.
_CHECKS: tuple[tuple[str, tuple[str, ...], bool], ...] = (
    (N_("Freshness gate"), ("status", "--datasets", "--gate"), True),
    (N_("Source probes"), ("sources", "probe", "--stale-only"), False),
    (N_("Source SLO"), ("sources", "slo"), False),
    (N_("Run evidence, last 20 sessions"), ("verify", "--runs", "--days", "20"), False),
)

# Legacy launchd jobs from scripts/scheduler; running both doubles every fetch.
_LEGACY_LAUNCHD = (
    "com.cnequity.daily",
    "com.cnequity.stale",
    "com.cnequity.events",
    "com.cnequity.events-news",
)


def _cne(*args: str) -> list[str]:
    return [sys.executable, "-X", "utf8", "-m", "cnequity", *args]


def _scheduled_groups(cfg) -> list[str]:
    """The groups the scheduled update runs: its research packs', else all of them."""
    try:
        from cnequity.research.packs import groups_for
        from cnequity.serve.ops.scheduler import settings

        packs = settings(cfg).get("daily_packs") or []
    except Exception:  # noqa: BLE001 — no timer settings means the plain daily update
        packs = []
    if packs:
        return [group for group in groups_for(packs) if group in cfg.schedule_groups]
    return list(cfg.schedule_groups)


def _notify(title: str, message: str) -> None:
    """A desktop notification on macOS; nothing elsewhere."""
    if sys.platform != "darwin":
        return
    script = f"display notification {json.dumps(message)} with title {json.dumps(title)}"
    try:
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        pass


@run.command("maintain")
@config_option
@click.option(
    "--groups",
    default=None,
    help=N_(
        "Schedule groups the freshness gate fails on (space- or comma-separated). Default: the "
        "groups the scheduled update runs."
    ),
)
@click.option(
    "--notify", is_flag=True, help=N_("On problems, also show a desktop notification (macOS).")
)
def maintain(config_path: str, groups: str | None, notify: bool):
    """Check the day's update, back up what cannot be rebuilt, and preview expiry.

    \b
    The scheduled timer runs this once after each session's daily update. In order:
    the run audit (the whole lake on [job.maintenance].full_audit_weekday), the freshness gate,
    source probes and SLO, run evidence over 20 sessions, a metadata backup
    (manifest DB, receipts, quality findings; never curated Parquet), and `cne run clean`'s preview.
    Exits 1 when the audit, the freshness gate or the backup fails; source and run-evidence
    findings are reported without failing.

    """
    from cnequity.storage.meta_backup import backup_meta

    cfg = _cfg(config_path)
    attach_log_file(cfg, "run-maintain")
    path = str(resolve_config_path(config_path).resolve())
    weekday = cfg.maintenance_full_audit_weekday
    full = bool(weekday) and shanghai_today().isoweekday() == weekday
    audit = (
        (N_("Whole-lake audit"), ("audit", "--full", "--quality-only"), True)
        if full
        else (N_("Run audit"), ("audit",), True)
    )
    gate_groups = groups if groups is not None else " ".join(_scheduled_groups(cfg))
    problems: list[str] = []
    notes: list[str] = []
    for label, args, gating in (audit, *_CHECKS):
        argv = list(args)
        if args[0] == "status" and gate_groups:
            argv += ["--groups", gate_groups]
        click.echo(f"--- {_(label)} ---", err=True)
        if subprocess.run(_cne(*argv, "--config", path), check=False).returncode:
            (problems if gating else notes).append(_(label))

    click.echo(f"--- {_('Metadata backup')} ---", err=True)
    try:
        result = backup_meta(
            cfg.meta_root,
            cfg.backup_root,
            retention_days=cfg.maintenance_backup_retention_days,
            retention_count=cfg.maintenance_backup_retention_count,
        )
        click.echo(
            _("Wrote {archive} ({size:,} bytes); {kept} archives kept, {removed} removed.").format(
                archive=result.archive,
                size=result.size_bytes,
                kept=result.kept,
                removed=len(result.removed),
            ),
            err=True,
        )
    except (OSError, ValueError) as exc:
        click.echo(_("Metadata backup failed: {exc}").format(exc=exc), err=True)
        problems.append(_("Metadata backup"))

    click.echo(f"--- {_('Expiry preview')} ---", err=True)
    if subprocess.run(_cne("run", "clean", "--config", path), check=False).returncode:
        notes.append(_("Expiry preview"))

    if notes:
        click.echo(_("Reported, not failing: {names}").format(names=", ".join(notes)), err=True)
    if problems:
        summary = ", ".join(problems)
        click.echo(_("Maintenance found problems: {names}").format(names=summary), err=True)
        if notify:
            _notify(_("cnequity maintenance"), _("Problems: {names}").format(names=summary))
        raise SystemExit(1)
    click.echo(_("Maintenance OK."), err=True)


@cli.group()
def schedule():
    """Install, inspect or remove this lake's scheduled daily update.

    \b
    The timer belongs to the current user (launchd on macOS, cron on Linux, Task Scheduler
    on Windows) and checks once a minute. Each trading day, once [job.daily].run_at
    (Beijing time) has passed, it runs `cne run daily`, then `cne run maintain`; after
    [job.stale].run_at it retries the snapshots the day missed. It is the same timer the
    dashboard's operations page manages, so either place shows and changes it.

    """


def _service(config_path: str):
    from cnequity.serve.ops.catalog import OpsError
    from cnequity.serve.ops.scheduler import ScheduleService

    try:
        return ScheduleService(_cfg(config_path))
    except OpsError as exc:
        raise click.ClickException(str(exc)) from None


def _legacy_jobs() -> list[str]:
    if sys.platform != "darwin":
        return []
    agents = Path.home() / "Library" / "LaunchAgents"
    return [name for name in _LEGACY_LAUNCHD if (agents / f"{name}.plist").exists()]


@schedule.command("status")
@config_option
@click.option("--json", "as_json", is_flag=True, help=N_("Output machine-readable JSON."))
def schedule_status(config_path: str, as_json: bool):
    """Show whether the timer is installed and active, what it runs, and when it last checked."""
    from cnequity.serve.ops.catalog import OpsError

    try:
        home = _service(config_path).home()
    except OpsError as exc:
        raise click.ClickException(str(exc)) from None
    legacy = _legacy_jobs()
    if as_json:
        keys = ("backend", "enabled", "daily", "stale", "daily_run_at", "stale_run_at")
        payload = {key: home.get(key) for key in keys}
        payload.update(
            events=home.get("events"),
            events_group=home.get("events_group"),
            daily_packs=home.get("daily_packs"),
            timer_health=home.get("timer_health"),
            last_tick=home.get("last_tick"),
            native=home.get("native"),
            legacy_jobs=legacy,
        )
        click.echo(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        return
    native = home.get("native") or {}
    if not native.get("available"):
        click.echo(
            _("This user cannot use the system scheduler ({backend}).").format(
                backend=home.get("backend")
            )
        )
    state = _("enabled") if home.get("enabled") else _("not enabled")
    click.echo(
        _("Scheduled update: {state} ({backend})").format(state=state, backend=home.get("backend"))
    )
    if home.get("daily"):
        click.echo(
            _("  Daily update after {at} Beijing time, then maintenance").format(
                at=home.get("daily_run_at")
            )
        )
    if home.get("stale"):
        click.echo(_("  Snapshot catch-up after {at}").format(at=home.get("stale_run_at")))
    if home.get("daily_packs"):
        click.echo(_("  Research packs: {packs}").format(packs=", ".join(home["daily_packs"])))
    if home.get("events"):
        click.echo(
            _("  Event group {group} every {minutes} minutes").format(
                group=home.get("events_group"), minutes=home.get("events_interval_minutes")
            )
        )
    tick = home.get("last_tick") or {}
    if tick:
        click.echo(
            _("  Last check: {at} ({status})").format(at=tick.get("at"), status=tick.get("status"))
        )
    if home.get("enabled") and home.get("timer_health") == "stale":
        click.echo(
            _(
                "  The timer has not checked in for over 20 minutes; is the machine asleep or the user logged out?"
            )
        )
    if home.get("warning"):
        click.echo(f"  {home['warning']}")
    if legacy:
        click.echo(
            _(
                "Legacy scripts/scheduler jobs are also installed: {names}. Remove them "
                "(scripts/scheduler/uninstall_scheduler.sh) so the lake is not updated twice."
            ).format(names=", ".join(legacy))
        )


@schedule.command("install")
@config_option
@click.option(
    "--pack",
    "packs",
    multiple=True,
    type=click.Choice(["market", "fundamentals", "universe"]),
    help=N_(
        "Update only these research packs' schedule groups, without event streams. Repeatable. "
        "Default: keep the current selection (every schedule group on a first install)."
    ),
)
@click.option(
    "--no-stale", is_flag=True, help=N_("Do not retry missed snapshots after [job.stale].run_at.")
)
@click.option(
    "--events-group",
    default=None,
    help=N_("Also run this event-stream group (announcements, news) on its own interval."),
)
@click.option(
    "--events-every",
    type=click.IntRange(1, 1440),
    default=60,
    show_default=True,
    help=N_("With --events-group: minutes between runs."),
)
@click.option("--yes", "-y", is_flag=True, help=N_("Install without asking for confirmation."))
def schedule_install(
    config_path: str,
    packs: tuple[str, ...],
    no_stale: bool,
    events_group: str | None,
    events_every: int,
    yes: bool,
):
    """Install (or update) the current user's timer for this lake."""
    from cnequity.serve.ops.catalog import OpsError
    from cnequity.serve.ops.scheduler import settings

    service = _service(config_path)
    cfg = service.config
    # Whatever this command has no flag for — or was not given one for — keeps
    # its current value, so installing from here never undoes a backup or event
    # schedule set up on the dashboard.
    saved = settings(cfg)
    events = events_group is not None or bool(saved.get("events"))
    try:
        preview = service.preview(
            daily=True,
            stale=not no_stale,
            daily_run_at=cfg.daily_run_at,
            stale_run_at=cfg.stale_run_at,
            backup=bool(saved.get("backup")),
            backup_run_at=saved.get("backup_run_at", "23:00"),
            backup_datasets=saved.get("backup_datasets"),
            backup_root=saved.get("backup_root"),
            events=events,
            events_group=events_group or saved.get("events_group"),
            events_interval_minutes=(
                events_every
                if events_group is not None
                else saved.get("events_interval_minutes", events_every)
            ),
            daily_packs=list(packs) if packs else list(saved.get("daily_packs") or []),
        )
    except OpsError as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(_("System scheduler: {backend}").format(backend=preview["backend"]))
    click.echo(
        _("Daily update after {at} Beijing time, then `cne run maintain`").format(
            at=cfg.daily_run_at
        )
    )
    if not no_stale:
        click.echo(_("Snapshot catch-up after {at}").format(at=cfg.stale_run_at))
    if preview.get("events"):
        click.echo(
            _("Event group {group} every {minutes} minutes").format(
                group=preview.get("events_group"), minutes=preview.get("events_interval_minutes")
            )
        )
    if preview.get("backup"):
        click.echo(_("Snapshot backup after {at}").format(at=preview.get("backup_run_at")))
    click.echo(preview["confirmation"])
    legacy = _legacy_jobs()
    if legacy:
        click.echo(
            _(
                "Legacy scripts/scheduler jobs are installed ({names}); remove them first "
                "(scripts/scheduler/uninstall_scheduler.sh) or the lake is updated twice."
            ).format(names=", ".join(legacy)),
            err=True,
        )
    if not yes and not click.confirm(_("Install it?"), default=True):
        raise SystemExit(1)
    try:
        service.apply(preview["token"], acknowledged=True, requested_by="cli")
    except OpsError as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(_("Installed. `cne schedule status` shows when it last checked."))


@schedule.command("remove")
@config_option
@click.option("--yes", "-y", is_flag=True, help=N_("Remove without asking for confirmation."))
def schedule_remove(config_path: str, yes: bool):
    """Stop scheduled runs for this lake and unregister its timer. Running jobs finish."""
    from cnequity.serve.ops.catalog import OpsError

    service = _service(config_path)
    cfg = service.config
    try:
        preview = service.preview(
            daily=False,
            stale=False,
            daily_run_at=cfg.daily_run_at,
            stale_run_at=cfg.stale_run_at,
        )
    except OpsError as exc:
        raise click.ClickException(str(exc)) from None
    if not yes and not click.confirm(_("Remove the scheduled update for this lake?"), default=True):
        raise SystemExit(1)
    try:
        service.apply(preview["token"], acknowledged=True, requested_by="cli")
    except OpsError as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(_("Removed. Nothing runs on a schedule for this lake now."))
