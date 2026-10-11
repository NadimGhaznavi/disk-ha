"""Request bounded directory detection and selection from the installed root helper."""

from diskha.interface.HealthControl import _schedule
from diskha.interface.SyncConfiguration import directory_path


def read_drives() -> dict:
    return _schedule({"action": "read-drives"})


def select_drives(source: str, target: str, save: bool = False) -> dict:
    first, second = directory_path(source), directory_path(target)
    return _schedule({"action": "save-drives" if save else "check-drives",
                      "source": str(first), "target": str(second)})
