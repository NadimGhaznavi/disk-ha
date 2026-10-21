"""Verify deployment and preservation in temporary installation directories."""

from contextlib import redirect_stdout
import importlib.util
import io
import ast
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("installer", ROOT / "scripts/install.py")
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.provision_account = installer.SystemAccount.provision
        temporary = tempfile.TemporaryDirectory(prefix="disk-ha-install-test-")
        self.addCleanup(temporary.cleanup)
        self.target = Path(temporary.name) / "prod"
        self.legacy = Path(temporary.name) / "disk-ha"
        legacy_setting = patch.object(installer.DDiskHA, "LEGACY_INSTALL_DIR", str(self.legacy))
        legacy_setting.start()
        self.addCleanup(legacy_setting.stop)
        scheduling = patch.object(installer.HealthSchedule, "apply")
        self.scheduling = scheduling.start()
        self.addCleanup(scheduling.stop)
        reading = patch.object(installer.HealthSchedule, "read", side_effect=lambda: {
            "enabled": json.loads((self.target / "conf/health.json").read_text())["enabled"],
            "expression": json.loads((self.target / "conf/health.json").read_text())["expression"] or ""})
        self.reading = reading.start()
        self.addCleanup(reading.stop)
        sync_scheduling = patch.object(installer.SyncSchedule, "apply")
        self.sync_scheduling = sync_scheduling.start()
        self.addCleanup(sync_scheduling.stop)
        sync_reading = patch.object(installer.SyncSchedule, "read", side_effect=lambda: {
            "enabled": json.loads((self.target / "conf/sync.json").read_text())["enabled"],
            "expression": json.loads((self.target / "conf/sync.json").read_text())["expression"] or ""})
        self.sync_reading = sync_reading.start()
        self.addCleanup(sync_reading.stop)
        executable_check = patch.object(installer.os, "access", return_value=True)
        executable_check.start()
        self.addCleanup(executable_check.stop)
        for target, value in (("SystemAccount.provision", SimpleNamespace(pw_uid=os.geteuid(), pw_gid=os.getegid())),
                              ("DatabaseProvisioning.provision", None)):
            provisioning = patch.object(getattr(installer, target.split('.')[0]), target.split('.')[1],
                                        return_value=value)
            provisioning.start()
            self.addCleanup(provisioning.stop)
        service = patch.object(installer.DDiskHA, "WEB_SERVICE_FILE",
                               str(Path(temporary.name) / "disk-ha-web.service"))
        service.start()
        self.addCleanup(service.stop)
        for name, filename in (("HEALTH_SERVICE_FILE", "disk-ha-health.service"),
                               ("EMAIL_REPORT_SERVICE_FILE", "disk-ha-email-report.service"),
                               ("SYNC_SERVICE_FILE", "disk-ha-sync.service"),
                               ("HEALTH_SUDOERS_FILE", "disk-ha-health")):
            setting = patch.object(installer.DDiskHA, name, str(Path(temporary.name) / filename))
            setting.start()
            self.addCleanup(setting.stop)
        original_run = subprocess.run
        validation = patch.object(installer.subprocess, "run", wraps=subprocess.run)
        self.commands = validation.start()
        self.addCleanup(validation.stop)

        def run_command(arguments, **kwargs):
            if arguments[0] == installer.DDiskHA.VISUDO:
                return SimpleNamespace(returncode=0)
            return original_run(arguments, **kwargs)

        # Preserve real archive checks while simulating privileged validation.
        self.commands.side_effect = run_command
        control = patch.object(installer, "systemctl")
        self.control = control.start()
        self.addCleanup(control.stop)
        readiness = patch.object(installer, "restart")
        self.restart = readiness.start()
        self.addCleanup(readiness.stop)
        metadata = patch.object(installer.DDiskHA, "INSTALL_DIR", str(self.target))
        metadata.start()
        self.addCleanup(metadata.stop)
        output = redirect_stdout(io.StringIO())
        output.__enter__()
        self.addCleanup(output.__exit__, None, None, None)

    def test_cmdb_discovery_convention_matches_installed_metadata(self):
        name = "DiskHA"
        # The unpatched declaration must use CMDB's lowercase application name.
        source = (ROOT / "diskha/constants/DDiskHA.py").read_text()
        declarations = {node.target.id: ast.literal_eval(node.value)
                        for node in ast.walk(ast.parse(source))
                        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
                        and (node.target.id.startswith("CMDB_")
                             or node.target.id in {"VERSION", "INSTALL_DIR"})}
        self.assertEqual(declarations["INSTALL_DIR"], "/opt/prod/" + name.lower())
        installer.install()
        constants = self.target / name.lower() / "constants" / ("D" + name + ".py")
        self.assertEqual(constants.read_text(), source)
        self.assertTrue(declarations["VERSION"])

    def test_installer_generates_network_settings_from_declaration(self):
        with patch.object(installer.DDiskHA, "CMDB_NETWORK", (("http", "127.0.0.2", 23456),)):
            installer.install()
        settings = json.loads((self.target / "conf/diskha.json").read_text())
        self.assertEqual(settings["network"], {"http": {"interface": "127.0.0.2", "port": 23456}})

    def test_legacy_upgrade_preserves_state_and_locks_through_canonical_alias(self):
        installer.install()
        self.target.rename(self.legacy)
        old_package = self.legacy / "disk_ha"
        (self.legacy / "diskha").rename(old_package)
        credentials = self.legacy / "conf/database.env"
        credentials.write_text("saved credentials")
        credentials.chmod(0o600)
        state = self.legacy / "data/health.json"
        state.write_text("saved result")
        lock = self.legacy / "conf/health.lock"
        lock.touch()
        identity = lock.stat().st_ino
        self.reading.side_effect = None
        self.reading.return_value = {"enabled": True, "expression": "*/20 * * * *"}
        self.sync_reading.side_effect = None
        self.sync_reading.return_value = {"enabled": False, "expression": ""}
        installer.install()
        self.assertTrue(self.target.is_symlink())
        self.assertTrue(self.target.samefile(self.legacy))
        self.assertEqual((self.target / "conf/health.lock").stat().st_ino, identity)
        self.assertEqual(credentials.read_text(), "saved credentials")
        self.assertEqual(credentials.stat().st_mode & 0o777, 0o600)
        self.assertEqual(state.read_text(), "saved result")
        self.assertFalse(old_package.exists())
        self.assertTrue((self.target / "diskha/constants/DDiskHA.py").is_file())
        self.assertEqual(json.loads((self.target / "conf/health.json").read_text())["expression"],
                         "*/20 * * * *")
        self.assertFalse(json.loads((self.target / "conf/sync.json").read_text())["enabled"])
        self.assertIn(f"ExecStart={self.target}/bin/disk-ha-web", Path(installer.DDiskHA.WEB_SERVICE_FILE).read_text())
        installer.install()
        installer.uninstall()
        self.assertFalse((self.target / "diskha").exists())
        self.assertEqual(credentials.read_text(), "saved credentials")
        self.assertEqual(state.read_text(), "saved result")

    def test_conflicting_installation_roots_fail_before_overwriting_state(self):
        self.target.mkdir()
        self.legacy.mkdir()
        saved = self.legacy / "saved"
        saved.write_text("existing state")
        with self.assertRaisesRegex(ValueError, "Both installation paths"):
            installer.install()
        self.assertEqual(saved.read_text(), "existing state")
        self.assertFalse((self.target / "bin").exists())
        self.control.assert_not_called()

    def test_reinstall_restores_deleted_legacy_home_for_retained_account(self):
        account = SimpleNamespace(pw_uid=984, pw_gid=979, pw_shell=installer.DDiskHA.NOLOGIN,
                                  pw_dir=str(self.legacy))
        with patch("pwd.getpwnam", return_value=account), \
                patch("grp.getgrnam", return_value=SimpleNamespace(gr_gid=979)), \
                patch("os.geteuid", return_value=0):
            root = installer.installation_root(installing=True)
            self.assertEqual(self.provision_account(), account)
        self.assertEqual(root, self.target)
        self.assertTrue(self.legacy.is_symlink())
        self.assertTrue(self.legacy.samefile(self.target))
        installer.install()
        self.assertTrue((self.target / "diskha/constants/DDiskHA.py").is_file())
        installer.install()
        installer.uninstall()
        self.assertTrue(self.legacy.samefile(self.target))
        self.assertTrue((self.legacy / "conf/health.json").is_file())

    def test_uninstall_legacy_installation_without_prior_upgrade(self):
        installer.install()
        self.target.rename(self.legacy)
        (self.legacy / "diskha").rename(self.legacy / "disk_ha")
        installer.uninstall()
        self.assertTrue(self.target.samefile(self.legacy))
        self.assertFalse((self.legacy / "disk_ha").exists())
        self.assertFalse((self.legacy / "bin/disk-ha-web").exists())
        self.assertTrue((self.legacy / "conf/health.json").is_file())
        self.scheduling.assert_any_call(self.target, None)

    def test_install_upgrade_and_uninstall_preserve_local_files(self):
        installer.install()
        constants = self.target / "diskha/constants/DDiskHA.py"
        expected = (ROOT / "diskha/constants/DDiskHA.py").read_bytes()
        self.assertEqual(constants.read_bytes(), expected)
        for directory in (self.target, self.target / "bin", constants.parent.parent, constants.parent):
            self.assertEqual(directory.stat().st_mode & 0o777, 0o755)
        self.assertEqual(constants.stat().st_mode & 0o777, 0o644)
        executable = self.target / "bin/disk-ha-web"
        self.assertEqual(executable.stat().st_mode & 0o777, 0o755)
        with zipfile.ZipFile(executable) as archive:
            self.assertEqual(archive.read("diskha/server/static/index.html"),
                             (ROOT / "diskha/server/static/index.html").read_bytes())
        service = Path(installer.DDiskHA.WEB_SERVICE_FILE)
        self.assertEqual(service.stat().st_mode & 0o777, 0o644)
        self.assertIn(f"ExecStart={executable} --config ${{CREDENTIALS_DIRECTORY}}/diskha.json",
                      service.read_text())
        self.assertIn(f"LoadCredential=diskha.json:{self.target}/conf/diskha.json", service.read_text())
        self.assertNotIn("--port", service.read_text())
        self.assertIn("User=diskha\nGroup=diskha", service.read_text())
        self.assertIn(f"LoadCredential=database.env:{installer.DDiskHA.DATABASE_ENV}", service.read_text())
        self.assertNotIn("LoadCredential=health.json", service.read_text())
        health_service = Path(installer.DDiskHA.HEALTH_SERVICE_FILE)
        sudoers = Path(installer.DDiskHA.HEALTH_SUDOERS_FILE)
        self.assertIn("User=root", health_service.read_text())
        email_service = Path(installer.DDiskHA.EMAIL_REPORT_SERVICE_FILE)
        self.assertIn("--email-report", email_service.read_text())
        self.assertIn("User=root", email_service.read_text())
        self.assertEqual(email_service.stat().st_mode & 0o777, 0o644)
        self.assertIn(f"ExecStart={self.target}/bin/disk-ha-check", health_service.read_text())
        sync_service = Path(installer.DDiskHA.SYNC_SERVICE_FILE)
        self.assertIn("User=root", sync_service.read_text())
        self.assertIn(f"ExecStart={self.target}/bin/disk-ha-sync --config {self.target}/conf/sync.json "
                      f"--result {self.target}/data/sync-output.log", sync_service.read_text())
        self.assertEqual(sync_service.stat().st_mode & 0o777, 0o644)
        self.assertEqual(sudoers.stat().st_mode & 0o777, 0o440)
        self.assertEqual(sudoers.read_text(),
                         "diskha ALL=(root) NOPASSWD: /usr/bin/systemctl start --no-block disk-ha-health.service\n"
                         "diskha ALL=(root) NOPASSWD: /usr/bin/systemctl start --no-block disk-ha-email-report.service\n"
                         "diskha ALL=(root) NOPASSWD: /usr/bin/systemctl start --no-block disk-ha-sync.service\n"
                         f'diskha ALL=(root) NOPASSWD: {self.target}/bin/disk-ha-schedule ""\n')
        self.control.assert_any_call("enable", service.name)
        self.restart.assert_called_once_with()
        self.assertEqual((self.target / "conf").stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.target / "data").stat().st_mode & 0o777, 0o750)
        self.assertEqual((self.target / "data/health.log").stat().st_mode & 0o777, 0o640)
        self.assertEqual((self.target / "conf/health.json").stat().st_mode & 0o777, 0o600)
        checker = self.target / "bin/disk-ha-check"
        self.assertTrue(checker.exists())
        self.assertEqual(checker.stat().st_mode & 0o777, 0o755)
        result = subprocess.run(
            ["/usr/bin/python3", "-B", "-c",
             "from diskha.constants.DDiskHA import DDiskHA; print(DDiskHA.VERSION)"],
            cwd=self.target, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), installer.DDiskHA.VERSION)
        preserved = {}
        for name in ("conf/settings.json", "conf/credentials.env", "data/state.json"):
            path = self.target / name
            path.write_text("Local configuration or data\n")
            path.chmod(0o600)
            preserved[path] = path.read_bytes()
        constants.write_text('VERSION = "old release"\n')
        legacy_constants = constants.with_name("DDISKHA.py")
        legacy_constants.write_text('class DDISKHA:\n    VERSION = "old release"\n')
        installer.install()
        self.assertEqual(constants.read_bytes(), expected)
        self.assertFalse(legacy_constants.exists())
        installer.uninstall()
        installer.uninstall()
        self.assertFalse((self.target / "diskha").exists())
        self.assertFalse(executable.exists())
        self.assertFalse(checker.exists())
        self.assertFalse((self.target / "bin/disk-ha-sync").exists())
        self.sync_scheduling.assert_any_call(self.target, None)
        self.assertFalse((self.target / "bin/disk-ha-schedule").exists())
        self.scheduling.assert_any_call(self.target, None)
        self.assertFalse(service.exists())
        self.assertFalse(health_service.exists())
        self.assertFalse(Path(installer.DDiskHA.SYNC_SERVICE_FILE).exists())
        self.assertFalse(Path(installer.DDiskHA.EMAIL_REPORT_SERVICE_FILE).exists())
        self.assertFalse(sudoers.exists())
        self.control.assert_any_call("disable", "--now", service.name)
        for path, content in preserved.items():
            self.assertEqual(path.read_bytes(), content)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_web_configuration_is_private_and_survives_upgrade_and_removal(self):
        installer.install()
        configuration = self.target / "conf/diskha.json"
        self.assertEqual(json.loads(configuration.read_text())["network"]["http"]["port"], 23300)
        self.assertEqual(configuration.stat().st_mode & 0o777, 0o600)
        with zipfile.ZipFile(self.target / "bin/disk-ha-web") as archive:
            self.assertIn("diskha/interface/WebConfiguration.py", archive.namelist())
        saved = '{"request_timeout":30}'
        configuration.write_text(saved)
        installer.install()
        self.assertEqual(configuration.read_text(), saved)
        installer.uninstall()
        self.assertEqual(configuration.read_text(), saved)
        self.assertEqual(configuration.stat().st_mode & 0o777, 0o600)

    def test_invalid_web_configuration_prevents_deployment(self):
        installer.install()
        archive = self.target / "bin/disk-ha-web"
        previous = archive.read_bytes()
        configuration = self.target / "conf/diskha.json"
        configuration.write_text('{"network": {"http": {"interface": "127.0.0.1", "port": 0}}, "request_timeout": 15}')
        self.restart.reset_mock()
        with self.assertRaisesRegex(ValueError, "port must be an integer between"):
            installer.install()
        self.assertEqual(archive.read_bytes(), previous)
        self.restart.assert_not_called()

    def test_staging_failure_keeps_installed_metadata(self):
        installer.install()
        constants = self.target / "diskha/constants/DDiskHA.py"
        original = constants.read_bytes()
        with patch.object(installer.shutil, "copytree", side_effect=OSError("Staging failed")):
            with self.assertRaisesRegex(OSError, "Staging failed"):
                installer.install()
        self.assertEqual(constants.read_bytes(), original)
        self.assertEqual(list(self.target.glob(".disk-ha-install-*")), [])

    def test_invalid_sudo_rule_keeps_previous_permission_and_cleans_candidate(self):
        installer.install()
        rule = Path(installer.DDiskHA.HEALTH_SUDOERS_FILE)
        previous = rule.read_bytes()
        self.restart.reset_mock()
        self.commands.side_effect = subprocess.CalledProcessError(1, [installer.DDiskHA.VISUDO])
        with self.assertRaises(subprocess.CalledProcessError):
            installer.install()
        self.assertEqual(rule.read_bytes(), previous)
        self.assertEqual(list(rule.parent.glob(".disk-ha-health-*")), [])
        self.restart.assert_not_called()

    def test_health_configuration_results_and_logs_survive_upgrade_and_removal(self):
        installer.install()
        configuration = self.target / "conf/health.json"
        values = json.loads(configuration.read_text())
        self.assertTrue(values["enabled"])
        self.assertEqual(values["expression"], "0 14 * * *")
        self.assertEqual(values["mail"]["config_path"], "/root/.msmtprc")
        values.update(enabled=True, expression="*/30 * * * *",
                      mail={"recipient": "operator@example.com", "sender": "disk@example.com",
                            "config_path": "/tmp/mail.conf", "timeout": 10})
        configuration.write_text(json.dumps(values))
        result = self.target / "data/health.json"
        result.write_text("saved health result")
        log = self.target / "data/health.log"
        log.write_text("saved health log")
        with patch.object(installer.os, "access", return_value=True):
            installer.install()
        self.assertTrue(self.scheduling.call_args.args[1].enabled)
        self.assertEqual(self.scheduling.call_args.args[1].expression, "*/30 * * * *")
        self.control.assert_any_call("enable", "--now", "cron.service")
        self.assertEqual(json.loads(configuration.read_text()), values)
        self.assertEqual(result.read_text(), "saved health result")
        self.assertEqual(log.read_text(), "saved health log")
        installer.uninstall()
        self.assertEqual(json.loads(configuration.read_text()), values)
        self.assertEqual(result.read_text(), "saved health result")
        self.assertEqual(log.read_text(), "saved health log")

    def test_health_checker_archive_runs_without_checkout_when_disabled(self):
        installer.install()
        configuration = self.target / "conf/health.json"
        values = json.loads(configuration.read_text())
        values["enabled"] = False
        configuration.write_text(json.dumps(values))
        checker = self.target / "bin/disk-ha-check"
        result = subprocess.run(["/usr/bin/python3", "-B", str(checker), "--help"],
                                cwd=self.target, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--config", result.stdout)
        # Invoke the runner function directly to avoid requiring root in the test.
        result = subprocess.run(
            ["/usr/bin/python3", "-B", "-c",
             "from pathlib import Path; from diskha.health import run; "
             "raise SystemExit(run(Path('conf/health.json'), Path('data/health.json')))"],
            cwd=self.target, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("monitoring is disabled", result.stdout)
        self.assertFalse((self.target / "data/health.json").exists())

    def test_upgrade_retains_live_cron_schedule_and_external_removal(self):
        installer.install()
        config = self.target / "conf/health.json"
        original_mail = json.loads(config.read_text())["mail"]
        self.reading.side_effect = None
        self.reading.return_value = {"enabled": True, "expression": "*/20 * * * *"}
        installer.install()
        self.assertEqual(json.loads(config.read_text())["expression"], "*/20 * * * *")
        self.assertEqual(json.loads(config.read_text())["mail"], original_mail)
        self.reading.return_value = {"enabled": False, "expression": ""}
        installer.install()
        self.assertFalse(json.loads(config.read_text())["enabled"])
        self.assertFalse(self.scheduling.call_args.args[1].enabled)

    def test_sync_install_upgrade_and_removal_preserve_settings_and_output(self):
        installer.install()
        config = self.target / "conf/sync.json"
        values = json.loads(config.read_text())
        self.assertTrue(values["enabled"])
        self.assertEqual(values["expression"], "0 */4 * * *")
        self.assertEqual(config.stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.target / "data/sync.log").stat().st_mode & 0o777, 0o640)
        worker = self.target / "bin/disk-ha-sync"
        self.assertEqual(worker.stat().st_mode & 0o777, 0o755)
        for name in ("SyncConfiguration", "MountInspection", "RsyncMirror", "SyncSchedule", "CronSchedule"):
            self.assertTrue((self.target / f"diskha/interface/{name}.py").is_file())
        result = subprocess.run([str(worker), "--help"], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--result", result.stdout)
        output = self.target / "data/sync-output.log"
        output.write_text("last verbose output")
        values["timeout"] = 12345
        config.write_text(json.dumps(values))
        self.sync_reading.side_effect = None
        self.sync_reading.return_value = {"enabled": True, "expression": "0 */6 * * *"}
        installer.install()
        self.assertEqual(json.loads(config.read_text())["expression"], "0 */6 * * *")
        self.assertEqual(json.loads(config.read_text())["timeout"], 12345)
        self.assertEqual(json.loads(config.read_text())["source"], values["source"])
        installer.uninstall()
        self.assertFalse(worker.exists())
        self.assertTrue(config.is_file())
        self.assertEqual(output.read_text(), "last verbose output")

    def test_wrappers_delegate_from_a_checkout_with_spaces(self):
        with tempfile.TemporaryDirectory(prefix="disk-ha-wrappers-") as temporary:
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
        self.assertIn("disk-ha:", errors.getvalue())

    def test_database_failure_does_not_replace_server_or_restart(self):
        installer.install()
        archive = self.target / "bin/disk-ha-web"
        before = archive.read_bytes()
        self.restart.reset_mock()
        with patch.object(installer.DatabaseProvisioning, "provision", side_effect=ValueError("Unavailable")):
            with self.assertRaisesRegex(ValueError, "Unavailable"):
                installer.install()
        self.assertEqual(archive.read_bytes(), before)
        self.restart.assert_not_called()


if __name__ == "__main__":
    unittest.main()
