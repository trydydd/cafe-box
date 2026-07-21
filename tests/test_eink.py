import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

import jinja2
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_ROOT = REPO_ROOT / "ansible" / "roles" / "eink"
TEMPLATE_PATH = ROLE_ROOT / "templates" / "hearth-eink.py.j2"

_TEST_BOX = {"name": "TestBox", "domain": "test.local"}
_TEST_ICON = "/opt/hearth/eink/fireplace.svg"


def _render_template(box=_TEST_BOX, eink_icon=_TEST_ICON):
    src = TEMPLATE_PATH.read_text()
    env = jinja2.Environment(undefined=jinja2.StrictUndefined)
    return env.from_string(src).render(box=box, eink_icon=eink_icon)


# ---------------------------------------------------------------------------
# Structure — filesystem + YAML validity
# ---------------------------------------------------------------------------
class TestEinkRoleStructure(unittest.TestCase):

    def test_role_directory_exists(self):
        self.assertTrue(ROLE_ROOT.is_dir(), f"Missing role directory: {ROLE_ROOT}")

    def test_required_files_present(self):
        expected = [
            "meta/main.yml",
            "defaults/main.yml",
            "tasks/main.yml",
            "handlers/main.yml",
            "templates/hearth-eink.py.j2",
            "templates/hearth-eink.service.j2",
        ]
        for rel in expected:
            with self.subTest(file=rel):
                self.assertTrue((ROLE_ROOT / rel).exists(), f"Missing: {rel}")

    def test_yaml_files_parse(self):
        for yml in ROLE_ROOT.rglob("*.yml"):
            with self.subTest(file=yml.relative_to(REPO_ROOT)):
                try:
                    yaml.safe_load(yml.read_text())
                except yaml.YAMLError as exc:
                    self.fail(f"YAML parse error in {yml}: {exc}")


# ---------------------------------------------------------------------------
# Template rendering — Jinja2 → valid Python with correct values injected
# ---------------------------------------------------------------------------
class TestEinkTemplateRender(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.rendered = _render_template()

    def test_template_renders_valid_python(self):
        try:
            compile(self.rendered, "<hearth-eink.py.j2>", "exec")
        except SyntaxError as exc:
            self.fail(f"Rendered template is not valid Python: {exc}")

    def test_display_url_injected(self):
        self.assertIn('DISPLAY_URL  = "test.local"', self.rendered)

    def test_icon_path_injected(self):
        self.assertIn('ICON_PATH    = "/opt/hearth/eink/fireplace.svg"', self.rendered)


# ---------------------------------------------------------------------------
# Display logic — _build_canvas() and main() with mocked hardware libs
# ---------------------------------------------------------------------------
class TestEinkDisplayLogic(unittest.TestCase):
    """
    RPi.GPIO, spidev, and cairosvg are not installable in CI (require Pi
    hardware / native libs).  We inject MagicMock stubs into sys.modules
    before loading the rendered script so that their imports resolve without
    error.  cairosvg.svg2png is configured to return a minimal but valid PNG
    so that PIL can open it inside _build_canvas().
    """

    @classmethod
    def setUpClass(cls):
        import io as _io
        from PIL import Image as _Image

        # Minimal 66×66 white RGBA PNG returned by the mocked cairosvg
        buf = _io.BytesIO()
        _Image.new("RGBA", (66, 66), (255, 255, 255, 255)).save(buf, "PNG")
        cls._dummy_png = buf.getvalue()

        # Write rendered script to a temp file (importlib needs a real path)
        cls._tmp = Path(tempfile.mktemp(suffix="_hearth_eink_test.py"))
        cls._tmp.write_text(_render_template())

        # Stub hardware/platform deps before import
        cls._mock_gpio = MagicMock()
        cls._mock_spidev = MagicMock()
        cls._mock_cairosvg = MagicMock()
        cls._mock_cairosvg.svg2png.return_value = cls._dummy_png
        sys.modules.setdefault("RPi", MagicMock())
        sys.modules.setdefault("RPi.GPIO", cls._mock_gpio)
        sys.modules.setdefault("spidev", cls._mock_spidev)
        sys.modules.setdefault("cairosvg", cls._mock_cairosvg)

        # Load the rendered script as a module
        spec = importlib.util.spec_from_file_location("_hearth_eink_test", cls._tmp)
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.unlink(missing_ok=True)
        for key in ("RPi", "RPi.GPIO", "spidev", "cairosvg"):
            sys.modules.pop(key, None)

    # --- _build_canvas() ---

    def test_build_canvas_returns_pil_image(self):
        from PIL import Image
        result = self.mod._build_canvas()
        self.assertIsInstance(result, Image.Image)

    def test_build_canvas_dimensions(self):
        result = self.mod._build_canvas()
        self.assertEqual(result.size, (250, 122))

    # --- _blank_white_buffer() ---

    def test_blank_white_buffer_is_all_white(self):
        buf = self.mod._blank_white_buffer()
        self.assertIsInstance(buf, list)
        self.assertTrue(all(b == 0xFF for b in buf))

    # --- main() graceful degradation ---

    def test_main_skips_gracefully_on_hardware_error(self):
        """_init_gpio_spi() raises Exception (no hardware) → sys.exit(0)."""
        orig = self.mod._init_gpio_spi
        self.mod._init_gpio_spi = MagicMock(side_effect=Exception("no hardware"))
        try:
            with self.assertRaises(SystemExit) as cm:
                self.mod.main()
            self.assertEqual(cm.exception.code, 0)
        finally:
            self.mod._init_gpio_spi = orig

    def test_main_skips_gracefully_on_import_error(self):
        """RPi.GPIO not importable (removed from sys.modules) → sys.exit(0)."""
        saved_rpi = sys.modules.pop("RPi", None)
        saved_gpio = sys.modules.pop("RPi.GPIO", None)
        saved_csv = sys.modules.pop("cairosvg", None)
        try:
            with self.assertRaises(SystemExit) as cm:
                self.mod.main()
            self.assertEqual(cm.exception.code, 0)
        finally:
            if saved_rpi is not None:
                sys.modules["RPi"] = saved_rpi
            if saved_gpio is not None:
                sys.modules["RPi.GPIO"] = saved_gpio
            if saved_csv is not None:
                sys.modules["cairosvg"] = saved_csv
