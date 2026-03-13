# Makefile — CafeBox developer shortcuts
#
# Prerequisites:
#   scripts/vm.sh   — for vm-* targets
#   scripts/config.py + scripts/generate-configs.py — for generate-configs
#   install.sh      — for the install target

.PHONY: help vm-start vm-stop vm-ssh install logs generate-configs

# Default target: print help
help:
	@echo "CafeBox developer shortcuts"
	@echo ""
	@echo "  make vm-start         Start the development VM (QEMU/libvirt)"
	@echo "  make vm-stop          Stop the development VM"
	@echo "  make vm-ssh           Open an SSH session into the development VM"
	@echo "  make install          Run install.sh inside the VM (or locally)"
	@echo "  make logs             Tail journald logs for all cafebox services"
	@echo "  make generate-configs Render all Jinja2 templates from cafe.yaml"

vm-start:
	@test -f scripts/vm.sh || { echo "ERROR: scripts/vm.sh not found."; exit 1; }
	bash scripts/vm.sh start

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
