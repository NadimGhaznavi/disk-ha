"""Provision a persistent, non-login Linux service account."""

import grp
import os
from pathlib import Path
import pwd
import subprocess

from diskha.constants.DDiskHA import DDiskHA


class SystemAccount:
    @staticmethod
    def provision():
        if os.geteuid() != 0:
            raise PermissionError("Run account provisioning as root.")
        try:
            group = grp.getgrnam(DDiskHA.SERVICE_GROUP)
        except KeyError:
            subprocess.run([DDiskHA.GROUPADD, "--system", DDiskHA.SERVICE_GROUP],
                           check=True, timeout=30)
            group = grp.getgrnam(DDiskHA.SERVICE_GROUP)
        if group.gr_gid == 0:
            raise ValueError("The service group must not be root.")
        try:
            account = pwd.getpwnam(DDiskHA.SERVICE_USER)
        except KeyError:
            subprocess.run(
                [DDiskHA.USERADD, "--system", "--gid", DDiskHA.SERVICE_GROUP,
                 "--home-dir", DDiskHA.INSTALL_DIR, "--no-create-home",
                 "--shell", DDiskHA.NOLOGIN, DDiskHA.SERVICE_USER], check=True, timeout=30)
            account = pwd.getpwnam(DDiskHA.SERVICE_USER)
        home_matches = account.pw_dir == DDiskHA.INSTALL_DIR
        if account.pw_dir == DDiskHA.LEGACY_INSTALL_DIR:
            root = Path(DDiskHA.INSTALL_DIR)
            home_matches = root.exists() and root.samefile(account.pw_dir)
        if (account.pw_uid == 0 or account.pw_gid != group.gr_gid
                or account.pw_shell != DDiskHA.NOLOGIN or not home_matches):
            raise ValueError("Existing diskha account must have the project home, diskha group, and nologin shell.")
        return account
