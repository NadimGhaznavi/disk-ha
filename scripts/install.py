"""Install, restart, or remove disk-ha's Web UI; preserve configuration and data."""

import argparse
import fcntl
import json
import os
from pathlib import Path
import pwd
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

from diskha.constants.DDiskHA import DDiskHA
from diskha.interface.DatabaseProvisioning import DatabaseProvisioning
from diskha.interface.SystemAccount import SystemAccount
from diskha.interface.HealthConfiguration import HealthConfiguration
from diskha.interface.HealthSchedule import HealthSchedule
from diskha.interface.SyncConfiguration import SyncConfiguration
from diskha.interface.SyncSchedule import SyncSchedule
from diskha.interface.WebConfiguration import WebConfiguration


def systemctl(*arguments: str) -> None:
    subprocess.run([DDiskHA.SYSTEMCTL, *arguments], check=True, timeout=30)


def restart() -> None:
    configuration = WebConfiguration(installation_root() / "conf/web-interface.cfg")
    service = Path(DDiskHA.WEB_SERVICE_FILE).name
    systemctl("restart", service)
    host = "127.0.0.1" if configuration.host == "0.0.0.0" else configuration.host
    url = f"http://{host}:{configuration.port}{DDiskHA.WEB_READY_PATH}"
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
                raise ValueError(f"Web UI did not respond on port {configuration.port}; "
                                 f"check journalctl -u {service}.") from None
        time.sleep(0.1)
    print(f"disk-ha Web UI: active on port {configuration.port} (listening on {configuration.host})")


def installation_root(*, installing: bool = False) -> Path:
    """Use the CMDB path while retaining legacy state and lock identities."""
    root = Path(DDiskHA.INSTALL_DIR)
    legacy = Path(DDiskHA.LEGACY_INSTALL_DIR)
    if legacy.exists():
        if not legacy.is_dir():
            raise ValueError("Legacy installation path must be a directory.")
        if root.exists() or root.is_symlink():
            if not root.exists() or not root.samefile(legacy):
                raise ValueError("Both installation paths exist and differ; reconcile them before upgrading.")
        else:
            # Keep saved state and active worker locks at the same filesystem location.
            root.symlink_to(legacy, target_is_directory=True)
    elif installing:
        try:
            account = pwd.getpwnam(DDiskHA.SERVICE_USER)
        except KeyError:
            account = None
        if account is not None and account.pw_dir == str(legacy):
            # Removal may leave the service account after its home was deleted.
            # Restore that path without changing the persistent account.
            root.mkdir(parents=True, exist_ok=True)
            legacy.symlink_to(root, target_is_directory=True)
    return root


def install() -> None:
    for executable in ("/usr/bin/python3", DDiskHA.SYSTEMCTL, DDiskHA.MARIADB,
                       DDiskHA.USERADD, DDiskHA.GROUPADD, DDiskHA.NOLOGIN, DDiskHA.CRONTAB,
                       DDiskHA.SUDO, DDiskHA.VISUDO, DDiskHA.FINDMNT, DDiskHA.LSBLK):
        if not os.access(executable, os.X_OK):
            raise ValueError(f"Required executable is missing: {executable}")
    root = installation_root(installing=True)
    account = SystemAccount.provision()
    upgrading = (root / "bin/disk-ha-check").exists()
    sync_upgrading = (root / "bin/disk-ha-sync").exists()
    root.mkdir(parents=True, exist_ok=True)
    root.chmod(0o755)
    for name in ("bin", "conf", "data"):
        directory = root / name
        directory.mkdir(exist_ok=True)
        directory.chmod(0o755 if name == "bin" else 0o700)
    web_configuration = root / "conf/web-interface.cfg"
    if not web_configuration.exists():
        with web_configuration.open("x") as stream:
            stream.write((REPOSITORY / "conf/web-interface.cfg").read_text())
    web_configuration.chmod(0o600)
    WebConfiguration(web_configuration)
    # Root writes SMART results; the Web UI group may only read them.
    os.chown(root / "data", os.geteuid(), account.pw_gid)
    (root / "data").chmod(0o750)
    configuration = root / "conf/health.json"
    if not configuration.exists():
        with configuration.open("x") as stream:
            stream.write((REPOSITORY / "conf/health.json").read_text())
    configuration.chmod(0o600)
    health = HealthConfiguration(configuration)
    sync_configuration = root / "conf/sync.json"
    if not sync_configuration.exists():
        with sync_configuration.open("x") as stream:
            stream.write((REPOSITORY / "conf/sync.json").read_text())
    sync_configuration.chmod(0o600)
    sync = SyncConfiguration(sync_configuration)
    if sync.enabled:
        for executable in (DDiskHA.RSYNC, DDiskHA.FINDMNT):
            if not os.access(executable, os.X_OK):
                raise ValueError(f"Required executable is missing: {executable}")
    if health.enabled:
        for executable in (DDiskHA.SMARTCTL, DDiskHA.MSMTP, DDiskHA.CRONTAB):
            if not os.access(executable, os.X_OK):
                raise ValueError(f"Required executable is missing: {executable}")
    log = root / "data/health.log"
    if log.is_symlink() or (log.exists() and (not log.is_file() or log.stat().st_uid != os.geteuid())):
        raise ValueError("Health log must be a regular file owned by root.")
    log.touch(exist_ok=True)
    os.chown(log, os.geteuid(), account.pw_gid)
    log.chmod(0o640)
    sync_log = root / "data/sync.log"
    if sync_log.is_symlink() or (sync_log.exists() and (not sync_log.is_file() or sync_log.stat().st_uid != os.geteuid())):
        raise ValueError("Sync log must be a regular file owned by root.")
    sync_log.touch(exist_ok=True)
    os.chown(sync_log, os.geteuid(), account.pw_gid)
    sync_log.chmod(0o640)
    DatabaseProvisioning().provision()
    # Stage the package before replacing installed files. Individual replacements
    # are atomic, including the constants file read by CMDB scanners.
    with tempfile.TemporaryDirectory(prefix=".disk-ha-install-", dir=root) as temporary:
        staging = Path(temporary)
        source_root = staging / "source"
        staged = source_root / "diskha"
        shutil.copytree(REPOSITORY / "diskha", staged,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        (source_root / "__main__.py").write_text(
            "from diskha.server.__main__ import main\nmain()\n")
        archive = staging / "disk-ha-web"
        zipapp.create_archive(source_root, target=archive, interpreter="/usr/bin/python3")
        archive.chmod(0o755)
        archive.replace(root / "bin/disk-ha-web")
        (source_root / "__main__.py").write_text(
            "from diskha.health import main\nraise SystemExit(main())\n")
        checker = staging / "disk-ha-check"
        zipapp.create_archive(source_root, target=checker, interpreter="/usr/bin/python3")
        checker.chmod(0o755)
        checker.replace(root / "bin/disk-ha-check")
        (source_root / "__main__.py").write_text(
            "from diskha.schedule import main\nraise SystemExit(main())\n")
        scheduler = staging / "disk-ha-schedule"
        zipapp.create_archive(source_root, target=scheduler, interpreter="/usr/bin/python3")
        scheduler.chmod(0o755)
        scheduler.replace(root / "bin/disk-ha-schedule")
        (source_root / "__main__.py").write_text(
            "from diskha.sync import main\nraise SystemExit(main())\n")
        sync_worker = staging / "disk-ha-sync"
        zipapp.create_archive(source_root, target=sync_worker, interpreter="/usr/bin/python3")
        sync_worker.chmod(0o755)
        sync_worker.replace(root / "bin/disk-ha-sync")
        package = root / "diskha"
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
        # Remove the former metadata module after its replacement is deployed.
        (package / "constants/DDISKHA.py").unlink(missing_ok=True)
    legacy_package = root / "disk_ha"
    if legacy_package.exists():
        shutil.rmtree(legacy_package)
    service = Path(DDiskHA.WEB_SERVICE_FILE)
    health_service = Path(DDiskHA.HEALTH_SERVICE_FILE)
    health_service.write_text(
        "[Unit]\nDescription=disk-ha manual health check\n\n"
        "[Service]\nType=oneshot\nUser=root\nGroup=root\nUMask=0077\nTimeoutStartSec=0\n"
        f"ExecStart={root}/bin/disk-ha-check --config {configuration} --result {root}/data/health.json\n"
        f"StandardOutput=append:{root}/data/health.log\nStandardError=append:{root}/data/health.log\n")
    health_service.chmod(0o644)
    email_service = Path(DDiskHA.EMAIL_REPORT_SERVICE_FILE)
    email_service.write_text(
        "[Unit]\nDescription=disk-ha email verbose disk report\n\n"
        "[Service]\nType=oneshot\nUser=root\nGroup=root\nUMask=0077\nTimeoutStartSec=0\n"
        f"ExecStart={root}/bin/disk-ha-check --config {configuration} "
        f"--result {root}/data/health.json --email-report\n"
        f"StandardOutput=append:{root}/data/health.log\nStandardError=append:{root}/data/health.log\n")
    email_service.chmod(0o644)
    sync_service = Path(DDiskHA.SYNC_SERVICE_FILE)
    sync_service.write_text(
        "[Unit]\nDescription=disk-ha manual data sync\n\n"
        "[Service]\nType=oneshot\nUser=root\nGroup=root\nUMask=0077\nTimeoutStartSec=0\n"
        f"ExecStart={root}/bin/disk-ha-sync --config {sync_configuration} --result {root}/data/sync-output.log\n"
        f"StandardOutput=append:{root}/data/sync.log\nStandardError=append:{root}/data/sync.log\n")
    sync_service.chmod(0o644)
    # Grant exactly this start command, without access to other units or commands.
    sudoers = Path(DDiskHA.HEALTH_SUDOERS_FILE)
    with tempfile.NamedTemporaryFile(mode="w", prefix=".disk-ha-health-", dir=sudoers.parent,
                                     delete=False) as stream:
        staged_rule = Path(stream.name)
        stream.write(
            f"{DDiskHA.SERVICE_USER} ALL=(root) NOPASSWD: {DDiskHA.SYSTEMCTL} "
            f"start --no-block {health_service.name}\n"
            f"{DDiskHA.SERVICE_USER} ALL=(root) NOPASSWD: {DDiskHA.SYSTEMCTL} "
            f"start --no-block {email_service.name}\n"
            f"{DDiskHA.SERVICE_USER} ALL=(root) NOPASSWD: {DDiskHA.SYSTEMCTL} "
            f"start --no-block {sync_service.name}\n"
            f'{DDiskHA.SERVICE_USER} ALL=(root) NOPASSWD: {root}/bin/disk-ha-schedule ""\n')
    try:
        staged_rule.chmod(0o440)
        subprocess.run([DDiskHA.VISUDO, "-cf", str(staged_rule)],
                       check=True, capture_output=True, timeout=10)
        staged_rule.replace(sudoers)
    finally:
        staged_rule.unlink(missing_ok=True)
    service.write_text(
        "[Unit]\nDescription=disk-ha Web UI\nAfter=network.target\n\n"
        f"[Service]\nType=exec\nUser={DDiskHA.SERVICE_USER}\nGroup={DDiskHA.SERVICE_GROUP}\n"
        f"LoadCredential=database.env:{DDiskHA.DATABASE_ENV}\n"
        f"LoadCredential=web-interface.cfg:{web_configuration}\n"
        f"ExecStart={root}/bin/disk-ha-web --config ${{CREDENTIALS_DIRECTORY}}/web-interface.cfg\n"
        "Restart=on-failure\nRestartSec=2\n\n[Install]\nWantedBy=multi-user.target\n")
    service.chmod(0o644)
    systemctl("daemon-reload")
    systemctl("enable", service.name)
    with configuration.with_suffix(".lock").open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        if upgrading:
            installed = HealthSchedule.read()
            values = json.loads(configuration.read_text())
            values.update(enabled=installed["enabled"], expression=installed["expression"] or None)
            HealthSchedule.save_configuration(configuration, values)
        health = HealthConfiguration(configuration)
        HealthSchedule.apply(root, health)
    with sync_configuration.with_suffix(".lock").open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        if sync_upgrading:
            installed = SyncSchedule.read()
            values = json.loads(sync_configuration.read_text())
            values.update(enabled=installed["enabled"], expression=installed["expression"] or None)
            SyncSchedule.save_configuration(sync_configuration, values)
        sync = SyncConfiguration(sync_configuration)
        SyncSchedule.apply(root, sync)
    if health.enabled or sync.enabled:
        systemctl("enable", "--now", "cron.service")
    restart()
    print(f"Installed disk-ha {DDiskHA.VERSION} in {root}; configuration and data preserved.")


def uninstall() -> None:
    root = installation_root()
    configuration = root / "conf/health.json"
    if configuration.parent.exists():
        with configuration.with_suffix(".lock").open("a") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            HealthSchedule.apply(root, None)
        with (root / "conf/sync.lock").open("a") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            SyncSchedule.apply(root, None)
    service = Path(DDiskHA.WEB_SERVICE_FILE)
    health_service = Path(DDiskHA.HEALTH_SERVICE_FILE)
    email_service = Path(DDiskHA.EMAIL_REPORT_SERVICE_FILE)
    sync_service = Path(DDiskHA.SYNC_SERVICE_FILE)
    reload_required = any(unit.exists() for unit in (service, health_service, email_service, sync_service))
    for worker_service in (health_service, email_service, sync_service):
        if worker_service.exists():
            systemctl("stop", worker_service.name)
            worker_service.unlink()
    Path(DDiskHA.HEALTH_SUDOERS_FILE).unlink(missing_ok=True)
    if service.exists():
        systemctl("disable", "--now", service.name)
        service.unlink()
    if reload_required:
        systemctl("daemon-reload")
    (root / "bin/disk-ha-web").unlink(missing_ok=True)
    (root / "bin/disk-ha-check").unlink(missing_ok=True)
    (root / "bin/disk-ha-schedule").unlink(missing_ok=True)
    (root / "bin/disk-ha-sync").unlink(missing_ok=True)
    for name in ("diskha", "disk_ha"):
        package = root / name
        if package.exists():
            shutil.rmtree(package)
    print("Removed disk-ha's Web UI service, executable, Python package, and CMDB metadata; "
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
        print(f"disk-ha: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
