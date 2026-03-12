# Stage 0 — Base Infrastructure Tasks

These tasks establish the foundational repository structure, configuration system,
networking stack, and image-build pipeline for CafeBox.

Complete tasks in the order they are numbered. Each task is scoped to approximately
one hour of work for an intermediate software engineer.

---

## Task 0.01 — Repository Scaffolding

Create all top-level directories and placeholder files described in the repository
structure diagram in `PLAN.md`. This gives every subsequent task a concrete place
to land.

**Deliverables:**
- Empty `cafe.yaml` (with `# TODO` comment)
- Empty `install.sh` (shebang only)
- Empty `Makefile`
- Directories: `scripts/`, `image/`, `system/templates/`, `system/generated/`,
  `storage/`, `services/conduit/`, `services/element-web/`, `services/calibre-web/`,
  `services/kiwix/`, `services/navidrome/`, `admin/backend/`, `admin/frontend/`,
  `portal/`
- `portal/index.html` (HTML stub)
- `image/README.md` (one-line stub)

**Acceptance criteria:** `tree -L 3` matches the layout in `PLAN.md`.

---

## Task 0.02 — `cafe.yaml` Sample Configuration

Write a fully-commented sample `cafe.yaml` that covers every field referenced in
the plan: box identity (`box.domain`, `box.name`), WiFi hotspot settings, storage
paths, and per-service enable flags.

**Deliverables:**
- `cafe.yaml` with realistic defaults and inline comments

**Acceptance criteria:**
- All keys referenced elsewhere in the codebase load without KeyError.
- File is valid YAML (`python -c "import yaml; yaml.safe_load(open('cafe.yaml'))"`).

---

## Task 0.03 — `scripts/config.py` — Configuration Loader

Write a small Python module that loads and validates `cafe.yaml`. It must be
importable by both `install.sh` (via `python scripts/config.py`) and the admin
backend.

**Deliverables:**
- `scripts/config.py` exposing a `load_config(path="cafe.yaml")` function that
  returns a validated dict/namespace.
- Basic sanity checks (required keys present, domain is a valid hostname, etc.).

**Acceptance criteria:**
- `python scripts/config.py` prints resolved config without errors.
- Missing required key raises a clear `ConfigError` with the key name.

---

## Task 0.04 — `scripts/generate-configs.py` — Jinja2 Template Renderer

Write the script that reads `cafe.yaml` (via `config.py`) and renders every
Jinja2 template in `system/templates/` into `system/generated/`.

**Deliverables:**
- `scripts/generate-configs.py`
- At least one stub template (`system/templates/nginx.conf.j2`) and its
  expected rendered form documented in comments.

**Acceptance criteria:**
- Running `python scripts/generate-configs.py` produces files in `system/generated/`.
- Re-running is idempotent.
- Unknown template variables raise a clear error, not a silent empty string.

---

## Task 0.05 — `Makefile` Dev Shortcuts

Add the developer convenience targets described in `PLAN.md`:
`vm-start`, `vm-stop`, `vm-ssh`, `install`, `logs`, `generate-configs`.

**Deliverables:**
- `Makefile` with each target delegating to the appropriate script.
- `.PHONY` declaration for all targets.

**Acceptance criteria:**
- `make help` (or `make` with a default help target) lists all targets with
  one-line descriptions.
- Each target fails with a descriptive message if its prerequisite (e.g., `vm.sh`)
  does not exist yet.

---

## Task 0.06 — `scripts/vm.sh` — VM Lifecycle Management

Write the shell script that manages a QEMU/libvirt development VM: `start`,
`stop`, `ssh`, `mount-share`, `status` sub-commands.

**Deliverables:**
- `scripts/vm.sh` with the sub-commands listed above.
- VM disk image path and SSH port configurable via environment variables with
  documented defaults.

**Acceptance criteria:**
- `scripts/vm.sh status` exits 0 and prints "stopped" when no VM is running.
- Script is POSIX-compatible (`bash -n scripts/vm.sh` passes).

---

## Task 0.07 — `scripts/dev-hosts.sh` — Local DNS Entries

Write a script that adds (and can remove) `*.cafe.box` wildcard entries to
`/etc/hosts` so the developer's browser resolves the box domain locally.

**Deliverables:**
- `scripts/dev-hosts.sh add` — appends entries, idempotent.
- `scripts/dev-hosts.sh remove` — removes the entries.

**Acceptance criteria:**
- Running `add` twice does not duplicate entries.
- Script requires `sudo` and exits with a helpful message if not run as root.

---

## Task 0.08 — `install.sh` Bootstrap Script

Write the main bootstrap script that runs identically on a Raspberry Pi and on
the development VM. It should: install system packages, call
`generate-configs.py`, enable systemd units, and run `storage/setup-symlinks.py`.

**Deliverables:**
- `install.sh` with clearly separated phases: package installation, config
  generation, service enablement, storage setup.
- Script detects whether it is running on Pi hardware vs. VM and logs accordingly.

**Acceptance criteria:**
- `bash -n install.sh` passes (syntax check).
- Script is idempotent: running it twice does not break a working installation.
- Each phase is guarded so a failure stops the script immediately (`set -e`).

---

## Task 0.09 — Network Policy: Firewall Rules (Hotspot-Only, Default-Deny)

Implement the threat-model firewall rules from Stage 0.0 of `PLAN.md` using
`nftables` (preferred) or `iptables`.

Rules must enforce:
- No WAN routing/NAT for connected clients.
- Allow DHCP (UDP 67/68), DNS (UDP/TCP 53), and HTTP (TCP 80) on the AP
  interface only.
- Drop everything else from clients.
- Allow full outbound from the box itself for build-time downloads.

**Deliverables:**
- `system/templates/nftables.conf.j2` (or `iptables.rules.j2`)
- Section in `install.sh` (or a separate `scripts/firewall.sh`) that applies rules
  and persists them across reboots.

**Acceptance criteria:**
- Rules template renders without Jinja2 errors.
- Comments in the file map each rule to the threat-model bullet it addresses.

---

## Task 0.10 — `hostapd` + `dnsmasq` Configuration Templates

Create Jinja2 templates for `hostapd.conf` and `dnsmasq.conf` so the WiFi
hotspot and captive-portal DNS are driven by `cafe.yaml`.

`dnsmasq` must:
- Resolve `*.cafe.box` to the box IP.
- Serve DHCP leases on the AP interface.
- Return the box IP for all other DNS queries (captive portal intercept).

**Deliverables:**
- `system/templates/hostapd.conf.j2`
- `system/templates/dnsmasq.conf.j2`

**Acceptance criteria:**
- Both templates render with the sample `cafe.yaml` without errors.
- Rendered `dnsmasq.conf` contains a `address=/#/<box_ip>` line.

---

## Task 0.11 — nginx Configuration Template + Captive Portal Redirect

Create a Jinja2 template for the main `nginx.conf` that:
- Serves the landing portal on port 80.
- Includes the captive-portal redirect: `location /generate_204 { return 302 http://{{ box.domain }}/; }`.
- Includes stub `location` blocks for each service (commented-out until the
  service is installed).

**Deliverables:**
- `system/templates/nginx.conf.j2`

**Acceptance criteria:**
- Template renders to valid nginx configuration (`nginx -t` passes against the
  rendered file).
- `/generate_204` block is present and points to `box.domain`.

---

## Task 0.12 — `portal/index.html` Landing Page

Build the portal landing page. It must:
- Call `GET /api/public/services/status` on page load.
- Render a tile grid from the response (name, enabled, URL).
- Show the first-boot password banner if the API response includes
  `first_boot: true`.
- Work with no JavaScript frameworks (vanilla JS acceptable; no CDN fetches).

**Deliverables:**
- `portal/index.html` (self-contained: inline CSS + JS or local assets only)

**Acceptance criteria:**
- Page renders correctly with a hard-coded mock API response (no server needed).
- Password banner is visible when mock response has `first_boot: true`.
- Password banner is hidden when `first_boot: false`.
- No external CDN resources referenced.

---

## Task 0.13 — `image/first-boot.sh` + `image/first-boot.service`

Implement the one-shot first-boot credential generator:
- Generate a random 12-character alphanumeric admin password.
- Hash it and set it for the `cafebox-admin` system user.
- Write a flag file (e.g., `/var/lib/cafebox/first-boot-done`) so the script
  does not re-run.
- Store the plaintext password temporarily in a readable location so the portal
  can display it (e.g., `/run/cafebox/initial-password`).

**Deliverables:**
- `image/first-boot.sh`
- `image/first-boot.service` (systemd oneshot, `Before=nginx.service`)

**Acceptance criteria:**
- Script is idempotent: second run exits 0 and does nothing.
- Password file has permissions `0400` owned by `cafebox-admin` (the admin
  backend process user from Task 1.05), so the API endpoint in Task 1.06 can
  read it. The portal landing page reads the flag via the
  `/api/public/services/status` API — not by accessing the file directly —
  so nginx's process user does not need read access to this file.
- `bash -n image/first-boot.sh` passes.

---

## Task 0.14 — `storage/setup-symlinks.py` Storage Layout

Write the script that creates the storage symlinks so each service's writable
data lives under a single top-level `storage/` mount point (easy to back up or
move to external media).

**Deliverables:**
- `storage/setup-symlinks.py` that reads storage paths from `cafe.yaml` and
  creates/updates symlinks under `/srv/cafebox/` (or configurable base).

**Acceptance criteria:**
- Script is idempotent.
- `python storage/setup-symlinks.py --dry-run` prints what it would do without
  making changes.
- Missing target directories are created automatically.

---

## Task 0.15 — `image/build.sh` — Flashable Image Builder

Write the script that produces a flashable `.img.xz` Raspberry Pi image.
It should use `pi-gen` (or a minimal custom loop-mount approach) to:
1. Start from a Raspberry Pi OS Lite base.
2. Copy repository files into the image.
3. Pre-install system packages offline (using a pre-downloaded package cache).
4. Enable `first-boot.service`.

**Deliverables:**
- `image/build.sh`
- `image/README.md` with instructions for building and flashing

**Acceptance criteria:**
- `bash -n image/build.sh` passes.
- README documents required host tools and estimated build time.

---

## Task 0.16 — `.github/workflows/build-image.yml` CI Image Build

Create a GitHub Actions workflow that:
- Triggers on tag push (`v*`).
- Runs `image/build.sh`.
- Uploads the resulting `.img.xz` as a release asset.

**Deliverables:**
- `.github/workflows/build-image.yml`

**Acceptance criteria:**
- Workflow YAML is valid (`actionlint` or `yamllint`).
- Uses pinned action versions (e.g., `actions/checkout@v4`).
- Workflow only runs on version tags, not on every push.
