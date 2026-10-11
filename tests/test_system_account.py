"""Verify account creation and reuse without changing host accounts."""

import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from diskha.constants.DDiskHA import DDiskHA
from diskha.interface.SystemAccount import SystemAccount


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.account = SimpleNamespace(pw_uid=998, pw_gid=998, pw_shell=DDiskHA.NOLOGIN,
                                       pw_dir=DDiskHA.INSTALL_DIR)
        self.group = SimpleNamespace(gr_gid=998)

    def test_missing_account_and_group_are_created_without_login_or_home_creation(self):
        with patch("os.geteuid", return_value=0), \
                patch("grp.getgrnam", side_effect=[KeyError(), self.group]), \
                patch("pwd.getpwnam", side_effect=[KeyError(), self.account]), \
                patch("diskha.interface.SystemAccount.subprocess.run") as run:
            self.assertEqual(SystemAccount.provision(), self.account)
        self.assertEqual(run.call_args_list[0].args[0], [DDiskHA.GROUPADD, "--system", "diskha"])
        command = run.call_args_list[1].args[0]
        self.assertIn("--no-create-home", command)
        self.assertIn(DDiskHA.NOLOGIN, command)
        self.assertIn("--system", command)
        for call in run.call_args_list:
            self.assertEqual(call.kwargs, {"check": True, "timeout": 30})

    def test_existing_account_is_reused_without_mutation(self):
        with patch("os.geteuid", return_value=0), \
                patch("grp.getgrnam", return_value=self.group), \
                patch("pwd.getpwnam", return_value=self.account), \
                patch("diskha.interface.SystemAccount.subprocess.run") as run:
            self.assertEqual(SystemAccount.provision(), self.account)
        run.assert_not_called()

    def test_conflicting_existing_account_is_rejected(self):
        for field, value, message in (("pw_uid", 0, "UID is 0"),
                                      ("pw_gid", 0, "primary GID is 0; expected 998"),
                                      ("pw_shell", "/bin/bash", "shell is '/bin/bash'"),
                                      ("pw_dir", "/root", "home is '/root'")):
            with self.subTest(field=field):
                account = SimpleNamespace(**vars(self.account))
                setattr(account, field, value)
                with patch("os.geteuid", return_value=0), \
                        patch("grp.getgrnam", return_value=self.group), \
                        patch("pwd.getpwnam", return_value=account), \
                        patch("diskha.interface.SystemAccount.subprocess.run") as run:
                    with self.assertRaisesRegex(ValueError, message):
                        SystemAccount.provision()
                    run.assert_not_called()

    def test_error_reports_all_conflicting_settings(self):
        self.account.pw_gid = 123
        self.account.pw_dir = "/home/diskha"
        self.account.pw_shell = "/bin/bash"
        with patch("os.geteuid", return_value=0), \
                patch("grp.getgrnam", return_value=self.group), \
                patch("pwd.getpwnam", return_value=self.account), \
                patch("diskha.interface.SystemAccount.subprocess.run") as run:
            with self.assertRaises(ValueError) as error:
                SystemAccount.provision()
        self.assertIn("primary GID is 123; expected 998 (diskha)", str(error.exception))
        self.assertIn("shell is '/bin/bash'", str(error.exception))
        self.assertIn("home is '/home/diskha'", str(error.exception))
        run.assert_not_called()

    def test_legacy_account_home_is_reused_only_when_installation_alias_matches(self):
        with tempfile.TemporaryDirectory() as temporary:
            legacy = Path(temporary) / "disk-ha"
            root = Path(temporary) / "diskha"
            legacy.mkdir()
            self.account.pw_dir = str(legacy)
            with patch.object(DDiskHA, "INSTALL_DIR", str(root)), \
                    patch.object(DDiskHA, "LEGACY_INSTALL_DIR", str(legacy)), \
                    patch("os.geteuid", return_value=0), \
                    patch("grp.getgrnam", return_value=self.group), \
                    patch("pwd.getpwnam", return_value=self.account), \
                    patch("diskha.interface.SystemAccount.subprocess.run") as run:
                with self.assertRaises(ValueError):
                    SystemAccount.provision()
                root.symlink_to(legacy, target_is_directory=True)
                self.assertEqual(SystemAccount.provision(), self.account)
                run.assert_not_called()

    def test_nonroot_provisioning_is_rejected(self):
        with patch("os.geteuid", return_value=1000), self.assertRaises(PermissionError):
            SystemAccount.provision()
