"""Verify deployment and preservation in temporary installation directories."""

from contextlib import redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("installer", ROOT / "scripts/install.py")
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


class InstallationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="nfs-ha-install-test-")
        self.addCleanup(temporary.cleanup)
        self.target = Path(temporary.name) / "prod"
        service = patch.object(installer.DNFSHA, "WEB_SERVICE_FILE",
                               str(Path(temporary.name) / "nfs-ha-web.service"))
        service.start()
        self.addCleanup(service.stop)
        control = patch.object(installer, "systemctl")
        self.control = control.start()
        self.addCleanup(control.stop)
        readiness = patch.object(installer, "restart")
        self.restart = readiness.start()
        self.addCleanup(readiness.stop)
        metadata = patch.object(installer.DNFSHA, "INSTALL_DIR", str(self.target))
        metadata.start()
        self.addCleanup(metadata.stop)
        output = redirect_stdout(io.StringIO())
        output.__enter__()
        self.addCleanup(output.__exit__, None, None, None)

    def test_install_upgrade_and_uninstall_preserve_local_files(self):
        installer.install()
        constants = self.target / "nfs_ha/constants/DNFSHA.py"
        expected = (ROOT / "nfs_ha/constants/DNFSHA.py").read_bytes()
        self.assertEqual(constants.read_bytes(), expected)
        for directory in (self.target, self.target / "bin", constants.parent.parent, constants.parent):
            self.assertEqual(directory.stat().st_mode & 0o777, 0o755)
        self.assertEqual(constants.stat().st_mode & 0o777, 0o644)
        executable = self.target / "bin/nfs-ha-web"
        self.assertEqual(executable.stat().st_mode & 0o777, 0o755)
        with zipfile.ZipFile(executable) as archive:
            self.assertEqual(archive.read("nfs_ha/server/static/index.html"),
                             (ROOT / "nfs_ha/server/static/index.html").read_bytes())
        service = Path(installer.DNFSHA.WEB_SERVICE_FILE)
        self.assertEqual(service.stat().st_mode & 0o777, 0o644)
        self.assertIn(f"ExecStart={executable} --host 0.0.0.0 --port 23300", service.read_text())
        self.assertIn("DynamicUser=yes", service.read_text())
        self.control.assert_any_call("enable", service.name)
        self.restart.assert_called_once_with()
        for name in ("conf", "data"):
            self.assertEqual((self.target / name).stat().st_mode & 0o777, 0o700)
        result = subprocess.run(
            ["/usr/bin/python3", "-B", "-c",
             "from nfs_ha.constants.DNFSHA import DNFSHA; print(DNFSHA.VERSION)"],
            cwd=self.target, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), installer.DNFSHA.VERSION)
        preserved = {}
        for name in ("conf/settings.json", "conf/credentials.env", "data/state.json"):
            path = self.target / name
            path.write_text("Local configuration or data\n")
            path.chmod(0o600)
            preserved[path] = path.read_bytes()
        constants.write_text('VERSION = "old release"\n')
        installer.install()
        self.assertEqual(constants.read_bytes(), expected)
        installer.uninstall()
        installer.uninstall()
        self.assertFalse((self.target / "nfs_ha").exists())
        self.assertFalse(executable.exists())
        self.assertFalse(service.exists())
        self.control.assert_any_call("disable", "--now", service.name)
        for path, content in preserved.items():
            self.assertEqual(path.read_bytes(), content)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_staging_failure_keeps_installed_metadata(self):
        installer.install()
        constants = self.target / "nfs_ha/constants/DNFSHA.py"
        original = constants.read_bytes()
        with patch.object(installer.shutil, "copytree", side_effect=OSError("Staging failed")):
            with self.assertRaisesRegex(OSError, "Staging failed"):
                installer.install()
        self.assertEqual(constants.read_bytes(), original)
        self.assertEqual(list(self.target.glob(".nfs-ha-install-*")), [])

    def test_wrappers_delegate_from_a_checkout_with_spaces(self):
        with tempfile.TemporaryDirectory(prefix="nfs-ha-wrappers-") as temporary:
            checkout = Path(temporary) / "checkout with spaces"
            scripts = checkout / "scripts"
            scripts.mkdir(parents=True)
            (scripts / "install.py").write_text(
                "import sys\nfrom pathlib import Path\n"
                "print(Path.cwd())\nprint(sys.argv[1])\nraise SystemExit(7)\n")
            for action in ("install", "upgrade", "uninstall", "restart"):
                wrapper = scripts / f"{action}.sh"
                wrapper.write_bytes((ROOT / "scripts" / wrapper.name).read_bytes())
                result = subprocess.run(["bash", str(wrapper)], cwd=temporary,
                                        text=True, capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 7)
                self.assertEqual(result.stdout.splitlines(), [str(checkout), action])

    def test_non_root_action_is_rejected(self):
        with patch.object(installer.os, "geteuid", return_value=1000), \
                patch("sys.argv", ["install.py", "install"]), redirect_stdout(io.StringIO()), \
                patch("sys.stderr", new_callable=io.StringIO) as errors:
            self.assertEqual(installer.main(), 1)
        self.assertIn("Run this script as root", errors.getvalue())
        self.assertFalse(self.target.exists())

    def test_service_failure_returns_failing_status(self):
        self.control.side_effect = subprocess.CalledProcessError(1, ["systemctl"])
        with patch.object(installer.os, "geteuid", return_value=0), \
                patch("sys.argv", ["install.py", "install"]), \
                patch("sys.stderr", new_callable=io.StringIO) as errors:
            self.assertEqual(installer.main(), 1)
        self.assertIn("nfs-ha:", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
