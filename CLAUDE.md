# Hearth

A self-contained offline community server for Raspberry Pi Zero 2 W. Broadcasts a WiFi hotspot and serves content through a landing page. Each service is an independent systemd unit routed through nginx.

## Common Commands

### Testing

```bash
# Create venv (first time — python3.12-venv apt package may not be available,
# so bootstrap pip manually if needed)
python3 -m venv --without-pip .venv
curl -sS https://bootstrap.pypa.io/get-pip.py | .venv/bin/python3

# Install test dependencies (first time)
.venv/bin/pip install pytest pyyaml jinja2 aiofiles mutagen pillow
.venv/bin/pip install -r ansible/roles/admin/files/backend/requirements.txt

# Activate (optional, or prefix commands with .venv/bin/)
source .venv/bin/activate

# Run full test suite
python3 -m pytest tests/ -v

# Run a single test file
python3 -m pytest tests/test_eink.py -v
```

### Development VM

```bash
vagrant up                                      # Start dev VM
vagrant halt                                    # Stop dev VM
vagrant ssh                                     # Shell into VM
vagrant destroy -f                              # Delete VM
vagrant ssh -c "journalctl -f -u 'hearth-*'"  # Tail service logs
```

### Build

```bash
bash scripts/build-image.sh                     # Build flashable .img.xz
sudo bash scripts/inject-content.sh /dev/mmcblk0  # Inject ZIMs/music onto SD
```

## Architecture

- `hearth.yaml` — single operator config file; all system configs are generated from it by Ansible
- `ansible/roles/` — one role per service; roles must be self-contained (no cross-role variable deps)
- `ansible/roles/common/` — host-level prerequisites shared across services
- `tests/` — pytest suite; runs without a VM (structural + unit), see `TESTING.md`
- Services are reverse-proxied through nginx on port 80

See `ARCHITECTURE.md` for role boundaries and dependency ownership decisions.
See `TESTING.md` for full testing strategy and Python venv standards.

---

## Code Exploration Policy

Always use jCodemunch-MCP tools for code navigation. Never fall back to Read, Grep, Glob, or Bash for code exploration.

**Start any session:**
1. `resolve_repo { "path": "." }` — confirm the project is indexed. If not: `index_folder { "path": "." }`
2. `suggest_queries` — when the repo is unfamiliar

**Finding code:**
- symbol by name → `search_symbols` (add `kind=`, `language=`, `file_pattern=` to narrow)
- string, comment, config value → `search_text` (supports regex, `context_lines`)
- database columns (dbt/SQLMesh) → `search_columns`

**Reading code:**
- before opening any file → `get_file_outline` first
- one or more symbols → `get_symbol_source` (single ID → flat object; array → batch)
- symbol + its imports → `get_context_bundle`
- specific line range only → `get_file_content` (last resort)

**Repo structure:**
- `get_repo_outline` → dirs, languages, symbol counts
- `get_file_tree` → file layout, filter with `path_prefix`

**Relationships & impact:**
- what imports this file → `find_importers`
- where is this name used → `find_references`
- is this dead code → `check_references`
- file dependency graph → `get_dependency_graph`
- what breaks if I change X → `get_blast_radius`
- class hierarchy → `get_class_hierarchy`
- related symbols → `get_related_symbols`
- diff two snapshots → `get_symbol_diff`

**After editing a file:** `index_file { "path": "/abs/path/to/file" }` to keep the index fresh.