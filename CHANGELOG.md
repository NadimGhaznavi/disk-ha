# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Project development guidance for disk monitoring, safe mirroring, installation,
  verification, and releases.
- Installation, upgrade, and uninstall scripts targeting `/opt/prod/nfs-ha`,
  preserving configuration and saved data.
- Python constants for version and CMDB discovery metadata.
- Release script to update version, codename, and changelog, publish through
  `dev` and `main`, and create the next feature branch.
