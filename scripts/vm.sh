#!/usr/bin/env bash
# scripts/vm.sh — Docker-based Raspberry Pi development environment (ptrsr/pi-ci)
#
# Sub-commands:
#   start        Start the pi-ci container (pulls image automatically if missing)
#   stop         Stop the pi-ci container
#   ssh          Open an interactive SSH session into the Pi emulator
#   mount-share  Copy the repository into the running Pi container
#   status       Print Pi status (container, dist dir, SSH reachability)
#   delete       Stop the container (if running) and remove the dist directory
#
# Configurable environment variables (with defaults):
#   VM_SSH_PORT   Host port forwarded to Pi SSH (default: 2222)
#   PI_DIST_DIR   Directory bind-mounted to /dist in the container (default: pi/dist)
#   PI_CI_IMAGE   Docker image to use (default: ptrsr/pi-ci)
#   PI_CONTAINER  Docker container name (default: cafebox-pi)

set -euo pipefail

VM_SSH_PORT="${VM_SSH_PORT:-2222}"
PI_DIST_DIR="${PI_DIST_DIR:-pi/dist}"
PI_CI_IMAGE="${PI_CI_IMAGE:-ptrsr/pi-ci}"
PI_CONTAINER="${PI_CONTAINER:-cafebox-pi}"
VM_LOG_FILE="${VM_LOG_FILE:-/tmp/cafebox-vm.log}"

# Print an error and exit if a required command is not installed.
# The second argument is a human-readable install hint.
_require_cmd() {
    local cmd="$1" hint="$2"
    if ! command -v "$cmd" &>/dev/null; then
        echo "ERROR: Required command not found: $cmd" >&2
        echo "       $hint" >&2
        exit 1
    fi
}

# Return 0 if the pi-ci container is currently running, 1 otherwise.
# Handles the case where Docker is not installed gracefully.
_pi_is_running() {
    command -v docker &>/dev/null || return 1
    local status
    status="$(docker inspect -f '{{.State.Running}}' "$PI_CONTAINER" 2>/dev/null)" || return 1
    [ "$status" = "true" ]
}

# Poll for the SSH banner (sent immediately by a running sshd) and return 0
# once it is detected, or 1 after MAX_SSH_WAIT seconds (default 120).
# Uses ssh-keyscan so the check is both reliable and side-effect free.
_wait_for_ssh() {
    local max_wait="${MAX_SSH_WAIT:-120}"
    local interval=5
    local elapsed=0
    if ! command -v ssh-keyscan &>/dev/null; then
        # ssh-keyscan unavailable — skip the wait; let ssh fail normally.
        return 0
    fi
    printf "Waiting for SSH on port %s" "$VM_SSH_PORT"
    while (( elapsed < max_wait )); do
        if ssh-keyscan -T 3 -p "$VM_SSH_PORT" 127.0.0.1 >/dev/null 2>&1; then
            printf " ready (%ds).\n" "$elapsed"
            return 0
        fi
        sleep "$interval"
        elapsed=$(( elapsed + interval ))
        printf "."
    done
    printf "\n"
    echo "WARNING: SSH did not become available after ${max_wait}s." >&2
    echo "         The Pi may still be completing first-boot setup." >&2
    return 1
}

cmd_status() {
    local state dist_info ssh_info

    if _pi_is_running; then
        state="running"
    else
        state="stopped"
    fi

    if [ -d "$PI_DIST_DIR" ]; then
        dist_info="$PI_DIST_DIR (exists)"
    else
        dist_info="$PI_DIST_DIR (not found — run 'make vm-start')"
    fi

    # Check whether the SSH port is accepting TCP connections.
    # Uses only bash builtins (/dev/tcp); no external tools required.
    if [ "$state" = "running" ]; then
        if (echo >/dev/tcp/127.0.0.1/"$VM_SSH_PORT") 2>/dev/null; then
            ssh_info="port $VM_SSH_PORT — reachable (Pi has booted)"
        else
            ssh_info="port $VM_SSH_PORT — not yet reachable (Pi may still be booting)"
        fi
    else
        ssh_info="port $VM_SSH_PORT — not checked (Pi is stopped)"
    fi

    echo "Pi status: $state"
    echo "  dist:    $dist_info"
    echo "  ssh:     $ssh_info"
}

cmd_start() {
    _require_cmd docker \
        "Install Docker: https://docs.docker.com/get-docker/"
    if _pi_is_running; then
        echo "INFO: Pi container is already running."
        return 0
    fi
    # Create the dist directory before starting the container; pi-ci stores
    # the persistent qcow2 disk image here across container restarts.
    mkdir -p "$PI_DIST_DIR"
    local abs_dist
    abs_dist="$(cd "$PI_DIST_DIR" && pwd)"
    echo "Starting Pi emulator (dist=$PI_DIST_DIR, ssh-port=$VM_SSH_PORT)…"
    docker run \
        --rm \
        --detach \
        --name "$PI_CONTAINER" \
        -p "${VM_SSH_PORT}:2222" \
        -v "${abs_dist}:/dist" \
        "$PI_CI_IMAGE" start \
        2>"$VM_LOG_FILE"
    echo "Pi emulator started. Use 'make vm-ssh' to connect (first boot may take a few minutes)."
    echo "  Container logs: docker logs $PI_CONTAINER"
    echo "  Startup log:    $VM_LOG_FILE"
}

cmd_stop() {
    if ! _pi_is_running; then
        echo "INFO: Pi container is not running."
        return 0
    fi
    echo "Stopping Pi container ($PI_CONTAINER)…"
    docker stop "$PI_CONTAINER"
    echo "Pi container stopped."
}

cmd_ssh() {
    if ! _pi_is_running; then
        echo "ERROR: Pi container is not running. Start it first with: $0 start" >&2
        exit 1
    fi
    # Wait until sshd is accepting connections (first boot can take several
    # minutes for first-run setup).  _wait_for_ssh is a no-op if ssh-keyscan
    # is unavailable.
    _wait_for_ssh || true
    # StrictHostKeyChecking is disabled for development convenience: the Pi
    # emulator is ephemeral and its host key changes on every rebuild.  Do NOT
    # use these flags against production or untrusted hosts.
    ssh -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null \
        -p "$VM_SSH_PORT" \
        root@127.0.0.1 "$@"
}

cmd_mount_share() {
    if ! _pi_is_running; then
        echo "ERROR: Pi container is not running. Start it first with: $0 start" >&2
        exit 1
    fi
    local repo_root
    repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    echo "Copying repository into Pi container at /mnt/cafebox…"
    docker exec "$PI_CONTAINER" mkdir -p /mnt/cafebox
    docker cp "${repo_root}/." "${PI_CONTAINER}:/mnt/cafebox/"
    echo "Repository available at /mnt/cafebox inside the container."
}

cmd_delete() {
    if _pi_is_running; then
        echo "Pi container is running — stopping it first…"
        cmd_stop
    fi
    if [ ! -d "$PI_DIST_DIR" ]; then
        echo "INFO: Pi dist directory not found (nothing to delete): $PI_DIST_DIR"
        return 0
    fi
    rm -rf "$PI_DIST_DIR"
    echo "Deleted Pi dist directory: $PI_DIST_DIR"
    echo "Run 'make vm-start' to start a fresh Pi environment."
}

usage() {
    echo "Usage: $0 {start|stop|ssh|mount-share|status|delete}" >&2
    exit 1
}

case "${1:-}" in
    start)       cmd_start ;;
    stop)        cmd_stop ;;
    ssh)         shift; cmd_ssh "$@" ;;
    mount-share) cmd_mount_share ;;
    status)      cmd_status ;;
    delete)      cmd_delete ;;
    *)           usage ;;
esac
