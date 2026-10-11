"""Root-only monitoring settings helper; accept a bounded JSON request on stdin."""

import json
import os
from pathlib import Path
import subprocess
import sys

from diskha.constants.DDiskHA import DDiskHA
from diskha.interface.HealthConfiguration import HealthConfiguration, validate_expression
from diskha.interface.HealthSchedule import HealthSchedule
from diskha.interface.SyncSchedule import SyncSchedule
from diskha.interface.DriveConfiguration import DriveConfiguration


def dispatch(request: dict) -> dict:
    if request == {"action": "read-drives"}:
        return DriveConfiguration.read(Path(DDiskHA.INSTALL_DIR))
    if (isinstance(request, dict) and set(request) == {"action", "source", "target"}
            and request["action"] in ("check-drives", "save-drives")):
        if request["action"] == "check-drives":
            return DriveConfiguration.check(request["source"], request["target"])
        return DriveConfiguration.save(Path(DDiskHA.INSTALL_DIR), request["source"], request["target"])
    if request == {"action": "read"}:
        return HealthSchedule.read()
    if request == {"action": "read-sync"}:
        return SyncSchedule.read()
    if request == {"action": "contact"}:
        configuration = HealthConfiguration(Path(DDiskHA.INSTALL_DIR) / "conf/health.json")
        return {"recipient": (configuration.notification.recipient
                              if configuration.notification is not None else None)}
    if (isinstance(request, dict) and set(request) == {"action", "enabled", "expression"}
            and request["action"] in ("update", "update-sync")):
        if type(request["enabled"]) is not bool or not isinstance(request["expression"], str):
            raise ValueError("Provide an enabled flag and a cron expression.")
        if request["expression"] or request["enabled"]:
            validate_expression(request["expression"])
        if request["enabled"]:
            subprocess.run([DDiskHA.SYSTEMCTL, "enable", "--now", "cron.service"],
                           capture_output=True, check=True, timeout=30)
        policy = SyncSchedule if request["action"] == "update-sync" else HealthSchedule
        return policy.update(Path(DDiskHA.INSTALL_DIR), request["enabled"], request["expression"])
    raise ValueError("Invalid schedule request.")


def main() -> int:
    if os.geteuid() != 0 or len(sys.argv) != 1:
        print("Schedule helper requires root and no arguments.", file=sys.stderr)
        return 1
    os.umask(0o077)
    try:
        source = sys.stdin.read(16385)
        if len(source) > 16384:
            raise ValueError("Schedule request is too large.")
        result = dispatch(json.loads(source))
    except ValueError as error:
        print(json.dumps({"error": str(error)}))
        return 2
    except (OSError, subprocess.SubprocessError):
        print(json.dumps({"error": "Cannot access cron or save settings; check permissions and retry."}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
