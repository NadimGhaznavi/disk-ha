"""Render the two-drive configuration table."""

from importlib.resources import files
from datetime import datetime
from html import escape
from pathlib import Path
import subprocess
import re

from diskha.constants.DDiskHA import DDiskHA
from diskha.interface.HealthResult import HealthResult
from diskha.interface.DriveControl import read_drives
from diskha.interface.HealthControl import read_schedule, read_contact, read_sync_schedule


def render_page() -> bytes:
    page = (files("diskha.server") / "static/index.html").read_text(encoding="utf-8")
    schedule, run_control = render_schedule()
    values = {"drive_configuration": render_drives(), "health": render_health(),
              "schedule": schedule, "run_control": run_control,
              "email_notification": render_email_notification(), "sync_schedule": render_sync_schedule()}
    # Directory names may contain braces; only expand the original template.
    page = re.sub(r"\{\{(\w+)\}\}", lambda match: values[match[1]], page)
    return page.encode("utf-8")


def render_drives() -> str:
    try:
        settings = read_drives()
    except (OSError, ValueError, subprocess.SubprocessError):
        return '<p>Drive settings unavailable. Check the installed settings helper and reload.</p>'
    rows = []
    for number, role in enumerate(("source", "target"), 1):
        entry = settings[role]
        readings = [f'{entry[key] / 10**12:,.2f}' if entry[key] is not None else "Unavailable"
                    for key in ("capacity", "used", "free")]
        details = (f'<small>Mount: {escape(entry["mount"])}<br>UUID: {escape(entry["uuid"])}<br>'
                   f'Drive: {escape(entry["disk"])}</small>')
        if entry.get("error"):
            details += f'<p>{escape(entry["error"])}</p>'
        rows.append(f'<tr><th scope="row">Disk {number}</th><td>{role.title()}</td>'
                    f'<td>{escape(entry["path"])}<br>{details}</td>'
                    + ''.join(f'<td>{value}</td>' for value in readings) + '</tr>')
    return ('<form id="drive-form">'
            '<label for="source-directory">Source directory</label>'
            f'<input id="source-directory" type="text" maxlength="4096" required value="{escape(settings["source"]["path"], quote=True)}">'
            '<label for="target-directory">Target directory</label>'
            f'<input id="target-directory" type="text" maxlength="4096" required value="{escape(settings["target"]["path"], quote=True)}">'
            '<div class="drive-actions"><button id="check-drives" type="submit">Check directories</button> '
            '<button id="save-drives" type="button" disabled>Save directories</button></div></form>'
            '<p>Use existing directories on two distinct local drives. Saving changes the next scheduled sync. '
            'Files absent from the source are deleted from the target.</p>'
            '<p id="drive-status" role="status" aria-live="polite"></p>'
            '<pre id="drive-preview" hidden></pre>'
            '<div class="drive-table"><table class="drives"><thead><tr>'
            '<th scope="col">Device</th><th scope="col">Role</th><th scope="col">Saved directory / drive</th>'
            '<th scope="col">Capacity (TB)</th><th scope="col">Usage (TB)</th><th scope="col">Free (TB)</th>'
            '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div>')


def render_sync_schedule() -> str:
    try:
        settings = read_sync_schedule()
    except (OSError, ValueError, subprocess.SubprocessError):
        return '<p>Cron schedule unavailable.</p>'
    expression = escape(settings["expression"], quote=True)
    checked = " checked" if settings["enabled"] else ""
    disabled = "" if settings["enabled"] else " disabled"
    return ('<form id="sync-schedule-form">'
            f'<label><input id="sync-schedule-enabled" type="checkbox"{checked}> Enabled</label> '
            '<label for="sync-schedule-expression">Cron Schedule</label> '
            f'<input id="sync-schedule-expression" type="text" size="20" maxlength="255" value="{expression}"> '
            '<button id="update-sync-schedule" type="submit">Update</button>'
            f'<button id="sync-now" type="button"{disabled}>Sync Now</button></form>'
            '<p id="sync-schedule-status" role="status" aria-live="polite"></p>'
            '<p id="sync-run-status" role="status" aria-live="polite"></p>')


def render_email_notification() -> str:
    try:
        recipient = read_contact()
    except (OSError, ValueError, subprocess.SubprocessError):
        contact = "Unavailable"
        disabled = " disabled"
    else:
        contact = escape(recipient) if recipient is not None else "Not configured"
        disabled = " disabled" if recipient is None else ""
    return (f'<p>Contact: {contact}</p>'
            f'<button id="email-report" type="button"{disabled}>Email disk report</button>'
            '<p id="email-status" role="status" aria-live="polite"></p>')


def render_schedule() -> tuple[str, str]:
    """Render the schedule form and manual-run controls from one cron reading."""
    try:
        settings = read_schedule()
    except (OSError, ValueError, subprocess.SubprocessError):
        return '<p>Cron schedule unavailable.</p>', '<button disabled>Run Now</button>'
    expression = escape(settings["expression"], quote=True)
    checked = " checked" if settings["enabled"] else ""
    disabled = "" if settings["enabled"] else " disabled"
    return ('<form id="schedule-form">'
            f'<label><input id="schedule-enabled" type="checkbox"{checked}> Enabled</label> '
            '<label for="schedule-expression">Cron Schedule</label> '
            f'<input id="schedule-expression" type="text" size="20" maxlength="255" value="{expression}"> '
            '<button id="update-schedule" type="submit">Update</button></form>'
            '<p id="schedule-status" role="status" aria-live="polite"></p>',
            f'<button id="run-now" type="button"{disabled}>Run Now</button>'
            '<p id="run-status" role="status" aria-live="polite"></p>')


def render_health() -> str:
    try:
        result = HealthResult(Path(DDiskHA.HEALTH_RESULT)).read()
    except (OSError, ValueError):
        return "<p>Health results unavailable.</p>"
    if result is None:
        return "<p>No health check recorded.</p>"
    rows = []
    for number, disk in enumerate(result["disks"], 1):
        status = "FAIL" if disk["problems"] else "PASS"
        problems = "; ".join(disk["problems"]) or "No problems detected"
        rows.append(f'<tr><th scope="row">Disk {number}</th><td>{status}</td>'
                    f'<td>{escape(disk["disk"]["device_path"])}</td>'
                    f'<td>{escape(problems)}</td></tr>')
    notification = ("<p>Email alert delivery failed: " + escape(result["notification_error"]) + "</p>"
                    if result["notification_error"] is not None else "")
    checked_at = datetime.fromisoformat(result["checked_at"]).astimezone()
    timestamp = checked_at.isoformat(timespec="seconds")
    display_time = checked_at.strftime("%Y-%m-%d %H:%M:%S")
    return (f'<p>Last check: <time datetime="{timestamp}">{display_time}</time> (server time)</p>'
            '<table><thead><tr><th scope="col">Device</th><th scope="col">Health</th>'
            '<th scope="col">Identity</th><th scope="col">Details</th></tr></thead>'
            '<tbody>' + "".join(rows) + '</tbody></table>' + notification)
