"""
config.py — CafeBox configuration loader

Usage (standalone):
    python scripts/config.py [path/to/cafe.yaml]

Usage (as a module):
    from scripts.config import load_config
    cfg = load_config()
"""

import re
import sys
import yaml


REQUIRED_KEYS = [
    "box.name",
    "box.domain",
    "box.ip",
    "wifi.ssid",
    "wifi.interface",
    "storage.base",
    "services",
]


class ConfigError(Exception):
    """Raised when the configuration is missing a required key or fails validation."""


def _get_nested(data: dict, dotted_key: str):
    """Return the value at a dotted key path, or raise KeyError if absent."""
    keys = dotted_key.split(".")
    node = data
    for k in keys:
        if not isinstance(node, dict) or k not in node:
            raise KeyError(dotted_key)
        node = node[k]
    return node


def _validate_hostname(domain: str) -> bool:
    """Return True if *domain* looks like a valid hostname."""
    pattern = r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$"
    return bool(re.match(pattern, domain))


def load_config(path: str = "cafe.yaml") -> dict:
    """Load, validate, and return the configuration from *path*.

    Raises:
        FileNotFoundError: if *path* does not exist.
        ConfigError: if a required key is missing or a value fails validation.
    """
    with open(path, "r") as fh:
        data = yaml.safe_load(fh)

    if data is None:
        data = {}

    # Check required keys
    for key in REQUIRED_KEYS:
        try:
            _get_nested(data, key)
        except KeyError:
            raise ConfigError(f"Missing required configuration key: '{key}'")

    # Validate domain
    domain = data["box"]["domain"]
    if not _validate_hostname(domain):
        raise ConfigError(
            f"'box.domain' must be a valid hostname, got: {domain!r}"
        )

    return data


if __name__ == "__main__":
    config_path = sys.argv[1] if len(sys.argv) > 1 else "cafe.yaml"
    try:
        cfg = load_config(config_path)
        print(f"Configuration loaded successfully from '{config_path}':")
        print(yaml.dump(cfg, default_flow_style=False))
    except (ConfigError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
