"""Own the saved directory selection shared by synchronization and monitoring."""

from contextlib import ExitStack
import fcntl
import json
from pathlib import Path
import shutil
import subprocess

from diskha.interface.DirectoryInspection import DirectoryInspection
from diskha.interface.HealthConfiguration import HealthConfiguration
from diskha.interface.MountInspection import MountInspection
from diskha.interface.SyncConfiguration import SyncConfiguration, directory_path
from diskha.interface.SyncSchedule import SyncSchedule


class DriveConfiguration:
    @staticmethod
    def read(root: Path) -> dict:
        configuration = SyncConfiguration(root / "conf/sync.json")
        disks = configuration.disks or HealthConfiguration(root / "conf/health.json").disks
        result = {}
        for number, role in enumerate(("source", "target")):
            path = getattr(configuration, role)
            mount = getattr(configuration, role + "_mount")
            identity = getattr(configuration, role + "_uuid")
            entry = {"path": str(path), "mount": str(mount), "uuid": identity,
                     "disk": disks[number].device_path}
            try:
                if configuration.disks is not None:
                    detected = DirectoryInspection().inspect(str(path), writable=role == "target")
                    if any(detected[key] != entry[key] for key in ("path", "mount", "uuid", "disk")):
                        raise ValueError("Directory no longer matches its saved drive identity.")
                    usage = (detected["capacity"], detected["used"], detected["free"])
                else:
                    MountInspection().inspect(mount, identity)
                    usage = shutil.disk_usage(path)
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                entry.update(status="Unavailable", error=str(error), capacity=None, used=None, free=None)
            else:
                entry.update(status="Available", capacity=usage[0], used=usage[1], free=usage[2])
            result[role] = entry
        return result

    @staticmethod
    def check(source: str, target: str) -> dict:
        return DirectoryInspection().pair(source, target, check_smart=True)

    @classmethod
    def save(cls, root: Path, source: str, target: str) -> dict:
        directory_path(source)
        directory_path(target)
        # The health worker reads sync.json under health.lock. No second copy of
        # the detected disks is written: one atomic publication changes both workers.
        with ExitStack() as stack:
            for name in ("health", "sync"):
                lock = stack.enter_context((root / f"conf/{name}.lock").open("a"))
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise OSError("A health check, sync, or settings update is active; retry after it finishes.") from None
            path = root / "conf/sync.json"
            previous = json.loads(path.read_text(encoding="utf-8"))
            SyncConfiguration(path)
            detected = cls.check(source, target)
            values = dict(previous)
            for role in ("source", "target"):
                values[role] = {key: detected[role][key] for key in ("path", "mount", "uuid", "disk")}
            SyncSchedule.save_configuration(path, values)
            return detected
