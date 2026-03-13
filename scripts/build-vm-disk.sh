#!/usr/bin/env bash
# scripts/build-vm-disk.sh — Download and prepare the development VM disk image
#
# Downloads Raspberry Pi OS Lite 64-bit and converts it to a qcow2 image
# ready for use by scripts/vm.sh.
#
# Configurable environment variables (with defaults):
#   VM_DISK      Destination qcow2 path  (default: vm/cafebox-dev.qcow2)
#   VM_PASSWORD  Password for the default 'pi' user (default: admin)
#   RPIOS_URL    Download URL for the image archive
#                (default: https://downloads.raspberrypi.com/raspios_lite_arm64_latest)
#   RPIOS_CACHE  Directory used to cache the downloaded .img.xz archive so that
#                subsequent builds skip the large download  (default: vm/rpios-cache)
#
# Prerequisites: curl, xz, qemu-img, mcopy (mtools), openssl

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

VM_DISK="${VM_DISK:-vm/cafebox-dev.qcow2}"
RPIOS_URL="${RPIOS_URL:-https://downloads.raspberrypi.com/raspios_lite_arm64_latest}"
RPIOS_CACHE="${RPIOS_CACHE:-vm/rpios-cache}"

# Resolve VM_DISK relative to the repo root when not an absolute path
if [[ "$VM_DISK" != /* ]]; then
    VM_DISK="$REPO_ROOT/$VM_DISK"
fi

# Resolve RPIOS_CACHE relative to the repo root when not an absolute path
if [[ "$RPIOS_CACHE" != /* ]]; then
    RPIOS_CACHE="$REPO_ROOT/$RPIOS_CACHE"
fi

VM_DIR="$(dirname "$VM_DISK")"
mkdir -p "$VM_DIR"
mkdir -p "$RPIOS_CACHE"

# Verify required tools are present, with install hints
declare -A TOOL_HINTS=(
    [curl]="sudo apt install curl"
    [xz]="sudo apt install xz-utils"
    [qemu-img]="sudo apt install qemu-utils"
    [mcopy]="sudo apt install mtools"
    [openssl]="sudo apt install openssl"
)
for tool in curl xz qemu-img mcopy openssl; do
    if ! command -v "$tool" &>/dev/null; then
        echo "ERROR: Required tool not found: $tool" >&2
        echo "       Install it with: ${TOOL_HINTS[$tool]}" >&2
        exit 1
    fi
done

TMP_DIR="$(mktemp -d)"
cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT

CACHED_ARCHIVE="$RPIOS_CACHE/rpios.img.xz"
if [[ -f "$CACHED_ARCHIVE" ]]; then
    echo "==> Using cached Raspberry Pi OS archive: $CACHED_ARCHIVE"
    echo "    (Delete it to force a fresh download)"
    cp "$CACHED_ARCHIVE" "$TMP_DIR/rpios.img.xz"
else
    echo "==> Downloading Raspberry Pi OS Lite 64-bit..."
    echo "    URL: $RPIOS_URL"
    curl -L --progress-bar -o "$TMP_DIR/rpios.img.xz" "$RPIOS_URL"
    echo "==> Caching archive for future builds: $CACHED_ARCHIVE"
    cp "$TMP_DIR/rpios.img.xz" "$CACHED_ARCHIVE"
fi

echo "==> Decompressing image..."
xz --decompress "$TMP_DIR/rpios.img.xz"

shopt -s nullglob
imgs=("$TMP_DIR"/*.img)
if [ "${#imgs[@]}" -eq 0 ]; then
    echo "ERROR: No .img file found after decompression." >&2
    exit 1
fi
IMG_FILE="${imgs[0]}"

echo "==> Enabling SSH on first boot..."
# Raspberry Pi OS disables SSH by default.  Placing an empty 'ssh' file in the
# FAT32 boot partition tells the OS to start the SSH daemon on first boot.
BOOT_START=$(sfdisk -d "$IMG_FILE" 2>/dev/null \
    | awk -F'start=' '/start=/{gsub(/,.*/, "", $2); print $2+0; exit}')
if [[ -z "$BOOT_START" || "$BOOT_START" -eq 0 ]]; then
    echo "ERROR: Could not determine boot partition offset from image: $IMG_FILE" >&2
    echo "       Ensure sfdisk is installed and the image has a valid partition table." >&2
    exit 1
fi
BOOT_OFFSET_BYTES=$(( BOOT_START * 512 ))
touch "$TMP_DIR/ssh"
if ! MTOOLS_SKIP_CHECK=1 mcopy -i "$IMG_FILE@@${BOOT_OFFSET_BYTES}" "$TMP_DIR/ssh" ::/ssh; then
    echo "ERROR: Failed to write ssh file into the boot partition." >&2
    echo "       Check that mtools is installed (sudo apt install mtools) and the image is valid." >&2
    exit 1
fi

echo "==> Creating default user (pi) via userconf.txt..."
# Raspberry Pi OS 12+ requires a userconf.txt in the boot partition to
# create the initial user on first boot.  The file must contain a single
# line in the form  username:hashed_password  where the hash is a standard
# SHA-512 crypt hash produced by openssl passwd.
# Override VM_PASSWORD to change the default password.
VM_PASSWORD="${VM_PASSWORD:-admin}"
HASHED_PW="$(openssl passwd -6 "$VM_PASSWORD")"
printf 'pi:%s\n' "$HASHED_PW" > "$TMP_DIR/userconf.txt"
if ! MTOOLS_SKIP_CHECK=1 mcopy -i "$IMG_FILE@@${BOOT_OFFSET_BYTES}" "$TMP_DIR/userconf.txt" ::/userconf.txt; then
    echo "ERROR: Failed to write userconf.txt into the boot partition." >&2
    echo "       Check that mtools is installed (sudo apt install mtools) and the image is valid." >&2
    exit 1
fi

echo "==> Converting to qcow2: $VM_DISK"
qemu-img convert -f raw -O qcow2 "$IMG_FILE" "$VM_DISK"

echo "==> Expanding image to 16G..."
qemu-img resize "$VM_DISK" 16G

echo ""
echo "VM disk image ready: $VM_DISK (16G)"
echo "Run 'make vm-start' to boot the VM."
