# Makefile — CafeBox developer shortcuts
#
# Prerequisites:
#   scripts/vm.sh   — for vm-* targets
#   scripts/config.py + scripts/generate-configs.py — for generate-configs
#   install.sh      — for the install target

# Default disk path — overridable via environment or make variable: VM_DISK=path/to/disk.qcow2
VM_DISK ?= vm/cafebox-dev.qcow2

.PHONY: help vm-build vm-start vm-stop vm-ssh install logs generate-configs test

# Default target: print help
help:
	@echo "CafeBox developer shortcuts"
	@echo ""
	@echo "  make vm-build         Download RPi OS Lite 64-bit and create vm/cafebox-dev.qcow2"
	@echo "  make vm-start         Start the development VM (builds disk first if missing)"
	@echo "  make vm-stop          Stop the development VM"
	@echo "  make vm-ssh           Open an SSH session into the development VM"
	@echo "  make install          Run install.sh inside the VM (or locally)"
	@echo "  make logs             Tail journald logs for all cafebox services"
	@echo "  make generate-configs Render all Jinja2 templates from cafe.yaml"
	@echo "  make test             Run the test suite (tests/)"

vm-build:
	@test -f scripts/build-vm-disk.sh || { echo "ERROR: scripts/build-vm-disk.sh not found."; exit 1; }
	VM_DISK="$(VM_DISK)" bash scripts/build-vm-disk.sh

vm-start:
	@test -f scripts/vm.sh || { echo "ERROR: scripts/vm.sh not found."; exit 1; }
	@test -f "$(VM_DISK)" || $(MAKE) vm-build VM_DISK="$(VM_DISK)"
	VM_DISK="$(VM_DISK)" bash scripts/vm.sh start

vm-stop:
	@test -f scripts/vm.sh || { echo "ERROR: scripts/vm.sh not found."; exit 1; }
	bash scripts/vm.sh stop

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
