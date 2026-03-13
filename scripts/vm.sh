#!/usr/bin/env bash
# scripts/vm.sh — QEMU/libvirt development VM lifecycle management
#
# Sub-commands:
#   start        Boot the development VM
#   stop         Shut down the development VM
#   ssh          Open an interactive SSH session into the VM
#   mount-share  Mount the repository into the VM via 9p/virtfs
#   status       Print "running" or "stopped" and exit 0
#
# Configurable environment variables (with defaults):
#   VM_DISK      Path to the VM disk image  (default: vm/cafebox-dev.qcow2)
#   VM_SSH_PORT  Host port forwarded to VM SSH (default: 2222)

set -euo pipefail

VM_DISK="${VM_DISK:-vm/cafebox-dev.qcow2}"
VM_SSH_PORT="${VM_SSH_PORT:-2222}"
VM_PID_FILE="/tmp/cafebox-vm.pid"
VM_NAME="cafebox-dev"

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

cmd_status() {
    if _vm_is_running; then
        echo "running"
    else
        echo "stopped"
    fi
}

cmd_start() {
    if _vm_is_running; then
        echo "INFO: VM is already running."
        return 0
    fi
    if [ ! -f "$VM_DISK" ]; then
        echo "ERROR: VM disk image not found: $VM_DISK" >&2
        exit 1
    fi
    echo "Starting development VM (disk=$VM_DISK, ssh-port=$VM_SSH_PORT)…"
    # Architecture fixed at ARM64 to match the Raspberry Pi 3/4 target hardware.
    # Adjust VM_MACHINE / VM_CPU overrides if you need a different arch locally.
    VM_MACHINE="${VM_MACHINE:-virt}"
    VM_CPU="${VM_CPU:-cortex-a53}"
    qemu-system-aarch64 \
        -machine "$VM_MACHINE" \
        -cpu "$VM_CPU" \
        -m 1024 \
        -nographic \
        -drive "file=$VM_DISK,format=qcow2" \
        -netdev "user,id=net0,hostfwd=tcp::${VM_SSH_PORT}-:22" \
        -device virtio-net-pci,netdev=net0 \
        -daemonize \
        -pidfile "$VM_PID_FILE"
    echo "VM started. SSH available on port $VM_SSH_PORT."
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

usage() {
    echo "Usage: $0 {start|stop|ssh|mount-share|status}" >&2
    exit 1
}

case "${1:-}" in
    start)       cmd_start ;;
    stop)        cmd_stop ;;
    ssh)         shift; cmd_ssh "$@" ;;
    mount-share) cmd_mount_share ;;
    status)      cmd_status ;;
    *)           usage ;;
esac
