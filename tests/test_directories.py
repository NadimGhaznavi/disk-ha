"""Verify directory selection with simulated disks and disposable saved settings."""

from contextlib import redirect_stdout
import copy
import fcntl
import io
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from diskha import schedule
from diskha.health import run as health_run
from diskha.entity.DiskHealth import DiskHealth
from diskha.interface.DirectoryInspection import DirectoryInspection
from diskha.interface.DriveConfiguration import DriveConfiguration
from diskha.interface.DriveControl import select_drives
from diskha.interface.MountInspection import MountInspection
from diskha.interface.SyncConfiguration import SyncConfiguration
from diskha.interface.SyncSchedule import SyncSchedule
from diskha.sync import run as sync_run

ROOT = Path(__file__).resolve().parents[1]


class DirectoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="disk-ha-directory-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "conf").mkdir()
        (self.root / "data").mkdir()
        self.source_mount = self.root / "disk1"
        self.target_mount = self.root / "disk2"
        self.source = self.source_mount / "archive/incoming/movies"
        self.target = self.target_mount / "inbox/media center"
        self.source.mkdir(parents=True)
        self.target.mkdir(parents=True)
        self.sync_path = self.root / "conf/sync.json"
        self.health_path = self.root / "conf/health.json"
        self.previous = json.loads((ROOT / "conf/sync.json").read_text())
        self.sync_path.write_text(json.dumps(self.previous))
        self.health_path.write_text((ROOT / "conf/health.json").read_text())
        self.records = {}
        for role, mount, number, disk in (("source", self.source_mount, "8:1", "/dev/sda"),
                                          ("target", self.target_mount, "8:17", "/dev/sdb")):
            self.records[role] = {"target": str(mount), "uuid": self.previous[role]["uuid"],
                                  "maj:min": number, "fsroot": "/", "fstype": "ext4", "options": "rw,relatime"}
        self.devices = {"8:1": "/dev/sda", "8:17": "/dev/sdb"}
        self.commands = patch("diskha.interface.DirectoryInspection.subprocess.run", side_effect=self.command)
        self.commands.start()
        self.addCleanup(self.commands.stop)
        self.original_stable = DirectoryInspection.stable_disk
        aliases = patch.object(DirectoryInspection, "stable_disk", side_effect=lambda device: "/dev/disk/by-id/ata-" + Path(device).name)
        aliases.start()
        self.addCleanup(aliases.stop)

    def command(self, arguments, **kwargs):
        if "--target" in arguments:
            path = arguments[arguments.index("--target") + 1]
            role = "source" if path == str(self.source) else "target"
            values = {"filesystems": [copy.deepcopy(self.records[role])]}
        elif "--inverse" in arguments:
            number = arguments[-1].removeprefix("/dev/block/")
            values = {"blockdevices": [{"name": "/dev/partition", "type": "part", "maj:min": number,
                      "children": [{"name": self.devices[number], "type": "disk", "tran": "sata"}]}]}
        elif "--info" in arguments:
            values = {"smart_support": {"available": True}}
        else:
            raise AssertionError(arguments)
        return SimpleNamespace(returncode=0, stdout=json.dumps(values))

    def detect(self):
        return DirectoryInspection().pair(str(self.source), str(self.target), check_smart=True)

    def test_arbitrary_subdirectories_and_spaces_detect_mounts_uuids_and_physical_disks(self):
        values = self.detect()
        self.assertEqual(values["source"]["path"], str(self.source))
        self.assertEqual(values["target"]["mount"], str(self.target_mount))
        self.assertEqual(values["target"]["disk"], "/dev/disk/by-id/ata-sdb")
        self.assertEqual(values["source"]["uuid"], self.previous["source"]["uuid"])
        self.assertGreater(values["target"]["capacity"], 0)

    def test_same_physical_drive_different_partitions_and_duplicate_uuids_rejected(self):
        self.devices["8:17"] = "/dev/sda"
        with self.assertRaisesRegex(ValueError, "distinct physical"):
            self.detect()
        self.devices["8:17"] = "/dev/sdb"
        self.records["target"]["uuid"] = self.records["source"]["uuid"]
        with self.assertRaisesRegex(ValueError, "distinct physical"):
            self.detect()

    def test_missing_symlink_and_nested_directories_rejected(self):
        with self.assertRaises(ValueError):
            DirectoryInspection().pair(str(self.source / "absent"), str(self.target))
        alias = self.source_mount / "alias"
        alias.symlink_to(self.source, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symbolic links"):
            DirectoryInspection().pair(str(alias), str(self.target))
        for first, second in ((self.source, self.source), (self.source_mount, self.source)):
            with self.assertRaisesRegex(ValueError, "nested"):
                DirectoryInspection().pair(str(first), str(second))

    def test_network_bind_root_readonly_and_nested_mounts_rejected(self):
        original = copy.deepcopy(self.records["target"])
        for changes in ({"fstype": "nfs"}, {"fstype": "btrfs"}, {"fsroot": "/bind"},
                        {"target": "/"}, {"options": "ro"}, {"uuid": None},
                        {"children": [{"target": str(self.target / "another-drive")}]}):
            with self.subTest(changes=changes):
                self.records["target"] = dict(original, **changes)
                with self.assertRaises(ValueError):
                    self.detect()
        self.records["target"] = dict(original, children=[{"target": str(self.target_mount / "elsewhere")}])
        self.detect()  # A sibling mount outside the selected subtree does not affect this mirror.

    def test_layered_loop_and_remote_block_devices_rejected(self):
        original = self.command
        for changes in ({"type": "lvm"}, {"type": "raid1"}, {"type": "loop"},
                        {"tran": "iscsi"}, {"tran": "fc"}, {"name": "/dev/nbd0"}):
            def changed(arguments, **kwargs):
                result = original(arguments, **kwargs)
                if "--inverse" in arguments:
                    values = json.loads(result.stdout)
                    values["blockdevices"][0]["children"][0].update(changes)
                    result.stdout = json.dumps(values)
                return result
            with self.subTest(changes=changes), patch("diskha.interface.DirectoryInspection.subprocess.run", side_effect=changed):
                with self.assertRaises(ValueError):
                    self.detect()

    def test_nvme_namespaces_on_one_controller_and_network_nvme_rejected(self):
        original = self.command
        self.devices.update({"8:1": "/dev/nvme0n1", "8:17": "/dev/nvme0n2"})
        def nvme(arguments, **kwargs):
            result = original(arguments, **kwargs)
            if "--inverse" in arguments:
                values = json.loads(result.stdout)
                values["blockdevices"][0]["children"][0]["tran"] = "nvme"
                result.stdout = json.dumps(values)
            return result
        with patch("diskha.interface.DirectoryInspection.subprocess.run", side_effect=nvme):
            with patch("diskha.interface.DirectoryInspection.Path.read_text", return_value="pcie\n"):
                with self.assertRaisesRegex(ValueError, "distinct physical"):
                    self.detect()
            with patch("diskha.interface.DirectoryInspection.Path.read_text", return_value="tcp\n"):
                with self.assertRaisesRegex(ValueError, "Network NVMe"):
                    self.detect()

    def test_stable_drive_identity_ignores_partition_aliases(self):
        device = self.root / "device"
        device.touch()
        whole = self.root / "ata-whole"
        partition = self.root / "ata-whole-part1"
        whole.symlink_to(device)
        partition.symlink_to(device)
        # Use the original method rather than this fixture's simulated identities.
        with patch("diskha.interface.DirectoryInspection.Path.glob", return_value=[partition, whole]), \
                patch("diskha.interface.DirectoryInspection.stat.S_ISBLK", return_value=True):
            self.assertEqual(self.original_stable(DirectoryInspection(), str(device)), str(whole))
        with patch("diskha.interface.DirectoryInspection.Path.glob", return_value=[partition]), \
                patch("diskha.interface.DirectoryInspection.stat.S_ISBLK", return_value=True):
            with self.assertRaisesRegex(ValueError, "stable"):
                self.original_stable(DirectoryInspection(), str(device))

    def test_missing_smart_support_and_failed_external_inspection_rejected(self):
        for result in (SimpleNamespace(returncode=2, stdout="{}"),
                       SimpleNamespace(returncode=0, stdout='{"smart_support":{"available":false}}')):
            with patch("diskha.interface.DirectoryInspection.subprocess.run", return_value=result):
                with self.assertRaises(ValueError):
                    DirectoryInspection().check_smart("/dev/disk/by-id/ata-test")
        with patch("diskha.interface.DirectoryInspection.subprocess.run", side_effect=subprocess.TimeoutExpired("findmnt", 10)):
            with self.assertRaises(subprocess.TimeoutExpired):
                self.detect()

    def test_save_preserves_schedules_and_mail_and_publishes_one_authoritative_selection(self):
        health_before = self.health_path.read_bytes()
        DriveConfiguration.save(self.root, str(self.source), str(self.target))
        selected = SyncConfiguration(self.sync_path)
        self.assertEqual(selected.source, self.source)
        self.assertEqual(selected.target, self.target)
        self.assertEqual(selected.source_mount, self.source_mount)
        self.assertEqual(selected.target_mount, self.target_mount)
        self.assertEqual(selected.disks[0].device_path, "/dev/disk/by-id/ata-sda")
        self.assertEqual(self.health_path.read_bytes(), health_before)
        for key in ("enabled", "expression", "timeout"):
            self.assertEqual(json.loads(self.sync_path.read_text())[key], self.previous[key])
        self.assertEqual(self.sync_path.stat().st_mode & 0o777, 0o600)
        MountInspection().verify(selected)

    def test_invalid_busy_or_failed_save_preserves_previous_selection(self):
        previous = self.sync_path.read_bytes()
        self.devices["8:17"] = "/dev/sda"
        with self.assertRaises(ValueError):
            DriveConfiguration.save(self.root, str(self.source), str(self.target))
        self.assertEqual(self.sync_path.read_bytes(), previous)
        self.devices["8:17"] = "/dev/sdb"
        for name in ("health", "sync"):
            with (self.root / f"conf/{name}.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with self.assertRaisesRegex(OSError, "active"):
                    DriveConfiguration.save(self.root, str(self.source), str(self.target))
            self.assertEqual(self.sync_path.read_bytes(), previous)
        with patch.object(SyncSchedule, "save_configuration", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                DriveConfiguration.save(self.root, str(self.source), str(self.target))
        self.assertEqual(self.sync_path.read_bytes(), previous)

    def test_mount_identity_change_and_reversed_drives_block_worker(self):
        DriveConfiguration.save(self.root, str(self.source), str(self.target))
        self.records["source"]["uuid"] = self.previous["target"]["uuid"]
        self.records["target"]["uuid"] = self.previous["source"]["uuid"]
        with patch("diskha.sync.RsyncMirror.run") as mirror, redirect_stdout(io.StringIO()):
            self.assertEqual(sync_run(self.sync_path, self.root / "data/sync-output.log"), 1)
            mirror.assert_not_called()

    def test_selected_subdirectories_copy_contents_delete_only_in_target_and_ignore_health_alert(self):
        DriveConfiguration.save(self.root, str(self.source), str(self.target))
        (self.source / "film.txt").write_text("film")
        (self.target / "obsolete.txt").write_text("delete")
        outside = self.target_mount / "outside.txt"
        outside.write_text("preserve")
        (self.root / "data/health.json").write_text('{"disks":[{"problems":["FAIL"]}]}')
        # Allow only the real rsync process; mount inspection is simulated above.
        with redirect_stdout(io.StringIO()):
            self.assertEqual(sync_run(self.sync_path, self.root / "data/sync-output.log"), 0)
        self.assertEqual((self.target / "film.txt").read_text(), "film")
        self.assertFalse((self.target / "obsolete.txt").exists())
        self.assertEqual(outside.read_text(), "preserve")

    def test_health_worker_monitors_detected_disks_without_requiring_mounts(self):
        DriveConfiguration.save(self.root, str(self.source), str(self.target))
        with patch("diskha.interface.SmartInspection.SmartInspection.inspect", side_effect=lambda disk: DiskHealth(disk)) as inspect, \
                patch("diskha.interface.EmailNotification.EmailNotification.send") as email, redirect_stdout(io.StringIO()):
            self.assertEqual(health_run(self.health_path, self.root / "data/health.json"), 0)
        self.assertEqual([call.args[0].device_path for call in inspect.call_args_list],
                         ["/dev/disk/by-id/ata-sda", "/dev/disk/by-id/ata-sdb"])
        email.assert_not_called()

    def test_helper_accepts_only_directory_names_and_client_uses_fixed_actions(self):
        with patch.object(schedule.DriveConfiguration, "check", return_value={}) as check:
            schedule.dispatch({"action": "check-drives", "source": str(self.source), "target": str(self.target)})
            check.assert_called_once_with(str(self.source), str(self.target))
        for request in ({"action": "save-drives", "source": str(self.source), "target": str(self.target), "uuid": "chosen"},
                        {"action": "save-drives", "source": [], "target": str(self.target)}):
            with self.assertRaises(ValueError):
                schedule.dispatch(request)
        with patch("diskha.interface.DriveControl._schedule", return_value={}) as helper:
            select_drives(str(self.source), str(self.target), save=True)
            helper.assert_called_once_with({"action": "save-drives", "source": str(self.source), "target": str(self.target)})

    def test_subdirectory_configuration_rejects_path_outside_mount(self):
        DriveConfiguration.save(self.root, str(self.source), str(self.target))
        values = json.loads(self.sync_path.read_text())
        values["source"]["path"] = str(self.target)
        self.sync_path.write_text(json.dumps(values))
        with self.assertRaisesRegex(ValueError, "inside"):
            SyncConfiguration(self.sync_path)
