# disk-ha
Low-Tech disk mirroring application.

Documentation: [diskha.osoylace.com](https://diskha.osoylace.com).

Requires Python 3.10 or newer, systemd with credential support, and local MariaDB.
From a checkout, run:

```sh
sudo scripts/install.sh
sudo scripts/upgrade.sh
sudo scripts/restart.sh
sudo scripts/uninstall.sh
```

Installation deploys the application and readable CMDB metadata to
`/opt/prod/disk-ha` and starts `disk-ha-web.service`.
Open `http://<server>:23300/` for the blank web interface.
The service uses the `diskha` Linux account; installation also provisions the
`diskha` MariaDB account and database. Upgrade and uninstall preserve accounts,
the database, `conf/`, and `data/`.
See [web interface setup](pages/web-interface.md) for development and service commands.

Create a release from a clean, committed feature branch with local `dev` and
`main` up to date and an `origin` remote:

```sh
scripts/new-release.sh 0.1.0 "Release codename"
```

After confirmation, this updates the version, CMDB codename, and changelog,
merges through `dev` and `main`, and pushes both branches and the release tag.
Use `scripts/new-release.sh --help` for the next feature branch option.
