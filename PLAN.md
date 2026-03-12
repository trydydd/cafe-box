# CafeBox — Agent Build Plan

A self-contained offline community server running on a Raspberry Pi Zero 2 W.
Broadcasts a WiFi hotspot, intercepts captive portal detection, and serves
content through a clean landing page. Extensible by design: each service is
an independent systemd unit routed through a single nginx reverse proxy.

This project is a spiritual descendant of **PirateBox**:
- **Strictly offline** (no WAN dependencies, no routing to the Internet)
- **Hotspot-only** access (all user traffic arrives via the AP)
- **Assume hostile clients** (treat every connected device as untrusted)
- **Anonymous-by-default for users**, but **hardened-by-default for the box**
- Content is **curated by the operator** (admin uploads), not an anonymous public dropbox

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
│   ├── build.sh                # Builds a flashable .img.xz using pi-gen-action locally
│   ├── first-boot.sh           # Runs once on first boot: generates password, sets flag
│   ├── first-boot.service      # systemd oneshot unit that calls first-boot.sh
│   └── README.md               # Instructions for building and flashing the image
├── .github/
│   └── workflows/
│       └── build-image.yml     # GitHub Action: builds and publishes image on tag
├── system/
│   ├── templates/              # Jinja2 templates — never edit these directly
│   │   ├── hostapd.conf.j2
│   │   ├── dnsmasq.conf.j2
│   │   ├── nginx-portal.conf.j2
│   │   ├── nginx-admin.conf.j2
│   │   ├── nginx-chat.conf.j2
│   │   ├── nginx-books.conf.j2
│   │   ├── nginx-learn.conf.j2
│   │   └── nginx-music.conf.j2
│   └── generated/              # Auto-generated — never edit directly
│       ├── hostapd.conf
│       ├── dnsmasq.conf
│       └── nginx/
│           └── sites/
├── storage/
│   └── setup-symlinks.py       # Creates /mnt/cafebox/ symlink tree
├── services/
│   ├── conduit/
│   │   ├── install.sh
│   │   ├── conduit.service
│   │   └── homeserver.yaml.j2
│   ├── element-web/
│   │   ├── install.sh
│   │   └── config.json.j2
│   ├── calibre-web/
│   │   ├── install.sh
│   │   └── calibre-web.service
│   ├── kiwix/
│   │   ├── install.sh
│   │   └── kiwix.service
│   └── navidrome/
│       ├── install.sh
│       ├── navidrome.toml.j2
│       └── navidrome.service
├── admin/
│   ├── backend/
│   │   ├── main.py
│   │   ├── requirements.txt
│   │   ├── service_manager.py  # Thin systemctl wrapper — no dev/prod split
│   │   ├── routers/
│   │   │   ├── auth.py
│   │   │   ├── services.py
│   │   │   ├── storage.py
│   │   │   ├── network.py
│   │   │   ├── content.py
│   │   │   ├── logs.py
│   │   │   └── public.py
│   │   └── admin.service
│   └── frontend/
│       ├── index.html
│       └── assets/
└── portal/
    └── index.html
```

---

## Central Configuration

**`cafe.yaml`** — The only file an operator ever needs to edit.

All system-level configs (`hostapd.conf`, `dnsmasq.conf`, nginx `server {}`
blocks, `homeserver.yaml`, `navidrome.toml`, `config.json`) are
**auto-generated** from this file by `scripts/generate-configs.py` using
Jinja2 templates. Operators should never need to touch the generated files.

```yaml
# ─────────────────────────────────────────────
#  CafeBox Configuration
#  Edit this file, then run: sudo ./install.sh
# ─────────────────────────────────────────────

box:
  name: "CafeBox"          # Shown on the landing page
  domain: "cafe.box"       # Local domain — change only if you know what you're doing

network:
  ssid: "CafeBox"          # WiFi network name broadcasted to users
  password: ""             # Leave empty for an open (no password) network
  channel: 6               # WiFi channel (1, 6, or 11 recommended)
  interface: "wlan0"       # WiFi interface name (wlan0 on Pi Zero 2 W)
  ip: "192.168.42.1"       # Pi's IP address on the hotspot network
  dhcp_range:
    start: "192.168.42.10"
    end: "192.168.42.200"
    lease: "24h"

admin:
  username: "admin"
  password: "changeme"     # Used only for builder installs; images use first-boot generation
  session_hours: 8         # How long login sessions last

storage:
  onboard_root: "/mnt/cafebox-onboard"
  usb_root: "/mnt/cafebox-usb"
  symlink_root: "/mnt/cafebox"
  # Per-service storage location. Options: "onboard" or "usb"
  locations:
    matrix:    onboard
    books:     onboard
    kiwix:     onboard
    music:     onboard
    navidrome: onboard

services:
  chat:
    enabled: true
    display_name: "Chat"
    icon: "💬"
    port: 6167
    # Matrix room created on first run
    default_room_name: "CafeBox General"
    default_room_topic: "Welcome to CafeBox — anonymous local chat"
    guest_access: true

  books:
    enabled: false
    display_name: "Library"
    icon: "📚"
    port: 8083
    public_access: true    # Allow browsing without login

  learn:
    enabled: false
    display_name: "Learn"
    icon: "🎓"
    port: 8888
    # List of ZIM files to serve (filenames only, placed in storage/kiwix/)
    zim_files: []

  music:
    enabled: false
    display_name: "Music"
    icon: "🎵"
    port: 4533
    public_access: true
    downsample_format: "opus"
```

### Service Identity Map (Naming Consistency)

CafeBox deals with three different “names” for the same conceptual service:

- **Tile id**: what the portal shows and what `/api/public/services/status` returns.
- **systemd unit**: what `systemctl` controls.
- **storage key**: what `storage.locations.*` uses.

This map must remain consistent across the installer, admin backend, and templates.

| Tile id | Display | systemd unit(s) | Storage key | Notes |
|---|---|---|---|---|
| `chat`  | Chat | `conduit.service` (and optionally `cafebox-element-web.service` if ever needed) | `matrix` | Element Web is static files served by nginx; Conduit stores data in `matrix`. |
| `books` | Library | `calibre-web.service` | `books` | Admin uploads books; public browsing allowed when enabled. |
| `learn` | Learn | `kiwix.service` | `kiwix` | Admin manages ZIM files; public browsing allowed when enabled. |
| `music` | Music | `navidrome.service` | `music` + `navidrome` | Music files in `music`, Navidrome state in `navidrome`. |

Implementation note:
- Public and portal surfaces speak in **tile ids**.
- Internals map tile ids → unit/storage keys (do not treat user-provided ids as unit names directly).

### Config Rendering Pipeline

**`scripts/generate-configs.py`**

Reads `cafe.yaml` and renders all Jinja2 templates into their target
locations under `system/generated/`. Called by:
- `install.sh` on first install
- `install.sh` on re-run (idempotent update)
- The admin backend's `/api/network` router after network changes
- The admin backend's `/api/services` router after enabling/disabling services

```python
import yaml
from jinja2 import Environment, FileSystemLoader
from pathlib import Path

def load_config(path="cafe.yaml"):
    with open(path) as f:
        return yaml.safe_load(f)

def render_all(config):
    env = Environment(loader=FileSystemLoader("system/templates"))
    targets = {
        "hostapd.conf.j2":        "system/generated/hostapd.conf",
        "dnsmasq.conf.j2":        "system/generated/dnsmasq.conf",
        "nginx-portal.conf.j2":   "system/generated/nginx/sites/portal.conf",
        "nginx-admin.conf.j2":    "system/generated/nginx/sites/admin.conf",
        "nginx-chat.conf.j2":     "system/generated/nginx/sites/chat.conf",
        "nginx-books.conf.j2":    "system/generated/nginx/sites/books.conf",
        "nginx-learn.conf.j2":    "system/generated/nginx/sites/learn.conf",
        "nginx-music.conf.j2":    "system/generated/nginx/sites/music.conf",
    }
    for template_name, output_path in targets.items():
        tmpl = env.get_template(template_name)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(tmpl.render(**config))
```

Service-specific configs (Conduit `homeserver.yaml`, Navidrome
`navidrome.toml`, Element Web `config.json`) are rendered into their
respective install directories by each service's `install.sh`, which also
calls `generate-configs.py` for its own template.

### Admin UI Config Editing

The admin backend reads `cafe.yaml` on startup (via `scripts/config.py`) and
exposes it through the API. The Network and Services sections of the admin UI
write changes back to `cafe.yaml` and re-run `generate-configs.py`,
then reload affected services. Operators can also edit `cafe.yaml` directly
in a text editor and re-run `install.sh`.

**`scripts/config.py`** — shared config loader used by both `install.sh`
(via subprocess) and the admin backend (imported directly):

```python
import yaml
from pathlib import Path

CONFIG_PATH = Path("/opt/cafebox/cafe.yaml")

def load() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text())

def save(config: dict):
    CONFIG_PATH.write_text(
        yaml.dump(config, default_flow_style=False, allow_unicode=True)
    )
```

---

## Stage 0 — Base Infrastructure

**Goal:** Pi broadcasts a WiFi network. Any device that connects sees `cafe.box`
resolve to the Pi. OS captive portal detection is intercepted and redirects to
the landing page. No content services required yet.

### 0.0 — Threat Model & Network Policy (Offline / Hostile Clients / Hotspot Only)

CafeBox assumes every connected client device is untrusted.

Policy goals:
- **Strictly offline:** no WAN dependencies; no routing/NAT for clients.
- **Hotspot-only:** all user access is via the AP interface (`network.interface`, typically `wlan0`).
- **Protect users from one another:** where possible, prevent client-to-client connectivity.
- **Protect the box:** only required ports are exposed; services bind to localhost where possible.
- **Admin is reachable from the hotspot** at `admin.<domain>`, but is **not linked** from the public portal.

Practical controls:
- **AP isolation** enabled via hostapd (client-to-client blocked at L2).
- **Default-deny firewall**:
  - allow DHCP/DNS/HTTP on the hotspot interface
  - deny everything else inbound
  - deny all forwarding

This is intentionally “simple but effective”, not a full enterprise security posture.

### 0.1 — OS Preparation

- Start from Raspberry Pi OS Lite (64-bit, no desktop)
- Enable SSH for builder installs; image installs may disable SSH by default
- Set hostname to `cafebox`
- Disable default `wpa_supplicant` on `wlan0` (it will be managed by `hostapd`)
- Install base packages:
  ```
  nginx hostapd dnsmasq python3-pip python3-venv git curl
  ```
- Set static IP on `wlan0`: `192.168.42.1/24`
- Disable `dhcpcd` management of `wlan0`

### 0.2 — hostapd

**`system/templates/hostapd.conf.j2`** — Jinja2 template, rendered into
`system/generated/hostapd.conf` by `generate-configs.py`.

```ini
interface={{ network.interface }}
driver=nl80211
ssid={{ network.ssid }}
hw_mode=g
channel={{ network.channel }}
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0

# Protect clients from each other (PirateBox-style)
ap_isolate=1

{% if network.password %}
wpa=2
wpa_passphrase={{ network.password }}
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
{% endif %}
```

- If `network.password` is empty in `cafe.yaml`, the `wpa_*` block is omitted (open network)
- Enable and start `hostapd.service`

### 0.4 — nginx Base Config

**Captive portal interception** — the portal template uses `box.domain`:

```nginx
# Android / Chrome
location /generate_204 { return 302 http://{{ box.domain }}/; }
```

### 0.4a — Firewall (Recommended Baseline)

Implement a simple default-deny firewall (nftables or ufw).

### 0.6 — Landing Portal

The portal uses `GET /api/public/services/status` and must not link to admin.

### 0.8 — First-Boot Credential Generation

CafeBox displays the first-boot admin password on the landing page until it is changed.

---

## Stage 1 — Admin UI

### CSRF Defense

Require a CSRF token header on state-changing requests.

### Sudo Grants

Use a dedicated cafebox-admin user and tighten sudoers.

---

## Stage 2 — Matrix Chat (Conduit + Element Web)

### 2.0 — Reality Check: E2EE vs Ephemerality

CafeBox does not promise messages are erased when users disconnect.
