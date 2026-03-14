#!/usr/bin/env bash
# scripts/build-vm-disk.sh — DEPRECATED
#
# This script is no longer used.  The CafeBox development environment now
# uses Docker + ptrsr/pi-ci instead of a QEMU VM disk image.
#
# Run 'make vm-build' to pull the pi-ci Docker image, or 'make vm-start' to
# start the Pi emulator directly (the image is pulled automatically).
echo "ERROR: build-vm-disk.sh is deprecated." >&2
echo "       Use 'make vm-build' (docker pull ptrsr/pi-ci) instead." >&2
exit 1
