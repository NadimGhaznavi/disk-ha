---
title: Data synchronization
author_profile: true
layout: single
---

[Documentation index]({{ site.baseurl }}{% link index.md %})

Data Sync Schedule mirrors the contents of the selected source directory into
the selected target directory. Deletions in the source propagate to the target.
Use **Check directories** and **Save directories** in Drive Configuration to select
existing directories on two distinct local drives. Directory names may differ.
Installation initially uses `/exports/disk1/` and `/exports/disk2/`.
The initial cron schedule is `0 */4 * * *`: every four hours at the top of the
hour, in server local time. Edit **Enabled** and **Cron Schedule**, then click
**Update**. The form reads the actual root cron entry; disabling removes it.
**Sync Now**, beside **Update**, requests a background run using the saved settings.
Enable and update the schedule first if synchronization is disabled. Manual runs
use the same mount checks, lock, timeout, and output as cron. Health alerts do not
disable synchronization.

## Configuration and safeguards

Installation creates `/opt/prod/diskha/conf/sync.json`, owned by root with mode
`0600`. GUI selection records each directory's `path`, backing `mount`, filesystem
`uuid`, and stable whole-drive `disk` identity in this file. SMART monitoring uses
these same drive identities. Existing mount-only configurations remain usable
until a selection is saved through the GUI.
The finite `timeout` bounds a complete rsync run in seconds; the
initial value is 86400 (24 hours). Adjust this timeout in the installed file.
Upgrades preserve settings and the live cron schedule.

GUI detection supports directly mounted ext2, ext3, ext4, and XFS filesystems on
individual local disks or their partitions, with stable `/dev/disk/by-id/` identities
and available SMART monitoring. Different partitions of the same physical drive
are rejected. Network filesystems, RAID/LVM or other layered devices, loop devices,
the root filesystem, symbolic-link paths, subdirectory bind mounts, and selected
trees containing other mounts are rejected. Directories must already exist;
the app does not create directories or mount drives. The target must be writable.

Before each sync, the worker rechecks the selected directories, their exact backing
mounts, UUIDs, and saved drive identities. Missing, changed, reversed, identical,
or nested paths prevent rsync from starting. Rsync stays on the selected filesystem.
A shared worker lock prevents overlapping syncs. Saving a selection is blocked
during either a health check or sync; failed checks leave settings unchanged.
Schedule edits during a worker run fail clearly; retry after it finishes.
Health checks continue to inspect the saved drives even when a mount is missing.

Cron invokes the root-owned `disk-ha-sync` worker, which runs:

```sh
rsync -avr --one-file-system --delete -- /disk1/archive/incoming/movies/ /disk2/inbox/media-center/
```

The trailing slashes mirror contents directly into the target directory. Space
readings show the entire backing filesystem; they do not guarantee that the
selected source contents will fit in the target's free space. Both scheduled jobs
have separate markers in root's crontab, and updates preserve unrelated jobs.
The worker does not require the web service to run.

## Output and failures

**Most recent sync output** opens `/sync/output`. It shows the latest rsync
transcript, start and finish timestamps, and an explicit success or failure.
Partial failures and timeouts are recorded as failed; timeout handling terminates
the rsync process group before releasing the sync lock.

Completed attempts atomically replace `data/sync-output.log`, owned by root with
mode `0640` and the `diskha` group. While a sync runs, the page continues to show
the previous transcript. A disabled, overlapping, or mount-rejected run preserves
that transcript. The output page displays filenames as text and streams large logs.

Cron appends skipped-run reasons, completion messages, and command failures to
`data/sync.log`. A failed sync exits with status 1; inspect this log if no new
transcript appears. Upgrade and removal preserve configuration and saved logs.
Uninstall removes disk-ha's sync cron entry, manual sync service, and executable.
