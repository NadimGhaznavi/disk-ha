"""Detect directory, filesystem, and physical drive identities without changing disks."""

import json
from pathlib import Path
import re
import shutil
import stat
import subprocess
from uuid import UUID

from diskha.constants.DDiskHA import DDiskHA
from diskha.interface.SyncConfiguration import directory_path


class DirectoryInspection:
    def command(self, arguments: list[str], key: str) -> list[dict]:
        result = subprocess.run(arguments, capture_output=True, text=True, timeout=10, check=False)
        if result.returncode != 0:
            raise ValueError("Cannot identify the mounted local drive; check the directory and mount.")
        values = json.loads(result.stdout)
        records = values.get(key) if isinstance(values, dict) else None
        if not isinstance(records, list) or not records or not all(isinstance(item, dict) for item in records):
            raise ValueError("Cannot identify the mounted local drive.")
        return records

    def inspect(self, value: str, writable: bool = False) -> dict:
        path = directory_path(value)
        try:
            resolved = path.resolve(strict=True)
        except OSError as error:
            raise ValueError(f"Directory is unavailable: {path}") from error
        if resolved != path or not path.is_dir():
            raise ValueError(f"Directory must exist and must not use symbolic links: {path}")
        records = self.command(
            [DDiskHA.FINDMNT, "--json", "--target", str(path), "--submounts", "--output",
             "TARGET,UUID,MAJ:MIN,FSROOT,FSTYPE,OPTIONS"], "filesystems")
        if len(records) != 1:
            raise ValueError("Cannot identify a unique backing filesystem.")
        current = records[0]
        mount = directory_path(current.get("target"))
        if path != mount and mount not in path.parents:
            raise ValueError("The selected directory does not belong to the detected mount.")
        if current.get("fsroot") != "/" or current.get("fstype") not in ("ext2", "ext3", "ext4", "xfs"):
            raise ValueError("Select a directory on a directly mounted ext2, ext3, ext4, or XFS local drive.")
        self.check_submounts(current.get("children", []), path)
        identity = current.get("uuid")
        if not isinstance(identity, str):
            raise ValueError("The backing filesystem must have a UUID.")
        identity = str(UUID(identity))
        if writable and "rw" not in (current.get("options") or "").split(","):
            raise ValueError("The target filesystem is read-only.")
        number = current.get("maj:min")
        if not isinstance(number, str) or not re.fullmatch(r"[0-9]+:[0-9]+", number):
            raise ValueError("Cannot identify the backing block device.")
        devices = self.command(
            [DDiskHA.LSBLK, "--json", "--paths", "--inverse", "--output", "NAME,TYPE,MAJ:MIN,TRAN",
             f"/dev/block/{number}"], "blockdevices")
        if len(devices) != 1 or devices[0].get("maj:min") != number:
            raise ValueError("Cannot identify a unique backing block device.")
        disk = devices[0]
        if disk.get("type") == "part":
            parents = disk.get("children", [])
            if not isinstance(parents, list) or len(parents) != 1 or not isinstance(parents[0], dict):
                raise ValueError("Cannot identify a single physical drive.")
            disk = parents[0]
        if (disk.get("type") != "disk" or disk.get("children")
                or disk.get("tran") not in (None, "ata", "sata", "sas", "spi", "usb", "nvme")
                or not isinstance(disk.get("name"), str)
                or not re.fullmatch(r"/dev/(?:sd[a-z]+|hd[a-z]+|vd[a-z]+|xvd[a-z]+|nvme[0-9]+n[0-9]+)", disk["name"])):
            raise ValueError("Select a single local drive; network, loop, RAID, and layered devices are unsupported.")
        # NVMe namespaces can also be supplied over a network transport.
        if disk.get("tran") == "nvme":
            transport = Path("/sys/class/block") / Path(disk["name"]).name / "device/transport"
            if transport.read_text().strip() != "pcie":
                raise ValueError("Network NVMe drives are unsupported.")
        physical = re.sub(r"n[0-9]+$", "", disk["name"]) if disk.get("tran") == "nvme" else disk["name"]
        stable = self.stable_disk(disk["name"])
        usage = shutil.disk_usage(path)
        return {"path": str(path), "mount": str(mount), "uuid": identity, "disk": stable,
                "physical": physical, "capacity": usage.total, "used": usage.used, "free": usage.free}

    def check_submounts(self, children: list, path: Path) -> None:
        if not isinstance(children, list):
            raise ValueError("Cannot inspect nested mounts.")
        for child in children:
            if not isinstance(child, dict) or not isinstance(child.get("target"), str):
                raise ValueError("Cannot inspect nested mounts.")
            nested = Path(child["target"])
            if nested == path or path in nested.parents:
                raise ValueError(f"Selected directory contains another mount: {nested}")
            self.check_submounts(child.get("children", []), path)

    def stable_disk(self, device: str) -> str:
        actual = Path(device).resolve(strict=True)
        if not stat.S_ISBLK(actual.stat().st_mode):
            raise ValueError("The detected drive is not a block device.")
        for alias in sorted(Path("/dev/disk/by-id").glob("*")):
            if (alias.is_symlink() and not re.search(r"-part[0-9]+$", alias.name)
                    and not any(character.isspace() for character in str(alias))
                    and alias.resolve() == actual):
                return str(alias)
        raise ValueError("The drive must have a stable /dev/disk/by-id/ identity for monitoring.")

    def pair(self, source: str, target: str, check_smart: bool = False) -> dict:
        first = directory_path(source)
        second = directory_path(target)
        if first == second or first in second.parents or second in first.parents:
            raise ValueError("Source and target directories must be distinct and must not be nested.")
        values = {"source": self.inspect(source), "target": self.inspect(target, writable=True)}
        if (values["source"]["physical"] == values["target"]["physical"]
                or values["source"]["uuid"] == values["target"]["uuid"]):
            raise ValueError("Source and target must be on two distinct physical drives and filesystems.")
        if check_smart:
            for role in ("source", "target"):
                self.check_smart(values[role]["disk"])
        return values

    def check_smart(self, disk: str) -> None:
        result = subprocess.run([DDiskHA.SMARTCTL, "--info", "--json", disk],
                                capture_output=True, text=True, timeout=10, check=False)
        if not 0 <= result.returncode <= 255 or result.returncode & 3:
            raise ValueError(f"Cannot inspect SMART information for {disk}.")
        values = json.loads(result.stdout)
        support = values.get("smart_support") if isinstance(values, dict) else None
        if not isinstance(support, dict) or support.get("available") is not True:
            raise ValueError(f"SMART monitoring is unavailable for {disk}.")
