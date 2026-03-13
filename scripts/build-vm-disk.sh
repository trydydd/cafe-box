#!/usr/bin/env bash
# scripts/build-vm-disk.sh — Download and prepare the development VM disk image
#
# Downloads Raspberry Pi OS Lite 64-bit and converts it to a qcow2 image
# ready for use by scripts/vm.sh.
#
# Configurable environment variables (with defaults):
#   VM_DISK    Destination qcow2 path  (default: vm/cafebox-dev.qcow2)
#   RPIOS_URL  Download URL for the image archive
#              (default: https://downloads.raspberrypi.com/raspios_lite_arm64_latest)
#
# Prerequisites: curl, xz, qemu-img

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

VM_DISK="${VM_DISK:-vm/cafebox-dev.qcow2}"
RPIOS_URL="${RPIOS_URL:-https://downloads.raspberrypi.com/raspios_lite_arm64_latest}"

# Resolve VM_DISK relative to the repo root when not an absolute path
if [[ "$VM_DISK" != /* ]]; then
    VM_DISK="$REPO_ROOT/$VM_DISK"
fi

VM_DIR="$(dirname "$VM_DISK")"
mkdir -p "$VM_DIR"

# Verify required tools are present, with install hints
declare -A TOOL_HINTS=(
    [curl]="sudo apt install curl"
    [xz]="sudo apt install xz-utils"
    [qemu-img]="sudo apt install qemu-utils"
)
for tool in curl xz qemu-img; do
    if ! command -v "$tool" &>/dev/null; then
        echo "ERROR: Required tool not found: $tool" >&2
        echo "       Install it with: ${TOOL_HINTS[$tool]}" >&2
        exit 1
    fi
done

TMP_DIR="$(mktemp -d)"
cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT

echo "==> Downloading Raspberry Pi OS Lite 64-bit..."
echo "    URL: $RPIOS_URL"
curl -L --progress-bar -o "$TMP_DIR/rpios.img.xz" "$RPIOS_URL"

echo "==> Decompressing image..."
xz --decompress "$TMP_DIR/rpios.img.xz"

shopt -s nullglob
imgs=("$TMP_DIR"/*.img)
if [ "${#imgs[@]}" -eq 0 ]; then
    echo "ERROR: No .img file found after decompression." >&2
    exit 1
fi
IMG_FILE="${imgs[0]}"

echo "==> Converting to qcow2: $VM_DISK"
qemu-img convert -f raw -O qcow2 "$IMG_FILE" "$VM_DISK"

echo ""
echo "VM disk image ready: $VM_DISK"
echo "Run 'make vm-start' to boot the VM."
