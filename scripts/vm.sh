#!/usr/bin/env bash
# scripts/vm.sh — QEMU/libvirt development VM lifecycle management
#
# Sub-commands:
#   start        Boot the development VM
#   stop         Shut down the development VM
#   ssh          Open an interactive SSH session into the VM
#   mount-share  Mount the repository into the VM via 9p/virtfs
#   status       Print detailed VM status (process, disk, SSH reachability)
#   delete       Stop the VM (if running) and remove the disk image
#
# Configurable environment variables (with defaults):
#   VM_DISK      Path to the VM disk image  (default: vm/cafebox-dev.qcow2)
#   VM_SSH_PORT  Host port forwarded to VM SSH (default: 2222)

set -euo pipefail

VM_DISK="${VM_DISK:-vm/cafebox-dev.qcow2}"
VM_SSH_PORT="${VM_SSH_PORT:-2222}"
VM_PID_FILE="/tmp/cafebox-vm.pid"
VM_NAME="cafebox-dev"

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

_vm_is_running() {
    if [ -f "$VM_PID_FILE" ]; then
        local pid
        pid="$(cat "$VM_PID_FILE")"
        if kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
        rm -f "$VM_PID_FILE"
    fi
    return 1
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
    echo "         The VM may still be completing first-boot setup." >&2
    return 1
}

cmd_status() {
    local state pid_info disk_info ssh_info

    if _vm_is_running; then
        local pid
        pid="$(cat "$VM_PID_FILE")"
        state="running"
        pid_info="(pid=$pid)"
    else
        state="stopped"
        pid_info=""
    fi

    if [ -f "$VM_DISK" ]; then
        disk_info="$VM_DISK (exists)"
    else
        disk_info="$VM_DISK (not found — run 'make vm-build')"
    fi

    # Check whether the SSH port is accepting TCP connections.
    # Uses only bash builtins (/dev/tcp); no external tools required.
    if [ "$state" = "running" ]; then
        if (echo >/dev/tcp/127.0.0.1/"$VM_SSH_PORT") 2>/dev/null; then
            ssh_info="port $VM_SSH_PORT — reachable (VM has booted)"
        else
            ssh_info="port $VM_SSH_PORT — not yet reachable (VM may still be booting)"
        fi
    else
        ssh_info="port $VM_SSH_PORT — not checked (VM is stopped)"
    fi

    echo "VM status: $state $pid_info"
    echo "  disk:    $disk_info"
    echo "  ssh:     $ssh_info"
}

cmd_start() {
    _require_cmd qemu-system-aarch64 \
        "Install QEMU ARM emulation (provides qemu-system-aarch64): sudo apt install qemu-system-arm qemu-efi-aarch64"
    if _vm_is_running; then
        echo "INFO: VM is already running."
        return 0
    fi
    if [ ! -f "$VM_DISK" ]; then
        echo "ERROR: VM disk image not found: $VM_DISK" >&2
        echo "       Run 'make vm-build' to download and create it." >&2
        exit 1
    fi
    # raspi3b is natively supported by qemu-system-aarch64 and includes the
    # Raspberry Pi firmware, so the RPi OS bootloader chain works without any
    # direct-kernel-boot workarounds.
    VM_MACHINE="${VM_MACHINE:-raspi3b}"
    VM_CPU="${VM_CPU:-cortex-a53}"
    echo "Starting development VM (disk=$VM_DISK, ssh-port=$VM_SSH_PORT)…"
    qemu-system-aarch64 \
        -machine "$VM_MACHINE" \
        -cpu "$VM_CPU" \
        -m 1024 \
        -display none \
        -drive "file=$VM_DISK,format=qcow2,if=sd" \
        -netdev "user,id=net0,hostfwd=tcp::${VM_SSH_PORT}-:22" \
        -device virtio-net-device,netdev=net0 \
        -daemonize \
        -pidfile "$VM_PID_FILE"
    echo "VM started. Use 'make vm-ssh' to connect (first boot may take a few minutes)."
}

cmd_stop() {
    if ! _vm_is_running; then
        echo "INFO: VM is not running."
        return 0
    fi
    local pid
    pid="$(cat "$VM_PID_FILE")"
    echo "Stopping VM (pid=$pid)…"
    kill "$pid"
    rm -f "$VM_PID_FILE"
    echo "VM stopped."
}

cmd_ssh() {
    if ! _vm_is_running; then
        echo "ERROR: VM is not running. Start it first with: $0 start" >&2
        exit 1
    fi
    # Wait until sshd is accepting connections (first boot can take several
    # minutes for key generation and first-run setup).  _wait_for_ssh is a
    # no-op if ssh-keyscan is unavailable.
    _wait_for_ssh || true
    # StrictHostKeyChecking is disabled for development convenience: the VM
    # is ephemeral and its host key changes on every rebuild.  Do NOT use
    # these flags against production or untrusted hosts.
    ssh -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null \
        -p "$VM_SSH_PORT" \
        pi@127.0.0.1 "$@"
}

cmd_mount_share() {
    if ! _vm_is_running; then
        echo "ERROR: VM is not running. Start it first with: $0 start" >&2
        exit 1
    fi
    echo "Mounting host repository share inside VM…"
    cmd_ssh -- \
        "sudo mkdir -p /mnt/cafebox && \
         sudo mount -t 9p -o trans=virtio cafebox /mnt/cafebox && \
         echo 'Mounted at /mnt/cafebox'"
}

cmd_delete() {
    if _vm_is_running; then
        echo "VM is running — stopping it before deleting the disk…"
        cmd_stop
    fi
    if [ ! -f "$VM_DISK" ]; then
        echo "INFO: VM disk image not found (nothing to delete): $VM_DISK"
        return 0
    fi
    rm -f "$VM_DISK"
    echo "Deleted VM disk image: $VM_DISK"
    echo "Run 'make vm-build' (or 'make vm-start') to create a fresh image."
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
