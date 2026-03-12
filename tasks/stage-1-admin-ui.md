# Stage 1 — Admin UI Tasks

These tasks build the CafeBox administration interface: a secure, session-based
web UI that lets the operator manage services, upload content, and change their
password — all from the local hotspot network.

Complete tasks in the order they are numbered. Each task is scoped to approximately
one hour of work for an intermediate software engineer.

**Prerequisites:** All Stage 0 tasks must be complete before starting Stage 1.

---

## Task 1.01 — Admin Backend Project Setup

Scaffold the admin backend application. Use Python with FastAPI (lightweight,
async, good for embedded use) inside `admin/backend/`.

**Deliverables:**
- `admin/backend/requirements.txt` (FastAPI, uvicorn, PyYAML, itsdangerous)
- `admin/backend/main.py` — application entry point; mounts routers
- `admin/backend/config.py` — loads `cafe.yaml` via `../../scripts/config.py`
- `admin/backend/README.md` — how to run locally

**Acceptance criteria:**
- `uvicorn admin.backend.main:app` starts without errors.
- `GET /healthz` returns `{"status": "ok"}`.

---

## Task 1.02 — Signed-Cookie Session Middleware

Add session support using signed cookies (no server-side store required for an
embedded single-operator device). Use `itsdangerous` for signing.

**Deliverables:**
- `admin/backend/session.py` — `SessionMiddleware` or dependency that reads/writes
  a signed cookie named `cafebox_session`.
- Secret key loaded from an environment variable `CAFEBOX_SECRET_KEY` with a
  clear startup error if unset.

**Acceptance criteria:**
- A route protected by `Depends(require_session)` returns 401 when no valid
  cookie is present.
- Cookie is `HttpOnly`, `SameSite=Strict`, `Secure=False` (HTTP on LAN is
  acceptable; document why).

---

## Task 1.03 — CSRF Token Protection

Add CSRF defence to all state-changing endpoints (`POST`, `PUT`, `DELETE`, `PATCH`).
Use the double-submit pattern: server sets a `csrf_token` cookie; client must
echo it in an `X-CSRF-Token` request header.

**Deliverables:**
- `admin/backend/csrf.py` — FastAPI dependency `verify_csrf_token` that:
  - Issues a `csrf_token` cookie on `GET` requests.
  - Validates the `X-CSRF-Token` header against the cookie on state-changing
    requests.
  - Returns 403 with `{"detail": "CSRF validation failed"}` on mismatch.

**Acceptance criteria:**
- `POST /api/admin/services/{id}/start` without the header returns 403.
- `POST /api/admin/services/{id}/start` with a matching header proceeds to the
  handler.
- Unit test covers both cases.

---

## Task 1.04 — Login / Logout Endpoints

Implement the admin login flow.

**Deliverables:**
- `POST /api/admin/login` — accepts `{"username": "admin", "password": "..."}`,
  validates against the `cafebox-admin` system account (use PAM or compare
  against the hashed password file from first-boot), issues session cookie.
- `POST /api/admin/logout` — clears session cookie.
- `admin/backend/auth.py` — password verification helper.

**Acceptance criteria:**
- Correct credentials → 200 + session cookie set.
- Wrong credentials → 401.
- Logout clears the session cookie.

---

## Task 1.05 — `cafebox-admin` System User + Sudoers

Create the minimal privilege setup for the admin backend process:
- `cafebox-admin` system user (no login shell, no home directory).
- Sudoers file that allows `cafebox-admin` to run only the required
  `systemctl start/stop/restart` commands for CafeBox services — nothing else.

**Deliverables:**
- `system/templates/sudoers-cafebox.j2` rendered to `/etc/sudoers.d/cafebox`
- Section in `install.sh` that creates the user and installs the sudoers file.

**Acceptance criteria:**
- `visudo -c -f system/generated/sudoers-cafebox` passes.
- Template only grants `systemctl` actions on the specific CafeBox service units,
  not blanket sudo.

---

## Task 1.06 — Public API: `GET /api/public/services/status`

Implement the unauthenticated endpoint consumed by the portal landing page.

Response shape:
```json
{
  "first_boot": true,
  "services": [
    {"id": "chat", "name": "Matrix Chat", "enabled": true, "url": "http://chat.cafe.box"},
    ...
  ]
}
```

**Deliverables:**
- `admin/backend/routers/public.py` with the `/api/public/services/status` route.
- Reads enabled/disabled state from `cafe.yaml` and live `systemctl is-active`
  status.
- `first_boot` is `true` when `/run/cafebox/initial-password` exists.

**Acceptance criteria:**
- Response is valid JSON matching the documented shape.
- Disabled services still appear in the list with `"enabled": false`.
- Does not require authentication.

---

## Task 1.07 — Admin API: Service Start / Stop

Implement authenticated endpoints for service management.

**Deliverables:**
- `POST /api/admin/services/{service_id}/start`
- `POST /api/admin/services/{service_id}/stop`
- `POST /api/admin/services/{service_id}/restart`
- All require valid session + CSRF token.
- Use `subprocess` to run `sudo systemctl <action> <unit>` via the sudoers rule
  from Task 1.05.
- Map `service_id` (tile id) → systemd unit name using the Service Identity Map
  from `PLAN.md`.

**Acceptance criteria:**
- Unknown `service_id` returns 404.
- `systemctl` failure returns 500 with stderr in the response body (for admin
  debugging).
- No shell injection: use a list argument, not a shell string.

---

## Task 1.08 — Admin API: Password Change

Allow the operator to change their admin password.

**Deliverables:**
- `POST /api/admin/auth/change-password`
  - Body: `{"current_password": "...", "new_password": "..."}`
  - Validates current password before updating.
  - Enforces a minimum password length of 12 characters (return 422 otherwise).
  - Updates the system account password (`chpasswd` via subprocess).
  - Deletes `/run/cafebox/initial-password` if it exists (clears the banner).
- Requires session + CSRF token.

**Acceptance criteria:**
- Wrong current password → 403.
- New password shorter than 12 characters → 422 with clear message.
- After successful change, `/api/public/services/status` returns `first_boot: false`.

---

## Task 1.09 — Admin Frontend: Login Page

Build a minimal login page for the admin UI.

**Deliverables:**
- `admin/frontend/login.html` — username/password form, no JS framework, no CDN.
- Submits `POST /api/admin/login` via `fetch`, redirects to dashboard on success,
  shows error message on failure.
- Reads and sends the CSRF token from cookie on form submit.

**Acceptance criteria:**
- Page works in a modern browser with JavaScript enabled.
- No external resources loaded (fully offline-capable).
- Form is accessible: labels are associated with inputs.

---

## Task 1.10 — Admin Frontend: Dashboard — Service Tiles

Build the main admin dashboard page.

**Deliverables:**
- `admin/frontend/dashboard.html` — fetches service list from
  `/api/public/services/status`, renders a tile for each service showing:
  - Service name
  - Current status (running / stopped)
  - Start / Stop / Restart buttons (calls admin API with CSRF header)
- Logout button that calls `POST /api/admin/logout`.

**Acceptance criteria:**
- Service tiles update without a full page reload after a start/stop action.
- Buttons are disabled while an action is in progress.
- No external resources loaded.

---

## Task 1.11 — Admin Frontend: File Upload UI

Build the content upload section of the dashboard (or a separate page) for
uploading Kiwix ZIM files, Calibre content, and music.

**Deliverables:**
- `admin/frontend/upload.html` (or section in `dashboard.html`)
- `POST /api/admin/upload/{service_id}` backend endpoint that:
  - Streams the uploaded file to the correct storage path (from `cafe.yaml`
    `storage.locations`).
  - Validates that the file extension is appropriate for the service.
  - Returns progress information.

**Acceptance criteria:**
- Upload succeeds for a small test file.
- Uploading to an unknown `service_id` returns 404.
- File extension validation rejects `.exe` with a clear error.

---

## Task 1.12 — nginx Routing for Admin and API Paths

Update the nginx configuration template to route admin and API traffic:
- `/api/` → admin backend (uvicorn, port 8000).
- `/admin/` → admin frontend static files.
- All other paths → portal.
- Admin and API paths must NOT be referenced or linked from the portal (`portal/index.html`).

**Deliverables:**
- Updated `system/templates/nginx.conf.j2` with `location` blocks for the above.

**Acceptance criteria:**
- Rendered config passes `nginx -t`.
- `curl http://cafe.box/api/public/services/status` succeeds.
- `curl http://cafe.box/api/admin/services/chat/start` without session returns 401.
- Portal HTML does not contain any link to `/admin/`.
