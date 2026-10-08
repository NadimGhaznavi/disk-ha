"""Install, restart, or remove nfs-ha's Web UI; preserve configuration and data."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener
import zipapp

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))

from nfs_ha.constants.DNFSHA import DNFSHA
from nfs_ha.interface.DatabaseProvisioning import DatabaseProvisioning
from nfs_ha.interface.SystemAccount import SystemAccount


def systemctl(*arguments: str) -> None:
    subprocess.run([DNFSHA.SYSTEMCTL, *arguments], check=True, timeout=30)


def restart() -> None:
    service = Path(DNFSHA.WEB_SERVICE_FILE).name
    systemctl("restart", service)
    url = f"http://127.0.0.1:{DNFSHA.WEB_PORT}{DNFSHA.WEB_READY_PATH}"
    opener = build_opener(ProxyHandler({}))
    deadline = time.monotonic() + 10
    while True:
        try:
            systemctl("is-active", "--quiet", service)
            with opener.open(Request(url, method="HEAD"), timeout=1) as response:
                if response.status != 200:
                    raise ValueError(f"Web UI returned HTTP {response.status}.")
            break
        except subprocess.CalledProcessError as error:
            if error.returncode != 3:
                raise
            if time.monotonic() >= deadline:
                raise ValueError(f"Web UI service did not become active; check journalctl -u {service}.") from None
        except HTTPError as error:
            status = error.code
            error.close()
            raise ValueError(f"Web UI readiness returned HTTP {status}; check journalctl -u {service}.") from None
        except (URLError, TimeoutError):
            if time.monotonic() >= deadline:
                raise ValueError(f"Web UI did not respond on port {DNFSHA.WEB_PORT}; "
                                 f"check journalctl -u {service}.") from None
        time.sleep(0.1)
    print(f"nfs-ha Web UI: active on port {DNFSHA.WEB_PORT} (listening on {DNFSHA.WEB_HOST})")


def install() -> None:
    for executable in ("/usr/bin/python3", DNFSHA.SYSTEMCTL, DNFSHA.MARIADB,
                       DNFSHA.USERADD, DNFSHA.GROUPADD, DNFSHA.NOLOGIN):
        if not os.access(executable, os.X_OK):
            raise ValueError(f"Required executable is missing: {executable}")
    account = SystemAccount.provision()
    root = Path(DNFSHA.INSTALL_DIR)
    root.mkdir(parents=True, exist_ok=True)
    root.chmod(0o755)
    for name in ("bin", "conf", "data"):
        directory = root / name
        directory.mkdir(exist_ok=True)
        directory.chmod(0o755 if name == "bin" else 0o700)
    os.chown(root / "data", account.pw_uid, account.pw_gid)
    DatabaseProvisioning().provision()
    # Stage the package before replacing installed files. Individual replacements
    # are atomic, including the constants file read by CMDB scanners.
    with tempfile.TemporaryDirectory(prefix=".nfs-ha-install-", dir=root) as temporary:
        staging = Path(temporary)
        source_root = staging / "source"
        staged = source_root / "nfs_ha"
        shutil.copytree(REPOSITORY / "nfs_ha", staged,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        (source_root / "__main__.py").write_text(
            "from nfs_ha.server.__main__ import main\nmain()\n")
        archive = staging / "nfs-ha-web"
        zipapp.create_archive(source_root, target=archive, interpreter="/usr/bin/python3")
        archive.chmod(0o755)
        archive.replace(root / "bin/nfs-ha-web")
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
    service = Path(DNFSHA.WEB_SERVICE_FILE)
    service.write_text(
        "[Unit]\nDescription=nfs-ha Web UI\nAfter=network.target\n\n"
        f"[Service]\nType=exec\nUser={DNFSHA.SERVICE_USER}\nGroup={DNFSHA.SERVICE_GROUP}\n"
        f"LoadCredential=database.env:{DNFSHA.DATABASE_ENV}\n"
        f"ExecStart={root}/bin/nfs-ha-web --host {DNFSHA.WEB_HOST} --port {DNFSHA.WEB_PORT}\n"
        "Restart=on-failure\nRestartSec=2\n\n[Install]\nWantedBy=multi-user.target\n")
    service.chmod(0o644)
    systemctl("daemon-reload")
    systemctl("enable", service.name)
    restart()
    print(f"Installed nfs-ha {DNFSHA.VERSION} in {root}; configuration and data preserved.")


def uninstall() -> None:
    root = Path(DNFSHA.INSTALL_DIR)
    service = Path(DNFSHA.WEB_SERVICE_FILE)
    if service.exists():
        systemctl("disable", "--now", service.name)
        service.unlink()
        systemctl("daemon-reload")
    (root / "bin/nfs-ha-web").unlink(missing_ok=True)
    package = Path(DNFSHA.INSTALL_DIR) / "nfs_ha"
    if package.exists():
        shutil.rmtree(package)
    print("Removed nfs-ha's Web UI service, executable, Python package, and CMDB metadata; "
          "accounts, database, configuration, credentials, and data preserved.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "upgrade", "uninstall", "restart"))
    args = parser.parse_args()
    if os.geteuid() != 0:
        print("Run this script as root.", file=sys.stderr)
        return 1
    if sys.version_info < (3, 10):
        print("Python 3.10 or newer is required.", file=sys.stderr)
        return 1
    os.umask(0o077)
    try:
        {"install": install, "upgrade": install, "uninstall": uninstall, "restart": restart}[args.action]()
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"nfs-ha: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
