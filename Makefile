# Makefile — CafeBox developer shortcuts
#
# Prerequisites:
#   scripts/vm.sh   — for vm-* targets
#   scripts/config.py + scripts/generate-configs.py — for generate-configs
#   install.sh      — for the install target

# Docker image used for the Pi emulator (ptrsr/pi-ci)
PI_CI_IMAGE ?= ptrsr/pi-ci
# Directory for persistent Pi emulator disk image (bind-mounted to /dist)
PI_DIST_DIR ?= pi/dist
# SSH port forwarded from the Pi emulator to the host
VM_SSH_PORT ?= 2222

.PHONY: help vm-build vm-start vm-stop vm-ssh vm-status vm-delete install logs generate-configs test

# Default target: print help
help:
	@echo "CafeBox developer shortcuts"
	@echo ""
	@echo "  make vm-build         Pull the ptrsr/pi-ci Docker image (Pi 3/4/5 + RPi OS Bookworm)"
	@echo "  make vm-start         Start the Pi emulator container (pulls image if missing)"
	@echo "  make vm-stop          Stop the Pi emulator container"
	@echo "  make vm-ssh           Open an SSH session into the Pi emulator"
	@echo "  make vm-status        Show Pi container state, dist dir, and SSH reachability"
	@echo "  make vm-delete        Stop the container (if running) and delete the dist directory"
	@echo "  make install          Run install.sh inside the Pi (or locally)"
	@echo "  make logs             Tail journald logs for all cafebox services"
	@echo "  make generate-configs Render all Jinja2 templates from cafe.yaml"
	@echo "  make test             Run the test suite (tests/)"

vm-build:
	@command -v docker >/dev/null 2>&1 || { echo "ERROR: Docker not found. Install from https://docs.docker.com/get-docker/"; exit 1; }
	docker pull $(PI_CI_IMAGE)

vm-start:
	@test -f scripts/vm.sh || { echo "ERROR: scripts/vm.sh not found."; exit 1; }
	PI_DIST_DIR="$(PI_DIST_DIR)" VM_SSH_PORT="$(VM_SSH_PORT)" PI_CI_IMAGE="$(PI_CI_IMAGE)" bash scripts/vm.sh start

vm-stop:
	@test -f scripts/vm.sh || { echo "ERROR: scripts/vm.sh not found."; exit 1; }
	bash scripts/vm.sh stop

vm-status:
	@test -f scripts/vm.sh || { echo "ERROR: scripts/vm.sh not found."; exit 1; }
	PI_DIST_DIR="$(PI_DIST_DIR)" VM_SSH_PORT="$(VM_SSH_PORT)" bash scripts/vm.sh status

vm-delete:
	@test -f scripts/vm.sh || { echo "ERROR: scripts/vm.sh not found."; exit 1; }
	PI_DIST_DIR="$(PI_DIST_DIR)" bash scripts/vm.sh delete

vm-ssh:
	@test -f scripts/vm.sh || { echo "ERROR: scripts/vm.sh not found."; exit 1; }
	bash scripts/vm.sh ssh

install:
	@test -f install.sh || { echo "ERROR: install.sh not found."; exit 1; }
	bash install.sh

logs:
	@test -f scripts/vm.sh || { echo "ERROR: scripts/vm.sh not found."; exit 1; }
	bash scripts/vm.sh ssh -- journalctl -f -u 'cafebox-*'

generate-configs:
	@test -f scripts/generate-configs.py || { echo "ERROR: scripts/generate-configs.py not found."; exit 1; }
	python scripts/generate-configs.py

test:
	python -m pytest tests/ -v
