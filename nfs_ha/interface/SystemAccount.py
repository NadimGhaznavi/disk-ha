"""Provision a persistent, non-login Linux service account."""

import grp
import os
import pwd
import subprocess

from nfs_ha.constants.DNFSHA import DNFSHA


class SystemAccount:
    @staticmethod
    def provision():
        if os.geteuid() != 0:
            raise PermissionError("Run account provisioning as root.")
        try:
            group = grp.getgrnam(DNFSHA.SERVICE_GROUP)
        except KeyError:
            subprocess.run([DNFSHA.GROUPADD, "--system", DNFSHA.SERVICE_GROUP],
                           check=True, timeout=30)
            group = grp.getgrnam(DNFSHA.SERVICE_GROUP)
        if group.gr_gid == 0:
            raise ValueError("The service group must not be root.")
        try:
            account = pwd.getpwnam(DNFSHA.SERVICE_USER)
        except KeyError:
            subprocess.run(
                [DNFSHA.USERADD, "--system", "--gid", DNFSHA.SERVICE_GROUP,
                 "--home-dir", DNFSHA.INSTALL_DIR, "--no-create-home",
                 "--shell", DNFSHA.NOLOGIN, DNFSHA.SERVICE_USER], check=True, timeout=30)
            account = pwd.getpwnam(DNFSHA.SERVICE_USER)
        if (account.pw_uid == 0 or account.pw_gid != group.gr_gid
                or account.pw_shell != DNFSHA.NOLOGIN or account.pw_dir != DNFSHA.INSTALL_DIR):
            raise ValueError("Existing nfsha account must have the project home, nfsha group, and nologin shell.")
        return account
