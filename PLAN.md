# PLAN.md

## Stage 0.6 Landing Portal

The page queries the admin API (/api/public/services/status).

## Stage 0

### 0.1 OS Preparation

### 0.1a — Threat Model & Network Policy (Offline / Hostile Clients / Hotspot Only)

- no WAN; admin reachable only from hotspot interface; firewall default deny inbound except 80 on wlan0, plus DHCP/DNS; client isolation if feasible; block forwarding/NAT; and SSH disabled by default (or restricted to hotspot).

## nginx Captive Portal Template Snippet

Change the Android /generate_204 handler to return a redirect (302) to http://{{ box.domain }}/ instead of 204, with a short note explaining why.

## Stage 1

Clarify that SessionMiddleware uses signed cookies (not server-side tokens) unless a server-side session store is added;
add a short CSRF defense section requiring CSRF token on state-changing requests.

## Sudo Grants

Replace www-data with a dedicated cafebox-admin user; tighten sudoers entries; fix setup-symlinks.sh to setup-symlinks.py (or document a wrapper script if preferred, but make consistent with storage/setup-symlinks.py).

## Admin Systemd Service Example

Run as cafebox-admin rather than www-data.

## Service Identity Map

Add a 'Service Identity Map' table near Central Configuration that maps tile id, systemd unit, and storage key for chat/conduit/matrix and the other services, and state that APIs use tile ids but systemd/storage keys are mapped internally.
