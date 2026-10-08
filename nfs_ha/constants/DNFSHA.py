"""Shared nfs-ha constants, including readable CMDB discovery metadata."""

from typing import Final


class DNFSHA:
    VERSION: Final[str] = "0.1.0"
    CMDB_SUBTYPE: Final[str] = "Disk Monitoring and Mirroring"
    CMDB_SUPPLIER: Final[str] = "Nadim-Daniel"
    CMDB_CODENAME: Final[str] = "Project Scaffolding"
    INSTALL_DIR: Final[str] = "/opt/prod/nfs-ha"
    WEB_HOST: Final[str] = "0.0.0.0"
    WEB_PORT: Final[int] = 23300
    WEB_REQUEST_TIMEOUT: Final[int] = 15
    WEB_READY_PATH: Final[str] = "/ready"
    WEB_SERVICE_FILE: Final[str] = "/etc/systemd/system/nfs-ha-web.service"
    SYSTEMCTL: Final[str] = "/usr/bin/systemctl"
    SERVICE_USER: Final[str] = "nfsha"
    SERVICE_GROUP: Final[str] = "nfsha"
    USERADD: Final[str] = "/usr/sbin/useradd"
    GROUPADD: Final[str] = "/usr/sbin/groupadd"
    NOLOGIN: Final[str] = "/usr/sbin/nologin"
    MARIADB: Final[str] = "/usr/bin/mariadb"
    DATABASE_NAME: Final[str] = "nfsha"
    DATABASE_USER: Final[str] = "nfsha"
    DATABASE_ENV: Final[str] = "/opt/prod/nfs-ha/conf/database.env"
    DATABASE_CONNECT_TIMEOUT: Final[int] = 5
