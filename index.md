---
title: Scheduled Disk Replication with Gmail Alerts
---

## Overview

This project is a basic disk replication application. It includes a web interface to:

- Choosesource and target directories.
- Set a SMART health check (cron) schedule.
- Set a (rsync) data synchronization (cron) schedule.
- Execute a manual health check.
- Email a disk report to a Gmail account.

**IMPORTANT NOTE**: The `rsync` operation includes the `--delete` flag, which means that delete operations on the source are propaged to the target.

## Download & Install

You can download the latest release tarball from [GitHub](https://github.com/NadimGhaznavi/disk-ha) or you can clone the repo with `git`:

```sh
sudo git clone https://github.com/NadimGhaznavi/disk-ha
cd disk-ha
sudo ./scripts/install.sh
```

The **DiskHA** software installs into `/opt/prod/diskha`.

## Configuring the Web Interface

The installation includes a `/opt/prod/diskha/conf/web-interface.cfg` file that lets you configure:

- The network interface to bind to (e.g. `0.0.0.0.` is all, `127.0.0.1` is only localhost).
- The port number that the web service listens on.
- The HTTP request timeout in seconds.

```sh
[web]
host = 0.0.0.0
port = 23300
request_timeout = 15
```

## Disk layout

| Role | Mount point | Filesystem UUID | Existing sync path |
| --- | --- | --- | --- |
| Primary | `/exports/disk1` | `824971c7-d263-4b6a-a562-3452c3482ece` | `/exports/old` |
| Recovery copy | `/exports/disk2` | `b14c1ec0-df91-4f3d-a990-b0c820b81a9c` | `/exports/new` |

Both filesystems are ext4 and are mounted by UUID through `/etc/fstab`.
Synchronization runs from the primary to the recovery copy.

## Agreed scope and behavior

- Check both disks regularly for failure or degradation and notify the operator
  when a problem is detected.
- Synchronize the recovery disk on a schedule.
- Select source and target directories, including differently named
  subdirectories, on two distinct local drives. Detect their backing mounts,
  filesystem UUIDs, and stable drive identities for mirroring and monitoring.
- Continue scheduled synchronization when a disk health check raises an alert.
- Verify that both expected disks are mounted before synchronization. A missing
  or incorrect mount must prevent that sync run, especially because rsync uses
  `--delete`.
- Make configuration, scheduling, installation, and verification clear enough
  to restore reliably after a server rebuild.

The recovery disk is a mirror: deletions on the primary propagate to it. It does
not retain earlier versions. Monitoring and mirroring reduce the risk of data
loss but cannot guarantee protection against two sudden disk failures.

## Manual response and boundaries

Disk replacement and recovery are manual. On receiving a disk failure alert,
the operator will power down the server, disconnect the drives, obtain one or
two replacements as needed, reconnect the appropriate drives, and synchronize
the replacement storage.

NFS configuration, NFS failover, and automatic recovery are outside this
project's scope.

The [web interface]({{ site.baseurl }}{% link pages/web-interface.md %}) currently
displays a title bar and Drive Configuration controls for source and target
directories on port `23300`, with filesystem capacity, usage, and free space in TB.
[Disk health]({{ site.baseurl }}{% link pages/disk-health.md %}) runs through a
configured cron job and saves results in a flat JSON file displayed by the Web UI.
Health Check Schedule reads and edits the installed cron schedule. The Disk Health
panel provides **Run Now** for a background health check.
Email Notification shows the configured contact and provides **Email disk report**
for a fresh, verbose SMART report of both disks.
The initial schedule checks daily at 14:00 server time and retains the existing
script's email settings. Installed settings are preserved on upgrade.
[Data synchronization]({{ site.baseurl }}{% link pages/data-sync.md %}) mirrors
the selected source directory to the target every four hours by default. Data Sync Schedule reads and edits
its cron entry and links to the most recent verbose output.

## Development

[Coding guidelines]({{ site.baseurl }}{% link pages/coding-guidelines.md %})
