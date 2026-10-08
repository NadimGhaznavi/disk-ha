---
title: Web interface
author_profile: true
layout: single
---

[Documentation index]({{ site.baseurl }}{% link index.md %})

The web interface currently serves a blank page at `http://<server>:23300/`.
It listens on all IPv4 interfaces and requires no third-party Python packages.

## Install and manage

On a Linux host with Python 3.10 or newer and systemd, run from the checkout:

```sh
sudo scripts/install.sh
sudo scripts/upgrade.sh
sudo scripts/restart.sh
```

Installation bundles the server and its page into `/opt/prod/nfs-ha/bin/nfs-ha-web`,
deploys the Python package and readable CMDB metadata, and enables
`nfs-ha-web.service` at boot. The service runs under a systemd dynamic user;
serving this page requires no root privileges or disk access.

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
