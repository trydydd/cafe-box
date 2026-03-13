"""
generate-configs.py — CafeBox Jinja2 template renderer

Reads cafe.yaml (via config.py) and renders every *.j2 template found in
system/templates/ into system/generated/, preserving the base filename
(e.g. nginx.conf.j2 → system/generated/nginx.conf).

Usage:
    python scripts/generate-configs.py [--config path/to/cafe.yaml]

Running the script twice (idempotent): files are only written when their
content changes.
"""

import argparse
import os
import sys

# Allow "python scripts/generate-configs.py" from the repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from config import load_config, ConfigError

try:
    from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateError
except ImportError:
    print(
        "ERROR: jinja2 is not installed. Run: pip install jinja2",
        file=sys.stderr,
    )
    sys.exit(1)


TEMPLATES_DIR = os.path.join(
    os.path.dirname(__file__), "..", "system", "templates"
)
OUTPUT_DIR = os.path.join(
    os.path.dirname(__file__), "..", "system", "generated"
)


def render_templates(config: dict, templates_dir: str, output_dir: str) -> list[str]:
    """Render all *.j2 templates from *templates_dir* into *output_dir*.

    Unknown template variables raise a :class:`jinja2.UndefinedError` (via
    ``StrictUndefined``) rather than silently expanding to an empty string.

    Returns a list of output file paths that were written (new or changed).
    """
    env = Environment(
        loader=FileSystemLoader(templates_dir),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )

    os.makedirs(output_dir, exist_ok=True)

    written = []
    templates = sorted(
        t for t in env.list_templates() if t.endswith(".j2")
    )

    if not templates:
        print(f"No *.j2 templates found in '{templates_dir}'.")
        return written

    for template_name in templates:
        output_name = template_name[:-3]  # strip .j2
        output_path = os.path.join(output_dir, output_name)

        try:
            tmpl = env.get_template(template_name)
            rendered = tmpl.render(**config)
        except TemplateError as exc:
            print(
                f"ERROR rendering '{template_name}': {exc}",
                file=sys.stderr,
            )
            sys.exit(1)

        # Only write if content changed (idempotent)
        existing = None
        if os.path.exists(output_path):
            with open(output_path, "r") as fh:
                existing = fh.read()

        if rendered != existing:
            with open(output_path, "w") as fh:
                fh.write(rendered)
            written.append(output_path)
            print(f"  Written:   {output_path}")
        else:
            print(f"  Unchanged: {output_path}")

    return written


def main():
    parser = argparse.ArgumentParser(
        description="Render Jinja2 templates from cafe.yaml"
    )
    parser.add_argument(
        "--config",
        default="cafe.yaml",
        metavar="PATH",
        help="Path to cafe.yaml (default: cafe.yaml)",
    )
    args = parser.parse_args()

    try:
        config = load_config(args.config)
    except (ConfigError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    templates_dir = os.path.abspath(TEMPLATES_DIR)
    output_dir = os.path.abspath(OUTPUT_DIR)

    print(f"Templates : {templates_dir}")
    print(f"Output    : {output_dir}")
    print()

    render_templates(config, templates_dir, output_dir)


if __name__ == "__main__":
    main()
