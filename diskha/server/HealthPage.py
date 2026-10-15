"""Display the latest saved health check, including both disks' SMART output."""

from html import escape
from importlib.resources import files
from pathlib import Path

from diskha.constants.DDiskHA import DDiskHA
from diskha.interface.HealthResult import HealthResult


def render_health_output() -> bytes:
    page = (files("diskha.server") / "static/health-output.html").read_text(encoding="utf-8")
    try:
        result = HealthResult(Path(DDiskHA.HEALTH_RESULT)).read()
        if result is None:
            output = "No health check recorded."
        else:
            lines = [f"Checked at: {result['checked_at']}"]
            for disk in result["disks"]:
                raw = disk.get("smart_output", "")
                if not isinstance(raw, str):
                    raise ValueError("Invalid SMART output.")
                lines.extend(("", "=" * 60, f"Disk: {disk['disk']['device_path']}"))
                lines.extend((f"FAIL: {problem}" for problem in disk["problems"])
                             if disk["problems"] else ["PASS"])
                lines.extend(("", raw.rstrip()))
            failed = any(disk["problems"] for disk in result["disks"])
            lines.extend(("=" * 60, f"Overall result: {'FAIL' if failed else 'PASS'}"))
            if result["notification_error"] is not None:
                lines.append(f"Notification failure: {result['notification_error']}")
            output = "\n".join(lines)
    except (OSError, ValueError):
        output = "Health results unavailable."
    return page.replace("{{output}}", escape(output)).encode("utf-8")
