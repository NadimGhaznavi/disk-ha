# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.3.0] - 2026-10-16 @ 23:10

This release celebrates the Cree languae. This is the **niyānanosāp** (15) release.

### Added

- A web page on setting up msmtp and Gmail.

## [2.2.4] - 2026-10-16 @ 21:09

This release celebrates the Cree language. This is the **nīsosāp** (12) release.

- Updated README.md that points at the website.

## [2.2.3] - 2026-10-15 @ 05:24

This release celebrates the Cree language. This is the **pēyakosāp** (11) release.

### Added

- Architecture diagram.
- Additions website content.

## [2.2.2] - 2026-10-15 @ 04:53

This release celebrates the Cree language. This is the **mitātaht** (10) release.

### Added

- Add website TOC, dividers.

### Changed

- Widen documentation pages using the theme's built-in wide layout.

## [2.2.1] - 2026-10-15 @ 04:20

This release celebrates the Cree language. This is the **kēkā-mitātaht** (9) release.

### Changed

- Move **Run Now** below the results in the Disk Health section.
- Additional website content.

## [2.2.0] - 2026-10-15 @ 03:49

This release celebrates the Cree language. This is the **ayēnānēw** (8) release.

### Added

- A **Most recent health check output** link opens the latest saved check,
  including both disks' raw SMART output and any email delivery failure.

### Changed

- Rename the email report button to **Email Health Check**.

- Configure the web interface host, port, and request timeout in
  `/opt/prod/diskha/conf/web-interface.cfg`; changes apply after restarting
  `disk-ha-web.service`. Invalid settings produce a clear startup error, and
  installation upgrades preserve the configuration file.

## [2.1.1] - 2026-10-14 @ 04:10

This release celebrates the Cree language: This is the **tēpakohp** (7) release.

### Fixed

- Rebuilt `_config.yml`.

## [2.1.0] - 2026-10-14 @ 03:53

This release celebrates the Cree language: This is the **nikotwāsik** (6) release.

### Fixed

- Website failed to resolve, typo in `_config.yml`.

## [2.0.0] - 2026-10-11 @ 06:16

This release remembers **Pikaia** who last walked Earth over 505 million years ago.

### Added

- GUI source and target directory selection with automatic filesystem and drive
  detection, validation of two distinct local drives, and SMART monitoring of
  the selected drives.

### Changed

- Mirror selected subdirectories with different names and recheck their saved
  mount, UUID, and drive identities before each sync.
- Display configured directories and backing filesystem capacity, usage, and
  free space instead of fixed mount paths.
- Logo background is now transparent.

## [1.4.0] - 2026-10-11 @ 05:53

This release remembers the **Opabinia** who went extinct about 505 million years ago.

### Added

- DiskHA logo in the top-left title bar on the main Web UI and sync-output page.

## [1.3.2] - 2026-10-11 @ 05:44

This release is named for the **Nuralagus** who died out about 3 million years ago.

- Added a [DiskHA Logo](/pages/images/diskha.png).

## [1.3.1] - 2026-10-11 @ 04:23

The **Kioea** release is in memory of the species which became extinct in 1859.

### Fixed

- Restore the legacy home alias on reinstall when the `diskha` account remains
  but its installation directories have been removed.
- Report the exact incompatible service-account settings when installation
  encounters an existing `diskha` account.

## [1.3.0] - 2026-10-11 @ 04:03

This release is in memory of the **Juratyrant** who walked on Earth 149 million years ago.

### Changed

- Make installed applications discoverable as `DiskHA` in CMDB using the
  `diskha` package under `/opt/prod/diskha`. Upgrades retain existing
  configuration, credentials, data, and worker locks through an alias to the
  former installation directory.

## [1.2.0] - 2026-10-10 @ 20:43

This release is to remember the **Glyptodon** who died out about 10,000 years ago. They lasted about 3.2 million years, well above the average run for a species.

### Added

- Formatted HTML SMART emails with a table of contents, health summary, disk identity and attribute tables, full diagnostics, and a plain-text alternative.

### Fixed

- Parse standard and brief SMART attribute tables correctly, and keep optional extended diagnostic failures separate from the disk health verdict.
- Report missing msmtp configuration explicitly instead of a generic mail exit status.

## [1.1.0] - 2026-10-10 @ 20:14

This release is in memory of the **Falkland Fox** who were wiped out by 1876.

### Added

- Sync Now button beside the Data Sync Schedule Update button for guarded background mirroring.

## [1.0.0] - 2026-10-10 @ 20:06

This release is in memory of the **Elephant Bird** which died around 1000 CE.

### Added

- Data Sync Schedule with editable cron controls, an every-four-hours default,
  guarded Disk 1 to Disk 2 mirroring with deletion propagation, and a separate
  page for the most recent verbose rsync output.

- Role column in Drive Configuration identifying Disk 1 as Source and Disk 2 as Target.

## [0.5.0] - 2026-10-10 @ 19:45

This release is in memory of the last **Dodo** who died in 1681.

### Added

- Email Notification section showing the configured contact and an Email disk report
  button for fresh, verbose SMART results from both disks.

### Changed

- Moved cron controls into a separate Health Check Schedule section.
- Renamed the constants module and class to `DDiskHA` and updated release tooling.

## [0.4.2] - 2026-10-10 @ 19:00

In memory of the **Cave Bear**, the last of which died out around 24,000 years ago.

### Changed

- Last health-check times are recorded and displayed in server local time with
  second precision.
- Disk Health scheduling follows CMDB's Enabled, Cron Schedule, and Update controls,
  populated from the live cron entry and retained across upgrades.

## [0.4.1] - 2026-10-10 @ 18:45

In memory of the **Barbary Lions**, who died out in the 20th century.

### Added

- Disk Health panel shows the configured cron schedule and a Run Now button
  to request a background health check.

## [0.4.0] - 2026-10-10 @ 18:02

In memory of the **Aurochs** that went extinct in 1627.

### Added

- Configurable cron health checks with atomic flat-file results, a Web UI health
  panel, and preservation of settings and results across upgrades and removal.
- Disk health entities, SMART and email interfaces, and a check activity modeling
  the existing script, with bounded commands and explicit unavailable-result
  and notification-failure reporting.

## [0.3.4] - 2026-10-10 @ 17:21

The **Zofia** release is dedicated to [Zofia Szmydt](https://en.wikipedia.org/wiki/Zofia_Szmydt).

### Added

- Drive Configuration table showing capacity and used space in TB for Disk 1
  and Disk 2, with explicit states for unmounted or unreadable drives.

## [0.3.2] - 2026-10-10 @ 17:03

### Added

The **Yvonne** release is dedicated to [Yvonne Choquet-Bruhat](https://en.wikipedia.org/wiki/Yvonne_Choquet-Bruhat).

- Dark teal web interface title bar with the caption “Vigilent since October 2026”.

## [0.3.0] - 2026-10-08 @ 18:03

### Changed

- Rebrand the project, Python package, service, installation paths, and accounts
  to disk-ha, with documentation at `https://diskha.osoylace.com`.
- Added Jekyll theme for GitHub Pages.

## [0.2.0] - 2026-10-08 @ 05:13

### Added

- Blank web interface on port `23300`, with a bundled server and systemd service
  managed by installation, upgrade, restart, and uninstall scripts.
- Dedicated `diskha` Linux service account and local MariaDB account and database,
  with protected credentials preserved across upgrades and removal.

## [0.1.0] - 2026-10-08 @ 04:48

### Added

- Project development guidance for disk monitoring, safe mirroring, installation,
  verification, and releases.
- Installation, upgrade, and uninstall scripts targeting `/opt/prod/disk-ha`,
  preserving configuration and saved data.
- Python constants for version and CMDB discovery metadata.
- Release script to update version, codename, and changelog, publish through
  `dev` and `main`, and create the next feature branch.
