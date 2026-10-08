"""Install, upgrade, or remove nfs-ha scaffolding; preserve configuration and data.

The application package and readable CMDB metadata are deployed now. Runtime
commands and scheduling will be added when the application is implemented.
"""

import argparse
import os
from pathlib import Path
import shutil
import sys
import tempfile

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))

from nfs_ha.constants.DNFSHA import DNFSHA


def install() -> None:
    root = Path(DNFSHA.INSTALL_DIR)
    root.mkdir(parents=True, exist_ok=True)
    root.chmod(0o755)
    for name in ("bin", "conf", "data"):
        directory = root / name
        directory.mkdir(exist_ok=True)
        directory.chmod(0o755 if name == "bin" else 0o700)
    # Stage the package before replacing installed files. Individual replacements
    # are atomic, including the constants file read by CMDB scanners.
    with tempfile.TemporaryDirectory(prefix=".nfs-ha-install-", dir=root) as temporary:
        staged = Path(temporary) / "nfs_ha"
        shutil.copytree(REPOSITORY / "nfs_ha", staged,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        package = root / "nfs_ha"
        package.mkdir(exist_ok=True)
        package.chmod(0o755)
        for source in sorted(staged.rglob("*")):
            destination = package / source.relative_to(staged)
            if source.is_dir():
                destination.mkdir(exist_ok=True)
                destination.chmod(0o755)
            else:
                source.chmod(0o644)
                source.replace(destination)
    print(f"Installed nfs-ha {DNFSHA.VERSION} in {root}; configuration and data preserved.")


def uninstall() -> None:
    package = Path(DNFSHA.INSTALL_DIR) / "nfs_ha"
    if package.exists():
        shutil.rmtree(package)
    print("Removed nfs-ha's Python package and CMDB metadata; configuration and data preserved.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "upgrade", "uninstall"))
    args = parser.parse_args()
    if os.geteuid() != 0:
        print("Run this script as root.", file=sys.stderr)
        return 1
    if sys.version_info < (3, 10):
        print("Python 3.10 or newer is required.", file=sys.stderr)
        return 1
    os.umask(0o077)
    try:
        {"install": install, "upgrade": install, "uninstall": uninstall}[args.action]()
    except (OSError, ValueError) as error:
        print(f"nfs-ha: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
