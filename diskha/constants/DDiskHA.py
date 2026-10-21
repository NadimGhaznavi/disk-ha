"""Shared disk-ha constants, including readable CMDB discovery metadata."""

from typing import Final


class DDiskHA:
    VERSION: Final[str] = "2.3.2"
    CMDB_TYPE: Final[str] = "application"
    CMDB_SUBTYPE: Final[str] = "Disk Monitoring and Mirroring"
    CMDB_SUPPLIER: Final[str] = "Nadim-Daniel"
    CMDB_CODENAME: Final[str] = "Apollo"
    CMDB_COMPONENTS: Final[tuple[tuple[str, str], ...]] = (
        ("Configuration", "conf"),
        ("Saved Data", "data"),
    )
    CMDB_DATABASES: Final[tuple[tuple[str, str], ...]] = (("DiskHA", "diskha"),)
    CMDB_NETWORK: Final[tuple[tuple[str, str, int], ...]] = (("http", "0.0.0.0", 23300),)
    INSTALL_DIR: Final[str] = "/opt/prod/diskha"
    LEGACY_INSTALL_DIR: Final[str] = "/opt/prod/disk-ha"
    CONFIG_SUBDIR: Final[str] = dict(CMDB_COMPONENTS)["Configuration"]
    DATA_SUBDIR: Final[str] = dict(CMDB_COMPONENTS)["Saved Data"]
    CONFIG_DIR: Final[str] = INSTALL_DIR + "/" + CONFIG_SUBDIR
    DATA_DIR: Final[str] = INSTALL_DIR + "/" + DATA_SUBDIR
    WEB_CONFIG: Final[str] = CONFIG_DIR + "/diskha.json"
    WEB_READY_PATH: Final[str] = "/ready"
    WEB_SERVICE_FILE: Final[str] = "/etc/systemd/system/disk-ha-web.service"
    SYSTEMCTL: Final[str] = "/usr/bin/systemctl"
    SERVICE_USER: Final[str] = "diskha"
    SERVICE_GROUP: Final[str] = "diskha"
    USERADD: Final[str] = "/usr/sbin/useradd"
    GROUPADD: Final[str] = "/usr/sbin/groupadd"
    NOLOGIN: Final[str] = "/usr/sbin/nologin"
    MARIADB: Final[str] = "/usr/bin/mariadb"
    DATABASE_USER: Final[str] = "diskha"
    DATABASE_ENV: Final[str] = CONFIG_DIR + "/database.env"
    DATABASE_CONNECT_TIMEOUT: Final[int] = 5
    SMARTCTL: Final[str] = "/usr/sbin/smartctl"
    MSMTP: Final[str] = "/usr/bin/msmtp"
    CRONTAB: Final[str] = "/usr/bin/crontab"
    HEALTH_CONFIG: Final[str] = CONFIG_DIR + "/health.json"
    HEALTH_RESULT: Final[str] = DATA_DIR + "/health.json"
    HEALTH_SERVICE_FILE: Final[str] = "/etc/systemd/system/disk-ha-health.service"
    EMAIL_REPORT_SERVICE_FILE: Final[str] = "/etc/systemd/system/disk-ha-email-report.service"
    HEALTH_SUDOERS_FILE: Final[str] = "/etc/sudoers.d/disk-ha-health"
    SUDO: Final[str] = "/usr/bin/sudo"
    VISUDO: Final[str] = "/usr/sbin/visudo"
    RSYNC: Final[str] = "/usr/bin/rsync"
    FINDMNT: Final[str] = "/usr/bin/findmnt"
    LSBLK: Final[str] = "/usr/bin/lsblk"
    SYNC_CONFIG: Final[str] = CONFIG_DIR + "/sync.json"
    SYNC_RESULT: Final[str] = DATA_DIR + "/sync-output.log"
    SYNC_SERVICE_FILE: Final[str] = "/etc/systemd/system/disk-ha-sync.service"
