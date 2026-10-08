"""Provision a persistent, non-login Linux service account."""

import grp
import os
import pwd
import subprocess

from disk_ha.constants.DDISKHA import DDISKHA


class SystemAccount:
    @staticmethod
    def provision():
        if os.geteuid() != 0:
            raise PermissionError("Run account provisioning as root.")
        try:
            group = grp.getgrnam(DDISKHA.SERVICE_GROUP)
        except KeyError:
            subprocess.run([DDISKHA.GROUPADD, "--system", DDISKHA.SERVICE_GROUP],
                           check=True, timeout=30)
            group = grp.getgrnam(DDISKHA.SERVICE_GROUP)
        if group.gr_gid == 0:
            raise ValueError("The service group must not be root.")
        try:
            account = pwd.getpwnam(DDISKHA.SERVICE_USER)
        except KeyError:
            subprocess.run(
                [DDISKHA.USERADD, "--system", "--gid", DDISKHA.SERVICE_GROUP,
                 "--home-dir", DDISKHA.INSTALL_DIR, "--no-create-home",
                 "--shell", DDISKHA.NOLOGIN, DDISKHA.SERVICE_USER], check=True, timeout=30)
            account = pwd.getpwnam(DDISKHA.SERVICE_USER)
        if (account.pw_uid == 0 or account.pw_gid != group.gr_gid
                or account.pw_shell != DDISKHA.NOLOGIN or account.pw_dir != DDISKHA.INSTALL_DIR):
            raise ValueError("Existing diskha account must have the project home, diskha group, and nologin shell.")
        return account
