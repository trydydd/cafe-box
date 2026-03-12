# CafeBox — Agent Build Plan

A self-contained offline community server running on a Raspberry Pi Zero 2 W.
Broadcasts a WiFi hotspot, intercepts captive portal detection, and serves
content through a clean landing page. Extensible by design: each service is
an independent systemd unit routed through a single nginx reverse proxy.

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
│   │   │   └── logs.py
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
  password: "changeme"     # Change this before first use!
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
the landing page. No services running yet.

### 0.1 — OS Preparation

- Start from Raspberry Pi OS Lite (64-bit, no desktop)
- Enable SSH, set hostname to `cafebox`
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
{% if network.password %}
wpa=2
wpa_passphrase={{ network.password }}
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
{% endif %}
```

- If `network.password` is empty in `cafe.yaml`, the `wpa_*` block is omitted (open network)
- Enable and start `hostapd.service`

### 0.3 — dnsmasq

**`system/templates/dnsmasq.conf.j2`** — rendered into
`system/generated/dnsmasq.conf`.

```ini
interface={{ network.interface }}
bind-interfaces
dhcp-range={{ network.dhcp_range.start }},{{ network.dhcp_range.end }},255.255.255.0,{{ network.dhcp_range.lease }}
dhcp-option=3,{{ network.ip }}
dhcp-option=6,{{ network.ip }}

# Resolve the box domain and all subdomains to the Pi
address=/{{ box.domain }}/{{ network.ip }}
address=/.{{ box.domain }}/{{ network.ip }}

# Captive portal: resolve ALL DNS queries to the Pi
address=/#/{{ network.ip }}
```

- Disable `systemd-resolved` stub listener if present (port 53 conflict)
- Enable and start `dnsmasq.service`

### 0.4 — nginx Base Config

**`system/nginx/nginx.conf`** — minimal base, includes all
`system/generated/nginx/sites/*.conf`. This file is static (not templated).

All site configs are Jinja2 templates in `system/templates/` rendered into
`system/generated/nginx/sites/` by `generate-configs.py`.

**Captive portal interception** — the portal template uses `box.domain` and
`network.ip` from `cafe.yaml`:

```nginx
# system/templates/nginx-portal.conf.j2

server {
    listen 80 default_server;
    server_name _;

    # Android / Chrome
    location /generate_204 { return 204; }
    location /connectivitycheck.gstatic.com { return 302 http://{{ box.domain }}/; }

    # Apple
    location /hotspot-detect.html { return 302 http://{{ box.domain }}/; }
    location /library/test/success.html { return 302 http://{{ box.domain }}/; }

    # Windows
    location /ncsi.txt { return 200 "Microsoft NCSI"; }
    location /connecttest.txt { return 200 "Microsoft Connect Test"; }
    location /redirect { return 302 http://{{ box.domain }}/; }

    location / { return 302 http://{{ box.domain }}/; }
}

server {
    listen 80;
    server_name {{ box.domain }};
    root /opt/cafebox/portal;
    index index.html;
    location / { try_files $uri $uri/ /index.html; }
}
```

### 0.5 — Storage Symlink System

**`storage/setup-symlinks.py`**

Creates the symlink tree that all services reference. Reads storage locations
from `cafe.yaml` via `scripts/config.py`. Called by `install.sh` and by the
admin backend when toggling storage location per service.

```
/mnt/cafebox/matrix/   → /mnt/cafebox-onboard/matrix/   (default)
/mnt/cafebox/books/    → /mnt/cafebox-onboard/books/
/mnt/cafebox/kiwix/    → /mnt/cafebox-onboard/kiwix/
/mnt/cafebox/music/    → /mnt/cafebox-onboard/music/
/mnt/cafebox/navidrome → /mnt/cafebox-onboard/navidrome/
```

Logic:
1. Load `cafe.yaml` via `scripts/config.py`
2. Create all directories under `storage.onboard_root` and `storage.usb_root`
3. For each service, read target location from `storage.locations.{service}`
4. Create/update symlinks accordingly
5. If USB target is selected but drive is not mounted, fall back to onboard
   and log a warning

### 0.6 — Landing Portal

**`portal/index.html`** — Single HTML file, no build step, no JS framework.

The page queries the admin API (`/api/services/status`) and renders service
tiles. Unavailable services are shown as greyed-out.

Design requirements:
- Mobile-first, works at 375px width
- Large tap targets (service tiles min 80px tall)
- Shows: Box name, active services with icons and links, a footer with
  connection count if available
- No external CDN dependencies — all assets served locally

Service tile data (returned by `/api/public/services/status`, derived from
`cafe.yaml` `services` block combined with live systemd status):
```json
[
  { "id": "chat",  "name": "Chat",    "url": "http://chat.cafe.box",  "icon": "💬", "running": true  },
  { "id": "books", "name": "Library", "url": "http://books.cafe.box", "icon": "📚", "running": false },
  { "id": "learn", "name": "Learn",   "url": "http://learn.cafe.box", "icon": "🎓", "running": false },
  { "id": "music", "name": "Music",   "url": "http://music.cafe.box", "icon": "🎵", "running": false }
]
```
`display_name` and `icon` are read from `cafe.yaml` so operators can
customise them without touching code.

### 0.7 — Bootstrap Script

**`install.sh`** — Idempotent. Safe to re-run.

Steps:
1. Verify `cafe.yaml` exists (exit with helpful error if not)
2. Install system packages including `python3-yaml python3-jinja2`
3. Run `scripts/generate-configs.py` to render all system configs from `cafe.yaml`
4. Configure static IP on `wlan0` (IP read from `cafe.yaml` via `scripts/config.py`)
5. Symlink generated `hostapd.conf` and `dnsmasq.conf` into place
6. Symlink generated nginx site configs into `/etc/nginx/sites-enabled/`
7. Run `storage/setup-symlinks.py`
8. Copy portal to `/opt/cafebox/portal/`
9. Write initial admin credentials from `cafe.yaml` to `/etc/cafebox/admin-credentials`
10. Enable services: `hostapd`, `dnsmasq`, `nginx`
11. Print completion message with admin URL

### 0.8 — First-Boot Credential Generation

On a pre-built image, admin credentials must not be the same across every
flash. A `systemd` oneshot service generates a random password on first boot,
writes it to the credentials file, and marks itself done. It never runs again.

**`image/first-boot.sh`**

```bash
#!/usr/bin/env bash
# Runs exactly once on first boot of a freshly flashed CafeBox image.
# Generates a random admin password, stores it hashed, and signals the
# landing portal to display it until the operator changes it.

set -euo pipefail

FLAG="/etc/cafebox/.first-boot-complete"

# Guard — exit immediately if already run
[ -f "$FLAG" ] && exit 0

# Generate a human-friendly password: three groups of 3 chars, hyphen-separated
# Avoids ambiguous characters: 0, O, 1, l, I
CHARS="abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789"
generate_group() {
    cat /dev/urandom | tr -dc "$CHARS" | head -c 3
}
PASSWORD="$(generate_group)-$(generate_group)-$(generate_group)"

# Hash with bcrypt and write to credentials file
python3 - <<EOF
import bcrypt, json
from pathlib import Path

password = "$PASSWORD"
hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()
creds = {"username": "admin", "password_hash": hashed}
Path("/etc/cafebox/admin-credentials").write_text(json.dumps(creds))
Path("/etc/cafebox/admin-credentials").chmod(0o640)
EOF

# Write the plaintext password to a separate display file readable by the
# portal backend. Deleted permanently when operator changes their password.
echo "$PASSWORD" > /etc/cafebox/first-boot-password
chmod 640 /etc/cafebox/first-boot-password

# Mark complete
touch "$FLAG"
echo "==> CafeBox first-boot setup complete"
```

**`image/first-boot.service`**

```ini
[Unit]
Description=CafeBox First Boot Setup
After=network.target
ConditionPathExists=!/etc/cafebox/.first-boot-complete

[Service]
Type=oneshot
ExecStart=/opt/cafebox/image/first-boot.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
```

`ConditionPathExists=!...` means systemd won't even attempt to start this
unit if the flag file exists — a second layer of protection on top of the
bash guard.

**`install.sh` integration**

`install.sh` installs and enables `first-boot.service` only if
`/etc/cafebox/.first-boot-complete` does not already exist. On subsequent
`install.sh` runs (updates), the flag is already present and this block
is skipped entirely.

**Password display file lifecycle**

```
/etc/cafebox/first-boot-password   ← created by first-boot.sh
                                   ← read by portal backend (landing page banner)
                                   ← deleted by auth router on first password change
```

The portal backend checks for the file on each page load. If present, it
passes the password to the landing page template for display in the setup
banner. Once the operator changes their password via the admin UI, the auth
router deletes the file and the banner disappears permanently.

**Updated `/api/public/services/status` response**

Add a `first_boot` field so the landing portal knows whether to show the banner:

```json
{
  "first_boot": true,
  "first_boot_password": "xk9-mT4-rp2",
  "services": [...]
}
```

When `first_boot` is false, `first_boot_password` is omitted entirely.

**Landing page banner design**

```
┌─────────────────────────────────────────────┐
│  🔑 First time setup                         │
│                                             │
│  Your admin password is:                   │
│                                             │
│      xk9-mT4-rp2                           │
│                                             │
│  Visit admin.cafe.box to get started.       │
│  This message disappears once you have      │
│  changed your password.                     │
└─────────────────────────────────────────────┘
```

Banner design requirements:
- Shown at the top of the landing page, above service tiles
- Dismissed permanently (not just hidden) once password is changed
- Password displayed in a large, legible monospace font
- Avoid showing it if connecting from a device that has already visited
  admin.cafe.box (use a `localStorage` flag on the admin UI side to signal
  this — not security-critical, just a UX nicety)

**Stage 0 acceptance criteria:**
- [ ] Pi broadcasts WiFi SSID
- [ ] Connected device gets IP in `192.168.42.x`
- [ ] `cafe.box` resolves to `192.168.42.1`
- [ ] Captive portal popup appears on Android, iOS, and Windows
- [ ] Landing page loads at `http://cafe.box`
- [ ] All service tiles shown as unavailable (greyed out)
- [ ] On a freshly flashed image, landing page shows first-boot banner with password
- [ ] Banner disappears after admin password is changed via admin UI
- [ ] Re-running `install.sh` does not regenerate or overwrite the password

---

## Stage 1 — Admin UI

**Goal:** Operator can manage services, storage, and network settings from a
browser without SSH. Protected by a username/password login form with
server-side session tokens.

### 1.1 — Backend (FastAPI)

**`admin/backend/main.py`**

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from routers import services, storage, network, content, logs, auth

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, max_age=28800)  # 8h sessions
app.include_router(auth.router,     prefix="/api/auth")
app.include_router(services.router, prefix="/api/services", dependencies=[Depends(require_auth)])
app.include_router(storage.router,  prefix="/api/storage",  dependencies=[Depends(require_auth)])
app.include_router(network.router,  prefix="/api/network",  dependencies=[Depends(require_auth)])
app.include_router(content.router,  prefix="/api/content",  dependencies=[Depends(require_auth)])
app.include_router(logs.router,     prefix="/api/logs",     dependencies=[Depends(require_auth)])
# Public endpoint — no auth (called by landing portal)
app.include_router(public.router,   prefix="/api/public")
app.mount("/", StaticFiles(directory="../frontend", html=True), name="frontend")
```

**`admin/backend/requirements.txt`**
```
fastapi
uvicorn
python-multipart
psutil
bcrypt
itsdangerous        # signed session cookies
```

#### Router: `/api/auth`

| Method | Path | Description |
|--------|------|-------------|
| POST | `/login` | Submit credentials, receive session cookie |
| POST | `/logout` | Invalidate session cookie |
| GET | `/me` | Returns `{ username }` if session is valid, else 401 |
| POST | `/change-password` | Change username and/or password (requires current password) |

Login flow:
1. Accept `{ username, password }` JSON body
2. Look up stored bcrypt hash in `/etc/cafebox/admin-credentials`
3. If username matches and `bcrypt.checkpw()` passes → create session, set
   `HttpOnly; SameSite=Strict` cookie, return `200`
4. If credentials are wrong → increment per-IP failure counter; after 5
   failures in 15 minutes return `429` and lock out that IP for 15 minutes
5. All failure responses take a constant ~300ms (timing-safe)

Session enforcement (`require_auth` dependency):
- Read session cookie
- Verify it is a valid, unexpired signed session token
- If missing or invalid → return `401 { "detail": "Not authenticated" }`
- Valid sessions extend their expiry on each request (sliding window)

Credential storage (`/etc/cafebox/admin-credentials`):
```json
{ "username": "admin", "password_hash": "$2b$12$..." }
```
Owned by `root`, readable only by `cafebox` user (mode `0640`).

#### Router: `/api/services`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | List all services with status |
| POST | `/{id}/start` | Start a service |
| POST | `/{id}/stop` | Stop a service |
| POST | `/{id}/restart` | Restart a service |
| GET | `/{id}/status` | Single service status |

Service status object:
```json
{
  "id": "conduit",
  "display_name": "Matrix Chat",
  "running": true,
  "enabled": true,
  "memory_mb": 82,
  "uptime_seconds": 3600
}
```

Implementation: call `systemctl is-active`, `systemctl is-enabled`,
read `/proc/{pid}/status` for memory. Use `subprocess` with specific
passwordless sudo grants (see 1.3).

#### Router: `/api/storage`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Disk usage (onboard + USB) and per-service locations |
| POST | `/{service}/toggle` | Switch service between onboard/USB storage |

Toggle logic:
1. Stop service
2. Optionally migrate data (rsync onboard→USB or USB→onboard)
3. Update `storage.locations.{service}` in `cafe.yaml` via `scripts/config.py`
4. Run `storage/setup-symlinks.py`
5. Start service

Storage status object:
```json
{
  "onboard": { "total_gb": 32.0, "free_gb": 14.2, "path": "/mnt/cafebox-onboard" },
  "usb": { "present": false, "total_gb": null, "free_gb": null },
  "services": {
    "matrix":   { "location": "onboard", "size_mb": 42  },
    "books":    { "location": "onboard", "size_mb": 120 },
    "kiwix":    { "location": "onboard", "size_mb": 890 },
    "music":    { "location": "onboard", "size_mb": 0   },
    "navidrome":{ "location": "onboard", "size_mb": 12  }
  }
}
```

#### Router: `/api/network`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Current SSID, box name, channel, client count |
| POST | `/` | Update SSID, password, box name |

Update flow: write updated values to `cafe.yaml` via `scripts/config.py` →
re-run `scripts/generate-configs.py` → `systemctl restart hostapd` →
`systemctl reload nginx`. The response should warn that updating SSID
disconnects all clients.

#### Router: `/api/content`

| Method | Path | Description |
|--------|------|-------------|
| POST | `/upload/{service}` | Upload file to service data dir |
| GET | `/files/{service}` | List files in service data dir |
| DELETE | `/files/{service}/{filename}` | Delete a file |

Supported uploads per service:
- `books` → `.epub`, `.pdf`, `.mobi` → `/mnt/cafebox/books/`
- `kiwix` → `.zim` → `/mnt/cafebox/kiwix/`
- `music` → `.mp3`, `.flac`, `.ogg`, `.m4a` → `/mnt/cafebox/music/`

Use `python-multipart` for streaming uploads. Do not load whole file into RAM.

#### Router: `/api/logs`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/{service}?lines=100` | Last N lines from journald |

Implementation: `journalctl -u {service}.service -n {lines} --no-pager`

### 1.2 — Frontend (Single HTML File)

**`admin/frontend/index.html`**

No framework, no build step. Plain HTML + CSS + vanilla JS.

On load, the frontend calls `GET /api/auth/me`. If it returns `401`, it
renders the **login screen** instead of the dashboard. On successful login
it transitions to the main UI without a page reload.

**Login screen:**
- Username and password fields
- "Sign in" button
- Error message shown inline on bad credentials
- After 5 failures, show "Too many attempts — try again in 15 minutes"

**Main UI sections (shown after login):**
1. **Dashboard** — service cards with status indicators and start/stop buttons
2. **Storage** — disk usage bars, per-service location toggles (onboard/USB radio buttons), migrate data checkbox
3. **Content** — file upload drag-and-drop per service, file list with delete
4. **Network** — SSID, password, box name form
5. **Logs** — service selector dropdown, scrolling log output (polls `/api/logs` every 5s when open)
6. **Account** — change username/password form, logout button

Dashboard card design:
```
┌──────────────────────────────────────┐
│  💬 Matrix Chat          ● running   │
│  Memory: 82 MB  Uptime: 1h 2m        │
│                  [Stop]  [Restart]   │
└──────────────────────────────────────┘
```

### 1.3 — Sudo Grants

Add to `/etc/sudoers.d/cafebox-admin` (via `visudo -f`):

```
www-data ALL=(ALL) NOPASSWD: /bin/systemctl start conduit
www-data ALL=(ALL) NOPASSWD: /bin/systemctl stop conduit
www-data ALL=(ALL) NOPASSWD: /bin/systemctl restart conduit
www-data ALL=(ALL) NOPASSWD: /bin/systemctl start calibre-web
www-data ALL=(ALL) NOPASSWD: /bin/systemctl stop calibre-web
www-data ALL=(ALL) NOPASSWD: /bin/systemctl restart calibre-web
www-data ALL=(ALL) NOPASSWD: /bin/systemctl start kiwix
www-data ALL=(ALL) NOPASSWD: /bin/systemctl stop kiwix
www-data ALL=(ALL) NOPASSWD: /bin/systemctl restart kiwix
www-data ALL=(ALL) NOPASSWD: /bin/systemctl start navidrome
www-data ALL=(ALL) NOPASSWD: /bin/systemctl stop navidrome
www-data ALL=(ALL) NOPASSWD: /bin/systemctl restart navidrome
www-data ALL=(ALL) NOPASSWD: /bin/systemctl restart hostapd
www-data ALL=(ALL) NOPASSWD: /opt/cafebox/storage/setup-symlinks.sh
```

### 1.4 — Admin systemd Service

**`admin/backend/admin.service`**

```ini
[Unit]
Description=CafeBox Admin API
After=network.target

[Service]
User=www-data
WorkingDirectory=/opt/cafebox/admin/backend
ExecStart=/opt/cafebox/admin/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

### 1.5 — nginx for Admin

**`system/nginx/sites/admin.conf`**

```nginx
server {
    listen 80;
    server_name admin.cafe.box;

    # All traffic proxied to FastAPI — auth is handled in the application layer
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        client_max_body_size 4G;   # allow large ZIM/music uploads
    }

    location / {
        root /opt/cafebox/admin/frontend;
        try_files $uri /index.html;
    }
}
```

No `auth_basic` directives — authentication is fully handled by FastAPI.
nginx is purely a reverse proxy here.

Initial credentials are written to `/etc/cafebox/admin-credentials` by
`install.sh` using `admin.username` and `admin.password` from `cafe.yaml`.

**Stage 1 acceptance criteria:**
- [ ] `http://admin.cafe.box` shows a login form (not the dashboard)
- [ ] Correct username+password → redirects to dashboard
- [ ] Wrong credentials → inline error message
- [ ] 5 wrong attempts → lockout message, further attempts return 429 for 15 min
- [ ] Session persists across page reloads for up to 8 hours
- [ ] Logout button invalidates the session; browser is redirected to login
- [ ] Changing password via Account tab works; old session remains valid, new login requires new password
- [ ] Dashboard shows all services as stopped
- [ ] Start/stop buttons work and status updates without page reload
- [ ] Storage section shows onboard disk usage
- [ ] Network section shows current SSID
- [ ] Log viewer shows nginx logs

---

## Stage 2 — Matrix Chat (Conduit + Element Web)

**Goal:** Users connect to WiFi, open browser, land on `cafe.box`, tap Chat,
and get a fully E2E-encrypted Matrix chat room. No account creation required
(guest access enabled).

### 2.1 — Conduit

**Architecture notes:**
- Conduit is a Matrix homeserver written in Rust — much lighter than Synapse
- Binary is a single self-contained executable (~20MB)
- Database is RocksDB embedded — no PostgreSQL needed
- Target: ~80MB RAM at idle

**`services/conduit/install.sh`**

1. Download latest `conduit-aarch64-unknown-linux-musl` binary from
   https://gitlab.com/famedly/conduit/-/releases (not available in Debian repos)
2. Place at `/opt/cafebox/services/conduit/conduit`
3. Write `homeserver.yaml` (see below)
4. Create systemd service
5. On first run, create admin user and pre-create a `#general:cafe.box` room

**`services/conduit/homeserver.yaml.j2`** — Jinja2 template, rendered into
`/opt/cafebox/services/conduit/homeserver.yaml` by `services/conduit/install.sh`.

```yaml
[global]
server_name = "{{ box.domain }}"
database_path = "/mnt/cafebox/matrix"
database_backend = "rocksdb"
port = {{ services.chat.port }}
max_request_size = 20_000_000
allow_registration = true
allow_guest_registration = {{ services.chat.guest_access | lower }}
allow_encryption = true
allow_federation = false
trusted_servers = []
address = "127.0.0.1"
```

**`services/conduit/conduit.service`**

```ini
[Unit]
Description=Conduit Matrix Homeserver
After=network.target

[Service]
User=cafebox
ExecStart=/opt/cafebox/services/conduit/conduit
Environment=CONDUIT_CONFIG=/opt/cafebox/services/conduit/homeserver.yaml
WorkingDirectory=/opt/cafebox/services/conduit
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 2.2 — Element Web

Element Web is a static site — just files served by nginx. No Node.js at runtime.

**`services/element-web/install.sh`**

1. Download latest Element Web release tarball from GitHub releases
2. Extract to `/opt/cafebox/services/element-web/`
3. Write `config.json` (see below)

**`services/element-web/config.json.j2`** — rendered into
`/opt/cafebox/services/element-web/config.json` by `services/element-web/install.sh`.

```json
{
  "default_server_config": {
    "m.homeserver": {
      "base_url": "http://chat.{{ box.domain }}",
      "server_name": "{{ box.domain }}"
    }
  },
  "disable_custom_urls": true,
  "disable_guests": {{ "false" if services.chat.guest_access else "true" }},
  "default_theme": "light",
  "room_directory": {
    "servers": ["{{ box.domain }}"]
  }
}
```

### 2.3 — nginx Config for Chat

**`system/nginx/sites/chat.conf`**

```nginx
# Matrix homeserver API
server {
    listen 80;
    server_name chat.cafe.box;

    # Element Web static files
    location / {
        root /opt/cafebox/services/element-web;
        try_files $uri $uri/ /index.html;
    }

    # Matrix Client API
    location /_matrix/ {
        proxy_pass http://127.0.0.1:6167;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        client_max_body_size 20M;
    }

    # Matrix well-known
    location /.well-known/matrix/ {
        proxy_pass http://127.0.0.1:6167;
    }
}
```

### 2.4 — First-Run Room Setup

After Conduit starts for the first time, run a setup script that:

1. Registers an admin user (`cafebox_admin`) via the admin API
2. Creates a public room `#general:cafe.box` with:
   - Name: "CafeBox General"
   - Topic: "Welcome to CafeBox — anonymous local chat"
   - Guest access: enabled
   - History visibility: world_readable

This script runs once and is gated by a flag file (`/etc/cafebox/.matrix-initialized`).

**Stage 2 acceptance criteria:**
- [ ] `http://chat.cafe.box` loads Element Web
- [ ] User can join as guest (no registration required)
- [ ] `#general:cafe.box` room is visible and joinable
- [ ] Messages between two devices are E2E encrypted (lock icon visible)
- [ ] Conduit using ~80MB RAM at idle
- [ ] Admin UI shows Conduit as running/stopped with correct memory usage

---

## Stage 3 — Ebook Library (Calibre-Web)

**Goal:** Books in EPUB/PDF/MOBI format are browsable and downloadable at
`books.cafe.box`. Admin can upload books via the admin UI.

### 3.1 — Calibre-Web

**`services/calibre-web/install.sh`**

1. Install Python dependencies:
   ```bash
   pip3 install calibreweb --break-system-packages
   ```
   Or use a virtualenv at `/opt/cafebox/services/calibre-web/venv/`

2. Initialize Calibre library at `/mnt/cafebox/books/`
3. Write initial `app.db` configuration:
   - Set book dir to `/mnt/cafebox/books/`
   - Disable login requirement (public library mode)
   - Enable anonymous browsing
   - Disable user registration

**`services/calibre-web/calibre-web.service`**

```ini
[Unit]
Description=CafeBox Library (Calibre-Web)
After=network.target

[Service]
User=cafebox
ExecStart=/opt/cafebox/services/calibre-web/venv/bin/cps
Environment=CALIBRE_DBPATH=/opt/cafebox/services/calibre-web
WorkingDirectory=/opt/cafebox/services/calibre-web
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Default port: 8083

### 3.2 — nginx Config

**`system/nginx/sites/books.conf`**

```nginx
server {
    listen 80;
    server_name books.cafe.box;

    location / {
        proxy_pass http://127.0.0.1:8083;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        client_max_body_size 100M;
    }
}
```

### 3.3 — Upload Integration

Admin UI content upload for `books` service:
- Accepts `.epub`, `.pdf`, `.mobi`
- Saves to `/mnt/cafebox/books/uploads/` staging directory
- Runs `calibredb add` via subprocess to import into library and update metadata
- Returns success/failure per file

**Stage 3 acceptance criteria:**
- [ ] `http://books.cafe.box` loads Calibre-Web
- [ ] Browse and download a book without logging in
- [ ] Upload a book via admin UI — it appears in library within 30 seconds
- [ ] Calibre-Web using ~60MB RAM at idle

---

## Stage 4 — Educational Content (Kiwix)

**Goal:** Offline Wikipedia, Khan Academy, and other ZIM content available at
`learn.cafe.box`. ZIM files can be large (Wikipedia ~100GB, KA ~30GB) so
storage toggling is especially important here.

### 4.1 — Kiwix-Serve

**`services/kiwix/install.sh`**

1. Download `kiwix-serve` ARM64 binary from https://download.kiwix.org/release/kiwix-tools/
   (the Debian package is several major versions behind and has ZIM format
   compatibility issues with newer files — do not use `apt install kiwix-tools`)
2. Place at `/opt/cafebox/services/kiwix/kiwix-serve`
3. Create library XML file pointing at ZIM directory
4. Create systemd service

**`services/kiwix/kiwix.service`**

```ini
[Unit]
Description=CafeBox Learn (Kiwix)
After=network.target

[Service]
User=cafebox
ExecStart=/opt/cafebox/services/kiwix/kiwix-serve \
    --library /opt/cafebox/services/kiwix/library.xml \
    --port 8888 \
    --address 127.0.0.1
WorkingDirectory=/opt/cafebox/services/kiwix
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 4.2 — ZIM Library Management

When a new `.zim` file is uploaded via admin UI:

1. Save to `/mnt/cafebox/kiwix/`
2. Regenerate `library.xml`:
   ```bash
   kiwix-manage /opt/cafebox/services/kiwix/library.xml add /mnt/cafebox/kiwix/*.zim
   ```
3. Restart kiwix service

### 4.3 — nginx Config

**`system/nginx/sites/learn.conf`**

```nginx
server {
    listen 80;
    server_name learn.cafe.box;

    location / {
        proxy_pass http://127.0.0.1:8888;
        proxy_set_header Host $host;
        proxy_buffering off;   # Kiwix handles its own caching
    }
}
```

### 4.4 — Suggested ZIM Files

Document these in `README.md` with download URLs and sizes:

| ZIM File | Size | Source |
|---|---|---|
| `wikipedia_en_wp_2024.zim` | ~100GB | kiwix.org |
| `khan_academy_en.zim` | ~30GB | kiwix.org |
| `wikipedia_en_simple.zim` | ~1GB | kiwix.org (recommended for SD card) |
| `gutenberg_en.zim` | ~60GB | kiwix.org |
| `stackoverflow_en.zim` | ~35GB | kiwix.org |

Note in docs: ZIM files are the main reason to use USB storage.

**Stage 4 acceptance criteria:**
- [ ] `http://learn.cafe.box` loads Kiwix multi-content page
- [ ] At least one ZIM served correctly (use `wikipedia_en_simple.zim` for testing)
- [ ] Upload a ZIM via admin UI — it appears in Kiwix within 60 seconds
- [ ] Kiwix using ~30MB RAM at idle

---

## Stage 5 — Music (Navidrome)

**Goal:** Music files served at `music.cafe.box`. Users can stream directly
from the browser with no login required.

### 5.1 — Navidrome

**`services/navidrome/install.sh`**

1. Download `navidrome_linux_arm64.tar.gz` from GitHub releases
   (not available in Debian/Pi OS repos)
2. Extract to `/opt/cafebox/services/navidrome/`
3. Write `navidrome.toml`

**`services/navidrome/navidrome.toml.j2`** — rendered into
`/opt/cafebox/services/navidrome/navidrome.toml` by `services/navidrome/install.sh`.

```toml
MusicFolder = "/mnt/cafebox/music"
DataFolder = "/mnt/cafebox/navidrome"
Address = "127.0.0.1"
Port = {{ services.music.port }}
LogLevel = "info"
EnableGravatar = false
EnableSharing = true
DefaultDownsamplingFormat = "{{ services.music.downsample_format }}"
AuthRequestLimit = 0
```

**`services/navidrome/navidrome.service`**

```ini
[Unit]
Description=CafeBox Music (Navidrome)
After=network.target

[Service]
User=cafebox
ExecStart=/opt/cafebox/services/navidrome/navidrome
WorkingDirectory=/opt/cafebox/services/navidrome
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 5.2 — nginx Config

**`system/nginx/sites/music.conf`**

```nginx
server {
    listen 80;
    server_name music.cafe.box;

    location / {
        proxy_pass http://127.0.0.1:4533;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        client_max_body_size 500M;
    }
}
```

### 5.3 — Upload Integration

Admin UI for `music`:
- Accepts `.mp3`, `.flac`, `.ogg`, `.m4a`, `.opus`
- Saves directly to `/mnt/cafebox/music/`
- Triggers a Navidrome library rescan via its REST API:
  ```
  POST http://127.0.0.1:4533/api/scanLibrary
  ```
- New tracks appear within 60 seconds

**Stage 5 acceptance criteria:**
- [ ] `http://music.cafe.box` loads Navidrome
- [ ] Music streams in browser without login
- [ ] Upload tracks via admin UI — they appear in library within 60 seconds
- [ ] Navidrome using ~50MB RAM at idle

---

## Cross-Cutting Concerns

### Memory Budget

| Component | Idle RAM |
|---|---|
| Raspberry Pi OS base | ~80MB |
| nginx + dnsmasq + hostapd | ~30MB |
| Admin backend (FastAPI/uvicorn) | ~40MB |
| Conduit | ~80MB |
| Calibre-Web | ~60MB |
| Kiwix | ~30MB |
| Navidrome | ~50MB |
| **Total (all running)** | **~370MB** |

The Zero 2 W has 512MB. ~140MB headroom. Recommendation: do not run all
services simultaneously under load. Admin UI should show a memory warning
if free RAM drops below 64MB.

### USB Drive Auto-Mount

Add to `/etc/fstab` (or a udev rule):
```
/dev/sda1  /mnt/cafebox-usb  auto  defaults,nofail,x-systemd.automount  0 0
```

`nofail` ensures boot succeeds without the drive. Admin API polls for drive
presence before showing USB options.

### Service User

All services run as a dedicated `cafebox` user (no shell, no password):
```bash
useradd --system --no-create-home --shell /usr/sbin/nologin cafebox
```

### Logging

All services log to journald. Admin UI tails logs via `journalctl`. Log
rotation is handled automatically by journald (cap at 100MB total).

### Health Check Endpoint

The admin backend exposes a lightweight endpoint used by the landing portal:

```
GET /api/public/services/status  (no auth required — called by public portal)
```

Returns only `{ id, running }` — no sensitive data.

This route is registered under the unauthenticated `public` router and
requires no session cookie.

---

## Image Distribution

CafeBox ships as a pre-built, flashable `.img.xz` for non-technical operators.
Flashing it produces a Pi that boots directly into a working CafeBox — no
terminal, no `install.sh`, no configuration required to get started.

The image is built automatically by a GitHub Actions workflow on every tagged
release and published to GitHub Releases for download.

---

### Two User Tiers

| | Appliance User | Builder User |
|---|---|---|
| **How they get CafeBox** | Download `.img.xz`, flash with Pi Imager | Clone repo, edit `cafe.yaml` |
| **First run** | Insert SD card, power on, connect to WiFi | Run `sudo ./install.sh` on Pi or in VM |
| **Customization** | Admin UI only | Full `cafe.yaml` + admin UI |
| **Updates** | Reflash SD card | `git pull && sudo ./install.sh` |
| **Codebase** | Identical | Identical |

The pre-built image is produced by running `install.sh` against a vanilla Pi
OS Lite base — there is no separate code path.

---

### Build Pipeline

**`image/build.sh`** — builds the image locally for testing.

The build uses **pi-gen-action** concepts but runs via a straightforward
chroot approach that works without the full pi-gen framework:

```bash
#!/usr/bin/env bash
# image/build.sh
# Builds a flashable CafeBox image from a vanilla Pi OS Lite base.
# Requires: qemu-system-arm, qemu-utils, kpartx
# Usage: ./image/build.sh [output-path]
set -euo pipefail

BASE_URL="https://downloads.raspberrypi.com/raspios_lite_arm64/images"
OUTPUT="${1:-cafebox.img}"
WORK_DIR="$(mktemp -d)"

echo "==> Downloading latest Pi OS Lite (arm64)"
# Fetch the latest image URL from the releases page
LATEST=$(curl -sL "$BASE_URL/" | grep -oP 'raspios_lite_arm64-[^/]+(?=/)' | sort | tail -1)
IMG_URL="$BASE_URL/$LATEST/${LATEST}-raspios-bookworm-arm64-lite.img.xz"
curl -L "$IMG_URL" | xz -d > "$WORK_DIR/base.img"

echo "==> Expanding image to 8GB"
qemu-img resize "$WORK_DIR/base.img" 8G

echo "==> Mounting image partitions"
LOOP=$(sudo losetup -fP --show "$WORK_DIR/base.img")
sudo partprobe "$LOOP"
mkdir -p "$WORK_DIR/boot" "$WORK_DIR/root"
sudo mount "${LOOP}p1" "$WORK_DIR/boot"
sudo mount "${LOOP}p2" "$WORK_DIR/root"

echo "==> Pre-configuring SSH and first-boot"
sudo touch "$WORK_DIR/boot/ssh"
# Copy repo into image
sudo cp -r "$(pwd)" "$WORK_DIR/root/opt/cafebox"
# Install first-boot service
sudo cp image/first-boot.service "$WORK_DIR/root/etc/systemd/system/"
sudo ln -sf /etc/systemd/system/first-boot.service \
    "$WORK_DIR/root/etc/systemd/system/multi-user.target.wants/first-boot.service"

echo "==> Running install.sh inside chroot"
sudo chroot "$WORK_DIR/root" /bin/bash -c "
    cd /opt/cafebox
    apt-get update -qq
    ./install.sh
"

echo "==> Cleaning up and compressing"
sudo umount "$WORK_DIR/boot" "$WORK_DIR/root"
sudo losetup -d "$LOOP"

# Shrink the image to minimum size with pishrink
curl -sL https://raw.githubusercontent.com/Drewsif/PiShrink/master/pishrink.sh | \
    sudo bash -s -- "$WORK_DIR/base.img"

xz -9 -T0 "$WORK_DIR/base.img"
mv "$WORK_DIR/base.img.xz" "$OUTPUT.xz"
echo "==> Image built: $OUTPUT.xz"
```

**PiShrink** is used after install to trim the image back down to the minimum
size needed to hold the installed content before compressing with xz. This
keeps download sizes small.

---

### GitHub Actions Workflow

**`.github/workflows/build-image.yml`**

Triggered on a version tag push (e.g. `v1.0.0`). Builds the image, computes
a SHA256 checksum, and publishes both to GitHub Releases.

```yaml
name: Build CafeBox Image

on:
  push:
    tags:
      - 'v*'

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Install dependencies
        run: |
          sudo apt-get update
          sudo apt-get install -y \
            qemu-system-arm qemu-utils kpartx xz-utils curl

      - name: Build image
        run: |
          chmod +x image/build.sh
          ./image/build.sh cafebox-${{ github.ref_name }}

      - name: Checksum
        run: |
          sha256sum cafebox-${{ github.ref_name }}.img.xz \
            > cafebox-${{ github.ref_name }}.img.xz.sha256

      - name: Publish release
        uses: softprops/action-gh-release@v2
        with:
          files: |
            cafebox-${{ github.ref_name }}.img.xz
            cafebox-${{ github.ref_name }}.img.xz.sha256
          body: |
            ## CafeBox ${{ github.ref_name }}

            ### Installation
            1. Download `cafebox-${{ github.ref_name }}.img.xz`
            2. Flash to a 8GB+ SD card using [Raspberry Pi Imager](https://www.raspberrypi.com/software/)
            3. Insert into Pi Zero 2 W and power on
            4. Connect to the **CafeBox** WiFi network
            5. Open a browser — your admin password is shown on the landing page
```

---

### Release Checklist

Before tagging a release:
- [ ] All stage acceptance criteria passing in the QEMU VM
- [ ] Stage 0 network behavior verified on real Pi hardware
- [ ] `cafe.yaml` defaults reviewed (sensible SSID, chat enabled, others disabled)
- [ ] Default admin username is `admin` and no static password is set
  (first-boot service generates it)
- [ ] `image/build.sh` tested locally — image boots and first-boot banner appears
- [ ] README updated with flashing instructions

---



The development environment is a full **Raspberry Pi OS VM running under QEMU
system emulation** on the developer's Linux Mint machine. This eliminates the
entire dev/prod abstraction layer from the previous approach:

- No `docker-compose.dev.yml`
- No `service_manager.py` dev/prod split
- No `dev.enabled` flag in `cafe.yaml`
- `install.sh` runs directly in the VM, identically to the Pi
- `systemd`, `nginx`, `dnsmasq`, and all service configs behave exactly as
  in production

The only genuine gap from real hardware is WiFi: `hostapd` cannot create an
AP without a physical radio. Everything else — systemd service management,
nginx routing, the admin UI, all content services — is production-identical.

---

### Why Full System Emulation over User-Space QEMU

| Concern | QEMU user-static + Docker | QEMU full system (Pi OS VM) |
|---|---|---|
| Systemd | ✗ Replaced by Docker Compose | ✓ Real systemd |
| `install.sh` | ✗ Can't run directly | ✓ Runs identically to Pi |
| `dev.enabled` flag | Required | Not needed |
| `service_manager.py` abstraction | Required | Not needed |
| Architecture parity | ✓ ARM64 via user-space | ✓ ARM64 via system emulation |
| OS environment | ✗ Alpine/Ubuntu base images | ✓ Actual Raspberry Pi OS |
| WiFi (hostapd) | ✗ Not testable | ✗ Not testable (no radio) |
| Speed | Faster startup | Slower startup (~2–4× on first boot) |

The tradeoff is startup time. Full system emulation is slower than
user-space QEMU, but for CafeBox development this is fine — once the VM
is up, day-to-day iteration (editing code, running `install.sh`, testing in
the browser) is fast. The slower path is only VM boot.

---

### One-Time VM Setup

#### 1. Install QEMU

```bash
sudo apt-get update
sudo apt-get install -y \
    qemu-system-arm \
    qemu-utils \
    qemu-efi-aarch64 \
    cloud-image-utils
```

#### 2. Download Raspberry Pi OS Lite (64-bit)

Download the latest **Raspberry Pi OS Lite (64-bit)** image from
`https://www.raspberrypi.com/software/operating-systems/` — use the `.img.xz`
file. Decompress it:

```bash
xz -d 2024-*-raspios-bookworm-arm64-lite.img.xz
mv 2024-*-raspios-bookworm-arm64-lite.img ~/cafebox-dev.img
```

#### 3. Resize the Image

The default image is small. Expand it to give the VM enough room for
services and content:

```bash
qemu-img resize ~/cafebox-dev.img 16G
```

The filesystem will be expanded on first boot by Pi OS's `init_resize.sh`
automatically.

#### 4. Extract the Kernel and DTB

QEMU's `virt` machine (the most stable aarch64 machine type) needs a kernel
supplied separately. Extract directly from the image:

```bash
# Mount the boot partition (partition 1) from the image
OFFSET=$(fdisk -l ~/cafebox-dev.img | grep "FAT32" | awk '{print $2}')
OFFSET_BYTES=$((OFFSET * 512))
mkdir -p /tmp/piboot
sudo mount -o loop,offset=$OFFSET_BYTES ~/cafebox-dev.img /tmp/piboot

# Copy out the kernel and device tree
cp /tmp/piboot/kernel8.img ~/cafebox-kernel8.img
cp /tmp/piboot/bcm2710-rpi-3-b-plus.dtb ~/cafebox.dtb
sudo umount /tmp/piboot
```

#### 5. Pre-configure SSH (Headless Boot)

Mount the boot partition again and enable SSH and set a password so you can
connect without a display:

```bash
sudo mount -o loop,offset=$OFFSET_BYTES ~/cafebox-dev.img /tmp/piboot

# Enable SSH on first boot
sudo touch /tmp/piboot/ssh

# Set a userconf (pi user with password "cafebox")
# Generate with: echo "cafebox" | openssl passwd -6 -stdin
echo 'pi:$6$rounds=656000$...' | sudo tee /tmp/piboot/userconf.txt

sudo umount /tmp/piboot
```

Or use the **Raspberry Pi Imager** tool to pre-configure the image with SSH
and credentials before the step above — it has a GUI for this.

#### 6. `scripts/vm.sh` — VM Management Script

All VM operations go through this single script. It reads `cafe.yaml` for
the domain name and constructs the QEMU command.

**`scripts/vm.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

DOMAIN=$(python3 -c "import yaml; print(yaml.safe_load(open('cafe.yaml'))['box']['domain'])")
VM_IMG="${CAFEBOX_VM_IMG:-$HOME/cafebox-dev.img}"
VM_KERNEL="${CAFEBOX_VM_KERNEL:-$HOME/cafebox-kernel8.img}"
VM_DTB="${CAFEBOX_VM_DTB:-$HOME/cafebox.dtb}"
VM_RAM="${CAFEBOX_VM_RAM:-1G}"
VM_CPUS="${CAFEBOX_VM_CPUS:-4}"
SSH_PORT=2222
HTTP_PORT=8080   # VM's port 80 forwarded to host port 8080

case "${1:-}" in

  start)
    echo "==> Starting CafeBox dev VM"
    qemu-system-aarch64 \
      -machine virt \
      -cpu cortex-a53 \
      -m "$VM_RAM" \
      -smp "$VM_CPUS" \
      -kernel "$VM_KERNEL" \
      -dtb "$VM_DTB" \
      -append "root=/dev/vda2 rootfstype=ext4 rw console=ttyAMA0 loglevel=3" \
      -drive "file=$VM_IMG,format=raw,if=virtio" \
      -netdev "user,id=net0,hostfwd=tcp::${SSH_PORT}-:22,hostfwd=tcp::${HTTP_PORT}-:80" \
      -device virtio-net-pci,netdev=net0 \
      -virtfs "local,path=$(pwd),mount_tag=cafebox,security_model=mapped-xattr,readonly=on" \
      -nographic \
      -serial mon:stdio &
    VM_PID=$!
    echo $VM_PID > /tmp/cafebox-vm.pid
    echo "==> VM started (PID $VM_PID)"
    echo "==> SSH:  ssh -p $SSH_PORT pi@localhost"
    echo "==> Web:  http://localhost:$HTTP_PORT (after install)"
    ;;

  stop)
    if [ -f /tmp/cafebox-vm.pid ]; then
      kill "$(cat /tmp/cafebox-vm.pid)" 2>/dev/null || true
      rm /tmp/cafebox-vm.pid
      echo "==> VM stopped"
    else
      echo "==> No VM PID file found"
    fi
    ;;

  ssh)
    ssh -p "$SSH_PORT" \
        -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null \
        pi@localhost "${@:2}"
    ;;

  mount-share)
    # Run inside the VM to mount the host repo share
    # Called via: ./scripts/vm.sh ssh "sudo ./scripts/vm.sh mount-share"
    mkdir -p /opt/cafebox-dev
    mount -t 9p -o trans=virtio,version=9p2000.L cafebox /opt/cafebox-dev
    echo "==> Host repo mounted at /opt/cafebox-dev (read-only)"
    ;;

  status)
    if [ -f /tmp/cafebox-vm.pid ] && kill -0 "$(cat /tmp/cafebox-vm.pid)" 2>/dev/null; then
      echo "==> VM is running (PID $(cat /tmp/cafebox-vm.pid))"
    else
      echo "==> VM is not running"
    fi
    ;;

  *)
    echo "Usage: $0 {start|stop|ssh|mount-share|status}"
    exit 1
    ;;
esac
```

#### 7. Host nginx Proxy (Clean Subdomain Access)

The VM's port 80 is forwarded to host port 8080. To access `http://cafe.box`
(and subdomains) cleanly at port 80 in the browser, the host's nginx proxies
all `*.cafe.box` traffic to the VM:

Install nginx on the host:
```bash
sudo apt-get install -y nginx
```

**`/etc/nginx/sites-available/cafebox-dev`**

```nginx
# Proxy all *.cafe.box traffic to the QEMU VM on port 8080
# This runs on the host machine, not inside the VM

server {
    listen 80;
    server_name cafe.box *.cafe.box;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        client_max_body_size 4G;
    }
}
```

```bash
sudo ln -sf /etc/nginx/sites-available/cafebox-dev /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

`/etc/hosts` still needed for DNS — `dev-hosts.sh` is unchanged:
```bash
./scripts/dev-hosts.sh add
# Adds: 127.0.0.1  cafe.box, chat.cafe.box, books.cafe.box, etc.
```

With both in place, opening `http://cafe.box` in the browser on the host
machine routes: browser → host nginx (port 80) → VM nginx (port 8080) →
individual services inside the VM.

---

### In-VM First Boot Setup

On first SSH into the VM:

```bash
# 1. Mount the host repo share (read-only reference)
sudo mkdir -p /opt/cafebox-dev
sudo mount -t 9p -o trans=virtio,version=9p2000.L cafebox /opt/cafebox-dev

# 2. Clone a working copy into the VM's own filesystem
#    (can't run install.sh from a read-only share)
git clone /opt/cafebox-dev /opt/cafebox
cd /opt/cafebox

# 3. Edit cafe.yaml if needed, then run the installer
sudo ./install.sh
```

For subsequent iterations, the workflow is:

```bash
# On the host — make code changes
vim admin/backend/routers/services.py

# In the VM — pull the changes and re-run
cd /opt/cafebox
git pull /opt/cafebox-dev   # pull from the mounted read-only share
sudo ./install.sh            # idempotent — only changed parts are updated
```

Or for pure code changes that don't need `install.sh` (e.g. FastAPI edits),
just `rsync` the changed file and restart the service:

```bash
# From the host:
./scripts/vm.sh ssh "cd /opt/cafebox && git pull /opt/cafebox-dev && sudo systemctl restart cafebox-admin"
```

---

### Repository Changes from Previous Approach

The following are **removed** — they are no longer needed:

```
# REMOVED
├── docker-compose.dev.yml
├── docker/
│   ├── nginx/Dockerfile
│   ├── admin/Dockerfile
│   └── portal/Dockerfile
```

`service_manager.py` is simplified — the `DEV_MODE` branch is removed and
it becomes a thin wrapper around `systemctl` only:

```python
# admin/backend/service_manager.py — no dev/prod split needed
import subprocess

def start(service_id: str):
    subprocess.run(["sudo", "systemctl", "start", service_id], check=True)

def stop(service_id: str):
    subprocess.run(["sudo", "systemctl", "stop", service_id], check=True)

def restart(service_id: str):
    subprocess.run(["sudo", "systemctl", "restart", service_id], check=True)

def status(service_id: str) -> dict:
    active = subprocess.run(
        ["systemctl", "is-active", service_id],
        capture_output=True, text=True
    ).stdout.strip() == "active"
    enabled = subprocess.run(
        ["systemctl", "is-enabled", service_id],
        capture_output=True, text=True
    ).stdout.strip() == "enabled"
    return {"running": active, "enabled": enabled, "memory_mb": _get_memory(service_id)}
```

`cafe.yaml` loses the `dev` block entirely — no flag needed.

`scripts/dev-setup.sh` is replaced by `scripts/vm.sh` + the one-time QEMU
install steps above.

---

### Updated Repository Structure

```
cafebox/
├── README.md
├── cafe.yaml                    # No dev block — same file for VM and Pi
├── install.sh
├── scripts/
│   ├── vm.sh                    # VM lifecycle: start, stop, ssh, mount-share
│   ├── dev-hosts.sh             # Adds *.cafe.box to /etc/hosts (unchanged)
│   ├── config.py
│   └── generate-configs.py
└── ...all other files unchanged...
```

---

### Makefile (Updated)

```makefile
.PHONY: vm-start vm-stop vm-ssh vm-status hosts-add hosts-remove reload

vm-start:     ## Start the Pi OS dev VM
	bash scripts/vm.sh start

vm-stop:      ## Stop the dev VM
	bash scripts/vm.sh stop

vm-ssh:       ## SSH into the dev VM
	bash scripts/vm.sh ssh

vm-status:    ## Check if the VM is running
	bash scripts/vm.sh status

hosts-add:    ## Add *.cafe.box to /etc/hosts
	bash scripts/dev-hosts.sh add

hosts-remove: ## Remove *.cafe.box from /etc/hosts
	bash scripts/dev-hosts.sh remove

install:      ## Run install.sh inside the VM
	bash scripts/vm.sh ssh "cd /opt/cafebox && git pull /opt/cafebox-dev && sudo ./install.sh"

reload-nginx: ## Reload nginx inside the VM (after config changes)
	bash scripts/vm.sh ssh "sudo systemctl reload nginx"

logs:         ## Tail all service logs in the VM
	bash scripts/vm.sh ssh "sudo journalctl -f"
```

First-time setup:
```bash
# One time on the host
sudo apt-get install -y qemu-system-arm qemu-utils nginx
./scripts/dev-hosts.sh add
sudo ln -sf $(pwd)/scripts/nginx-cafebox-dev.conf /etc/nginx/sites-enabled/
sudo systemctl reload nginx

# One time in the VM (after make vm-start)
make vm-ssh
# ... first-boot steps above ...
```

Day-to-day dev loop:
```bash
make vm-start     # boot VM (if not already running)
# ... edit files on host ...
make install      # sync + re-run install.sh in VM
# ... open http://cafe.box in host browser ...
make vm-stop      # done for the day
```

---

### What Still Can't Be Tested in the VM

| Feature | Testable in VM | Notes |
|---|---|---|
| All services (nginx, admin, chat, books, learn, music) | ✓ | Full production parity |
| systemd service management | ✓ | Identical to Pi |
| `install.sh` idempotency | ✓ | Run it repeatedly |
| `cafe.yaml` config rendering | ✓ | Identical to Pi |
| Admin UI | ✓ | Via host browser |
| E2E Matrix encryption | ✓ | Two browser tabs |
| `hostapd` WiFi AP | ✗ | No radio hardware |
| Captive portal on real devices | ✗ | Requires actual WiFi clients |
| `dnsmasq` DHCP to real clients | ✗ | Requires real network segment |
| Pi-specific hardware (GPIO, etc.) | ✗ | N/A for this project |

The three untestable items all live in Stage 0 and only require a single
focused hardware test session once the VM work is complete.

---

### Development Workflow Summary

```
┌──────────────────────────────────────────────────────────────┐
│  Linux Mint Host                                              │
│                                                               │
│  edit files in cafebox/                                       │
│       │                                                       │
│  make install  ──→  git pull + sudo ./install.sh (in VM)     │
│                                                               │
│  host nginx (port 80)                                         │
│       │  proxy_pass → VM port 8080                           │
│       │                                                       │
│  Browser → http://cafe.box ──────────────────────────────┐   │
│                                                           │   │
│  ┌────────────────────────────────────────────────────┐  │   │
│  │  QEMU — Raspberry Pi OS (arm64)               VM  │  │   │
│  │                                                    │  │   │
│  │  systemd                                           │  │   │
│  │    nginx ──────────────────────────────────────────┘  │   │
│  │    cafebox-admin  (FastAPI)                            │   │
│  │    conduit        (Matrix)                             │   │
│  │    calibre-web                                         │   │
│  │    kiwix                                               │   │
│  │    navidrome                                           │   │
│  │                                                        │   │
│  │  /opt/cafebox-dev ←── 9p share from host (read-only)  │   │
│  └────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
         │
         │  git push
         ▼
┌──────────────────────────────────────────────────────────────┐
│  Raspberry Pi Zero 2 W                                        │
│                                                               │
│  git pull && sudo ./install.sh                                │
│  (identical to what ran in the VM — no surprises)             │
└──────────────────────────────────────────────────────────────┘
```

---

## Agent Implementation Notes

- **Two delivery tiers share one codebase.** The pre-built image is produced
  by running `install.sh` against a vanilla Pi OS base. There is no separate
  image-specific code path. Keep it that way.
- **First-boot password is generated at runtime, not build time.** Never
  bake a static password into the image. `first-boot.service` must run on
  the Pi, not during `image/build.sh`.
- **`cafe.yaml` is the single source of truth.** All system configs are
  rendered from it. Never hardcode values from `cafe.yaml` into templates,
  scripts, or service configs.
- **Build and test in the Pi OS VM first.** All stages should be fully
  working in the QEMU VM before doing a hardware deploy. The VM is the
  primary build target.
- **`install.sh` is the only deployment mechanism** — for both the VM and
  the Pi. There is no separate dev install path.
- **`service_manager.py` uses only `systemctl`.** There is no dev/prod
  split. The VM runs real systemd.
- **Build stages in order.** Each stage depends on the previous. Do not
  install a service before the admin UI is functional.
- **Never hardcode the domain, IP, or ports.** All configs are rendered
  from Jinja2 templates using values from `cafe.yaml`.
- **All install scripts must be idempotent.** Re-running should not break
  a working installation — this is tested constantly in the VM.
- **SD card writes.** Minimize writes to `/` (SD card root). All service
  data goes through `/mnt/cafebox/` symlinks. Log to journald (RAM-buffered),
  not flat files.
- **Conduit binary.** Not available in Debian/Pi OS repos — download from the
  official GitLab CI artifacts for `aarch64-unknown-linux-musl` (statically
  linked, no libc dependency). This same binary runs in both the VM and on
  the Pi.
- **Element Web.** Not available as a distro package — download the pre-built
  release tarball from GitHub. Do NOT build from source on the Pi or in the VM.
- **Kiwix-serve.** Available in Debian repos but the packaged version is
  several major versions behind upstream and has ZIM format compatibility
  issues with newer files. Use the static ARM64 binary from
  download.kiwix.org instead.
- **Navidrome.** Not available in Debian/Pi OS repos — use the `arm64`
  tarball from GitHub releases.
- **Everything else** (nginx, dnsmasq, hostapd, Python, Calibre-Web
  dependencies) should use `apt` — the distro packages are current enough
  and it's less to maintain.
- **Test WiFi on real hardware last.** Everything except `hostapd` and
  captive portal behavior can be fully validated in the VM. Reserve a
  single hardware session for Stage 0 network testing once all other
  stages are passing.
