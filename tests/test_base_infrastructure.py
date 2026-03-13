import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


config_module = _load_module("cafebox_config", REPO_ROOT / "scripts" / "config.py")
generate_module = _load_module(
    "cafebox_generate_configs", REPO_ROOT / "scripts" / "generate-configs.py"
)


class TestRepositoryScaffolding(unittest.TestCase):
    def test_required_directories_exist(self):
        expected = [
            "scripts",
            "image",
            "system/templates",
            "system/generated",
            "storage",
            "services/conduit",
            "services/element-web",
            "services/calibre-web",
            "services/kiwix",
            "services/navidrome",
            "admin/backend",
            "admin/frontend",
            "portal",
        ]
        for rel in expected:
            with self.subTest(path=rel):
                self.assertTrue((REPO_ROOT / rel).is_dir(), f"Missing directory: {rel}")

    def test_required_files_exist(self):
        expected = [
            "cafe.yaml",
            "install.sh",
            "Makefile",
            "portal/index.html",
            "image/README.md",
        ]
        for rel in expected:
            with self.subTest(path=rel):
                self.assertTrue((REPO_ROOT / rel).is_file(), f"Missing file: {rel}")

    def test_portal_and_image_stubs_are_non_empty(self):
        portal_html = (REPO_ROOT / "portal" / "index.html").read_text()
        image_readme = (REPO_ROOT / "image" / "README.md").read_text()

        self.assertIn("<html", portal_html.lower())
        self.assertTrue(image_readme.strip(), "image/README.md should not be empty")


class TestSampleConfig(unittest.TestCase):
    def test_cafe_yaml_is_valid_yaml(self):
        data = yaml.safe_load((REPO_ROOT / "cafe.yaml").read_text())
        self.assertIsInstance(data, dict)

    def test_cafe_yaml_contains_required_top_level_sections(self):
        data = yaml.safe_load((REPO_ROOT / "cafe.yaml").read_text())
        for key in ["box", "wifi", "storage", "services"]:
            with self.subTest(key=key):
                self.assertIn(key, data)


class TestConfigLoader(unittest.TestCase):
    def test_load_config_returns_valid_mapping(self):
        config = config_module.load_config(str(REPO_ROOT / "cafe.yaml"))
        self.assertIsInstance(config, dict)
        self.assertIn("box", config)
        self.assertIn("domain", config["box"])

    def test_missing_required_key_raises_configerror(self):
        broken = {
            "box": {"name": "CafeBox", "ip": "10.0.0.1"},
            "wifi": {"ssid": "CafeBox", "interface": "wlan0"},
            "storage": {"base": "/srv/cafebox"},
            "services": {},
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.yaml"
            path.write_text(yaml.safe_dump(broken))
            with self.assertRaises(config_module.ConfigError) as ctx:
                config_module.load_config(str(path))
        self.assertIn("box.domain", str(ctx.exception))

    def test_invalid_hostname_raises_configerror(self):
        broken = {
            "box": {"name": "CafeBox", "domain": "not a hostname", "ip": "10.0.0.1"},
            "wifi": {"ssid": "CafeBox", "interface": "wlan0"},
            "storage": {"base": "/srv/cafebox"},
            "services": {},
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "invalid-domain.yaml"
            path.write_text(yaml.safe_dump(broken))
            with self.assertRaises(config_module.ConfigError) as ctx:
                config_module.load_config(str(path))
        self.assertIn("box.domain", str(ctx.exception))


class TestTemplateRenderer(unittest.TestCase):
    def test_generate_configs_script_renders_nginx(self):
        result = subprocess.run(
            [sys.executable, "scripts/generate-configs.py", "--config", "cafe.yaml"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertTrue((REPO_ROOT / "system" / "generated" / "nginx.conf").is_file())

    def test_generate_configs_is_idempotent(self):
        first = subprocess.run(
            [sys.executable, "scripts/generate-configs.py", "--config", "cafe.yaml"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        second = subprocess.run(
            [sys.executable, "scripts/generate-configs.py", "--config", "cafe.yaml"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(first.returncode, 0, msg=first.stderr)
        self.assertEqual(second.returncode, 0, msg=second.stderr)
        self.assertIn("Unchanged:", second.stdout)

    def test_unknown_template_variable_exits_with_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            templates_dir = Path(tmp) / "templates"
            output_dir = Path(tmp) / "output"
            templates_dir.mkdir(parents=True, exist_ok=True)
            (templates_dir / "broken.conf.j2").write_text("value={{ missing_key }}\n")

            with self.assertRaises(SystemExit) as ctx:
                generate_module.render_templates(
                    {"box": {"domain": "cafe.box"}},
                    str(templates_dir),
                    str(output_dir),
                )
            self.assertEqual(ctx.exception.code, 1)


class TestMakefileTargets(unittest.TestCase):
    def test_help_lists_expected_targets(self):
        result = subprocess.run(
            ["make", "help"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        for target in [
            "vm-build",
            "vm-start",
            "vm-stop",
            "vm-ssh",
            "vm-delete",
            "install",
            "logs",
            "generate-configs",
        ]:
            with self.subTest(target=target):
                self.assertIn(target, result.stdout)

    def test_vm_target_fails_with_descriptive_message_when_vm_script_missing(self):
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            # Copy only the Makefile so that scripts/vm.sh is absent
            shutil.copy(REPO_ROOT / "Makefile", tmp)
            result = subprocess.run(
                ["make", "vm-start"],
                cwd=tmp,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            combined = f"{result.stdout}\n{result.stderr}"
            self.assertIn("scripts/vm.sh not found", combined)


class TestVMScript(unittest.TestCase):
    VM_SCRIPT = REPO_ROOT / "scripts" / "vm.sh"

    def test_vm_script_exists(self):
        self.assertTrue(self.VM_SCRIPT.is_file(), "scripts/vm.sh must exist")

    def test_vm_script_syntax(self):
        result = subprocess.run(
            ["bash", "-n", str(self.VM_SCRIPT)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)

    def test_status_exits_zero_and_prints_stopped_when_no_vm_running(self):
        result = subprocess.run(
            ["bash", str(self.VM_SCRIPT), "status"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("stopped", result.stdout)

    def test_unknown_subcommand_exits_nonzero(self):
        result = subprocess.run(
            ["bash", str(self.VM_SCRIPT), "bogus-command"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)

    def test_vm_disk_and_ssh_port_configurable_via_env(self):
        """start sub-command should honour VM_DISK / VM_SSH_PORT env vars."""
        import os
        import tempfile

        # Stub qemu-system-aarch64 so the prerequisite check passes and the
        # script reaches the disk-existence check (which is what we're testing).
        with tempfile.TemporaryDirectory() as stub_bin:
            stub = Path(stub_bin) / "qemu-system-aarch64"
            stub.write_text("#!/bin/sh\nexit 1\n")
            stub.chmod(0o755)

            env_vars = {
                "VM_DISK": "/nonexistent/custom.qcow2",
                "VM_SSH_PORT": "9999",
                "PATH": f"{stub_bin}:{os.environ.get('PATH', '')}",
            }
            env = {**os.environ, **env_vars}
            result = subprocess.run(
                ["bash", str(self.VM_SCRIPT), "start"],
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )
        # Should fail because the disk image doesn't exist, but the error
        # message must mention the custom path, proving the env var was read.
        combined = f"{result.stdout}\n{result.stderr}"
        self.assertIn("/nonexistent/custom.qcow2", combined)
        self.assertNotEqual(result.returncode, 0)

    def test_delete_removes_disk_image(self):
        """delete sub-command should remove an existing disk image."""
        import os
        with tempfile.TemporaryDirectory() as tmp:
            disk = Path(tmp) / "cafebox-dev.qcow2"
            disk.write_bytes(b"fake-qcow2-data")
            env = {**os.environ, "VM_DISK": str(disk)}
            result = subprocess.run(
                ["bash", str(self.VM_SCRIPT), "delete"],
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertFalse(disk.exists(), "Disk image should have been deleted")
            self.assertIn("Deleted", result.stdout)

    def test_delete_when_no_disk_prints_info_and_exits_zero(self):
        """delete sub-command should exit 0 with an INFO message when no disk exists."""
        import os
        env = {**os.environ, "VM_DISK": "/nonexistent/no-disk.qcow2"}
        result = subprocess.run(
            ["bash", str(self.VM_SCRIPT), "delete"],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("INFO", result.stdout)


class TestBuildVMDiskScript(unittest.TestCase):
    BUILD_SCRIPT = REPO_ROOT / "scripts" / "build-vm-disk.sh"

    def test_build_script_syntax(self):
        result = subprocess.run(
            ["bash", "-n", str(self.BUILD_SCRIPT)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)

    def test_build_script_requires_mtools(self):
        content = self.BUILD_SCRIPT.read_text()
        self.assertIn(
            "mcopy", content,
            "build-vm-disk.sh should check for mcopy (mtools)",
        )

    def test_build_script_enables_ssh(self):
        content = self.BUILD_SCRIPT.read_text()
        self.assertIn(
            "::/ssh", content,
            "build-vm-disk.sh should write an ssh file into the boot partition",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
