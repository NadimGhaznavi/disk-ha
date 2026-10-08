# nfs-ha
Low-Tech disk mirroring application.

Project scaffolding requires Python 3.10 or newer. From a checkout, run:

```sh
sudo scripts/install.sh
sudo scripts/upgrade.sh
sudo scripts/uninstall.sh
```

Installation deploys the Python package and readable CMDB metadata to
`/opt/prod/nfs-ha`. Upgrade and uninstall preserve `conf/` and `data/`.
Runtime commands and scheduling will be added with the application.

Create a release from a clean, committed feature branch with local `dev` and
`main` up to date and an `origin` remote:

```sh
scripts/new-release.sh 0.1.0 "Release codename"
```

After confirmation, this updates the version, CMDB codename, and changelog,
merges through `dev` and `main`, and pushes both branches and the release tag.
Use `scripts/new-release.sh --help` for the next feature branch option.
