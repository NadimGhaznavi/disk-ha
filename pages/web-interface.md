---
title: Web interface
author_profile: true
layout: single
---

[Documentation index]({{ site.baseurl }}{% link index.md %})

The web interface currently serves a blank page at `http://<server>:23300/`.
It listens on all IPv4 interfaces and requires no third-party Python packages.

## Install and manage

On a Linux host with Python 3.10 or newer, systemd with `LoadCredential` support,
and a running local MariaDB server with the `mariadb` client, run from the checkout.
Root must be able to connect to MariaDB through Unix socket authentication.

```sh
sudo scripts/install.sh
sudo scripts/upgrade.sh
sudo scripts/restart.sh
```

Installation bundles the server and its page into `/opt/prod/nfs-ha/bin/nfs-ha-web`,
deploys the Python package and readable CMDB metadata, and enables
`nfs-ha-web.service` at boot. The service runs under the persistent `nfsha` account;
serving this page requires no root privileges or disk access.

## Accounts and database

Installation creates the `nfsha` Linux system account and group with a non-login
shell and no separate home directory. Application code stays root-owned;
`/opt/prod/nfs-ha/data/` belongs to `nfsha` with mode `0700`.

Following the BMDynIP provisioning pattern, installation creates:

- MariaDB database `nfsha`, using `utf8mb4` with `utf8mb4_bin` collation.
- Local MariaDB account `'nfsha'@'localhost'` with a generated password.
- Root-owned credentials at `/opt/prod/nfs-ha/conf/database.env`, mode `0600`,
  inside the root-only `conf/` directory.

The database account receives `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `CREATE`,
`ALTER`, `INDEX`, and `REFERENCES` privileges on `nfsha` only. The database
currently has no application tables.

Systemd supplies a private copy of `database.env` to the service through
`LoadCredential`; the service can read it under `$CREDENTIALS_DIRECTORY`.
The blank page does not query the database yet.

Upgrade validates and retains saved credentials. If the credential file is
missing, installation generates a new password for the local application
database account while preserving the database. Uninstall preserves both
accounts, the Linux group, the database, credentials, and saved data.

## Service checks

Check readiness and logs:

```sh
curl --fail http://127.0.0.1:23300/ready
systemctl status nfs-ha-web.service
journalctl -u nfs-ha-web.service
```

Remove the service and application with `sudo scripts/uninstall.sh`.
Upgrade and removal preserve configuration, credentials, and saved data in
`/opt/prod/nfs-ha/conf/` and `/opt/prod/nfs-ha/data/`.

## Run from a checkout

```sh
python3 -m nfs_ha.server
```

Use `--host 127.0.0.1` to listen locally or `--port <port>` to override the port.
Stop the foreground server with Ctrl+C.
