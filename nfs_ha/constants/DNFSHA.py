"""Shared nfs-ha constants, including readable CMDB discovery metadata."""

from typing import Final


class DNFSHA:
    VERSION: Final[str] = "0.0.1"
    CMDB_SUBTYPE: Final[str] = "Disk Monitoring and Mirroring"
    CMDB_SUPPLIER: Final[str] = "Nadim-Daniel"
    CMDB_CODENAME: Final[str] = "Scaffolding"
    INSTALL_DIR: Final[str] = "/opt/prod/nfs-ha"
