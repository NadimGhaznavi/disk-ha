"""Validate disk identities, direction, schedule, and rsync timeout."""

import json
import math
from pathlib import Path
from uuid import UUID

from diskha.entity.Disk import Disk
from diskha.interface.HealthConfiguration import validate_expression


def directory_path(value: str) -> Path:
    if (not isinstance(value, str) or not value.startswith("/") or not value.rstrip("/")
            or any(part in ("", ".", "..") for part in value.rstrip("/").split("/")[1:])
            or any(ord(character) < 32 or ord(character) == 127 for character in value)):
        raise ValueError("Use an absolute, non-root directory path without relative components or control characters.")
    return Path(value)


def mount_identity(values: dict) -> tuple[Path, str]:
    if not isinstance(values, dict) or set(values) not in ({"mount", "uuid"}, {"path", "mount", "uuid", "disk"}):
        raise ValueError("Provide a mount path and filesystem UUID for each disk.")
    mount = directory_path(values["mount"])
    if not isinstance(values["uuid"], str):
        raise ValueError("Filesystem UUID must be a string.")
    identity = str(UUID(values["uuid"]))
    return mount, identity


class SyncConfiguration:
    def __init__(self, path: Path):
        values = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(values, dict) or set(values) != {"enabled", "expression", "source", "target", "timeout"}:
            raise ValueError("Invalid synchronization configuration fields.")
        if type(values["enabled"]) is not bool:
            raise ValueError("Sync enabled must be a boolean.")
        self.enabled = values["enabled"]
        self.expression = validate_expression(values["expression"]) if values["expression"] is not None else None
        if self.enabled and self.expression is None:
            raise ValueError("Enabled synchronization requires a cron expression.")
        self.source_mount, self.source_uuid = mount_identity(values["source"])
        self.target_mount, self.target_uuid = mount_identity(values["target"])
        if ("path" in values["source"]) != ("path" in values["target"]):
            raise ValueError("Configure both directory identities together.")
        self.source = directory_path(values["source"].get("path", str(self.source_mount)))
        self.target = directory_path(values["target"].get("path", str(self.target_mount)))
        self.disks = None
        if "path" in values["source"]:
            if not all(isinstance(values[role]["disk"], str) for role in ("source", "target")):
                raise ValueError("Disk identities must be stable device paths.")
            self.disks = tuple(Disk(values[role]["disk"]) for role in ("source", "target"))
            if self.disks[0] == self.disks[1]:
                raise ValueError("Source and target must use distinct physical drives.")
        for path, mount in ((self.source, self.source_mount), (self.target, self.target_mount)):
            if path != mount and mount not in path.parents:
                raise ValueError("Each directory must be inside its configured mount.")
        if (self.source_uuid == self.target_uuid or self.source == self.target
                or self.source in self.target.parents or self.target in self.source.parents):
            raise ValueError("Source and target must be distinct, non-nested disks.")
        if (type(values["timeout"]) not in (int, float)
                or not math.isfinite(values["timeout"]) or values["timeout"] <= 0):
            raise ValueError("Rsync timeout must be finite and positive.")
        self.timeout = values["timeout"]
