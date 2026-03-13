# CafeBox

A self-contained offline community server running on a **Raspberry Pi Zero 2 W**.
CafeBox broadcasts a WiFi hotspot, intercepts captive portal detection, and serves
content through a clean landing page. Each service is an independent systemd unit
routed through a single nginx reverse proxy.

CafeBox is a spiritual descendant of **PirateBox**:

- **Offline during operation** — no WAN required; no runtime downloads.
- **Builder can download during build** — CI/local build may fetch upstream releases.
- **Hotspot-only access** — all user traffic arrives via the AP interface.
- **Assume hostile clients** — every connected device is treated as untrusted.
- **Anonymous-by-default for users**, but **hardened-by-default for the box**.
- Content is **curated by the operator** (admin uploads), not an anonymous public dropbox.
- **Prebuilt image** — flash SD card → power on → works.

---

## Quick Start

### 1 — Edit `cafe.yaml`

`cafe.yaml` is the **only file an operator ever needs to edit**. Set the box name,
domain, WiFi credentials, and toggle which services you want.

### 2 — Generate system configs

```bash
make generate-configs
```

This renders all Jinja2 templates in `system/templates/` into `system/generated/`
using the values from `cafe.yaml`.

### 3 — Bootstrap the VM or Pi

```bash
make vm-start      # start the dev VM
make install       # run install.sh inside the VM (or directly on a Pi)
```

### 4 — (Optional) Build a flashable image

```bash
bash image/build.sh
```

See [`image/README.md`](image/README.md) for build prerequisites and flashing instructions.

---

## Repository Structure

```
cafebox/
├── README.md
├── cafe.yaml                   # *** Single user-facing config file ***
├── install.sh                  # Bootstrap script (run on VM or Pi — identical)
├── Makefile                    # Dev shortcuts: vm-start, vm-ssh, install, logs...
├── scripts/
│   ├── vm.sh                   # VM lifecycle: start, stop, ssh, mount-share, status
│   ├── dev-hosts.sh            # Adds *.cafe.box to /etc/hosts
│   ├── config.py               # Loads cafe.yaml, used by install.sh + admin backend
│   └── generate-configs.py     # Renders all Jinja2 templates from cafe.yaml
├── image/
│   ├── build.sh                # Builds a flashable .img.xz
│   ├── first-boot.sh           # Runs once on first boot: generates password, sets flag
│   ├── first-boot.service      # systemd oneshot unit that calls first-boot.sh
│   └── README.md               # Instructions for building and flashing the image
├── .github/
│   └── workflows/
│       └── build-image.yml     # GitHub Action: builds and publishes image on tag
├── system/
│   ├── templates/              # Jinja2 templates — never edit these directly
│   └── generated/              # Auto-generated — never edit directly
├── storage/
│   └── setup-symlinks.py       # Creates /srv/cafebox/* symlinks from cafe.yaml
├── services/
│   ├── conduit/                # Matrix homeserver
│   ├── element-web/            # Matrix web client
│   ├── calibre-web/            # eBook library
│   ├── kiwix/                  # Offline Wikipedia / ZIM reader
│   └── navidrome/              # Music streaming server
├── admin/
│   ├── backend/                # Admin API (FastAPI)
│   └── frontend/               # Admin web UI
└── portal/
    └── index.html              # Landing page served to hotspot clients
```

---

## Configuration Reference

`cafe.yaml` contains four top-level sections:

| Section | Purpose |
|---------|---------|
| `box` | Identity: `name`, `domain`, `ip` |
| `wifi` | Hotspot: SSID, passphrase, interface, channel, DHCP range |
| `storage` | Base path and per-service data directories |
| `services` | Per-service `enabled` flags |

All system-level configs (nginx, hostapd, dnsmasq, nftables) are **auto-generated**
from `cafe.yaml` by `scripts/generate-configs.py`. Never edit files in
`system/generated/` by hand.

---

## Services

| Service | Description | Port |
|---------|-------------|------|
| [Conduit](https://conduit.rs) | Matrix homeserver | 6167 |
| [Element Web](https://element.io) | Matrix web client | 8080 |
| [Calibre-Web](https://github.com/janeczku/calibre-web) | eBook library | 8083 |
| [Kiwix](https://kiwix.org) | Offline Wikipedia / ZIM reader | 8888 |
| [Navidrome](https://navidrome.org) | Music streaming server | 4533 |

All services are reverse-proxied through nginx on port 80 and reachable at
`http://<box.domain>/<service-path>/`.

---

## Developer Workflow

```bash
make help              # List all available targets

make vm-start          # Start the QEMU/libvirt dev VM
make vm-stop           # Stop the dev VM
make vm-ssh            # SSH into the dev VM

make generate-configs  # Render system/templates/ → system/generated/
make install           # Run install.sh (inside VM or on a Pi)
make logs              # Tail journald logs for all cafebox-* services
```

### Local DNS

To resolve `*.cafe.box` from your development machine:

```bash
sudo bash scripts/dev-hosts.sh add     # add entries to /etc/hosts
sudo bash scripts/dev-hosts.sh remove  # remove them
```

---

## Network & Security Model

- **No WAN routing/NAT** for clients — the box is not an internet gateway.
- **Default-deny firewall** (nftables) — only DHCP (UDP 67/68), DNS (UDP/TCP 53),
  and HTTP (TCP 80) are allowed from the AP interface.
- **AP client isolation** enabled where supported by the hardware.
- Admin UI is reachable from the hotspot but is **not linked** from the portal.
- First-boot generates a random 12-character admin password displayed on the portal
  banner until the operator changes it.

---

## Build-time vs Runtime

| Phase | Responsibility |
|-------|---------------|
| **Build-time (CI/builder)** | Download upstream releases, package everything into the image |
| **Runtime (deployed box)** | No WAN needed. Render configs, manage services, handle uploads |

The resulting image is **fully self-contained** — no internet access is required
after flashing.

---

## Stages

| Stage | Description |
|-------|-------------|
| **Stage 0** | Base infrastructure: config system, templates, networking, image builder |
| **Stage 1** | Admin UI: FastAPI backend + web frontend, authentication |
| **Stage 2** | Matrix Chat: Conduit homeserver + Element Web client |

---

## License

This project is provided as-is for personal and community use.
