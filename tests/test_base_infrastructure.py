import importlib.util
import os
import shutil
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
            "vm-status",
            "vm-delete",
            "install",
            "logs",
            "generate-configs",
        ]:
            with self.subTest(target=target):
                self.assertIn(target, result.stdout)

    def test_vm_target_fails_with_descriptive_message_when_vm_script_missing(self):
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

    def test_status_shows_dist_dir_when_stopped(self):
        """status should report the PI_DIST_DIR path regardless of whether
        the Pi container is running."""
        env = {**os.environ, "PI_DIST_DIR": "/tmp/nonexistent-cafebox-pi"}
        result = subprocess.run(
            ["bash", str(self.VM_SCRIPT), "status"],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        # The dist dir path must appear in the output.
        self.assertIn("/tmp/nonexistent-cafebox-pi", result.stdout)
        # When the dist dir is absent the output must say so.
        self.assertIn("not found", result.stdout)

    def test_status_shows_ssh_port_not_checked_when_stopped(self):
        """status should report the SSH port and note it was not checked when VM is stopped."""
        env = {**os.environ, "VM_SSH_PORT": "9876"}
        result = subprocess.run(
            ["bash", str(self.VM_SCRIPT), "status"],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("9876", result.stdout)
        self.assertIn("not checked", result.stdout)

    def test_unknown_subcommand_exits_nonzero(self):
        result = subprocess.run(
            ["bash", str(self.VM_SCRIPT), "bogus-command"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)

    def test_pi_ssh_port_and_dist_dir_configurable_via_env(self):
        """start sub-command should honour PI_DIST_DIR / VM_SSH_PORT env vars."""
        # Stub docker so the prerequisite check passes but docker run fails,
        # proving the script reaches the start echo (which prints PI_DIST_DIR).
        with tempfile.TemporaryDirectory() as tmp_dir:
            stub_bin = Path(tmp_dir) / "bin"
            stub_bin.mkdir()
            custom_dist = Path(tmp_dir) / "custom-pi-dist"

            stub = stub_bin / "docker"
            stub.write_text("#!/bin/sh\nexit 1\n")
            stub.chmod(0o755)

            env_vars = {
                "PI_DIST_DIR": str(custom_dist),
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
        # Should fail because docker run fails, but the echo before it must
        # mention the custom PI_DIST_DIR, proving the env var was read.
        combined = f"{result.stdout}\n{result.stderr}"
        self.assertIn(str(custom_dist), combined)
        self.assertNotEqual(result.returncode, 0)

    def test_delete_removes_dist_directory(self):
        """delete sub-command should remove an existing Pi dist directory."""
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp) / "pi" / "dist"
            dist.mkdir(parents=True)
            env = {**os.environ, "PI_DIST_DIR": str(dist)}
            result = subprocess.run(
                ["bash", str(self.VM_SCRIPT), "delete"],
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertFalse(dist.exists(), "Dist directory should have been deleted")
            self.assertIn("Deleted", result.stdout)

    def test_delete_when_no_dist_dir_prints_info_and_exits_zero(self):
        """delete sub-command should exit 0 with an INFO message when no dist dir exists."""
        env = {**os.environ, "PI_DIST_DIR": "/nonexistent/no-pi-dist"}
        result = subprocess.run(
            ["bash", str(self.VM_SCRIPT), "delete"],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("INFO", result.stdout)

    def test_pi_start_uses_pi_ci_docker_image(self):
        """vm.sh start must use the ptrsr/pi-ci Docker image instead of QEMU."""
        content = self.VM_SCRIPT.read_text()
        self.assertIn(
            "ptrsr/pi-ci",
            content,
            "vm.sh should reference the ptrsr/pi-ci Docker image",
        )
        self.assertNotIn(
            "qemu-system-aarch64",
            content,
            "vm.sh must not invoke QEMU directly: use the Docker image instead",
        )

    def test_pi_start_uses_docker_run(self):
        """vm.sh start must use 'docker run' to launch the Pi emulator."""
        content = self.VM_SCRIPT.read_text()
        self.assertIn(
            "docker run",
            content,
            "vm.sh should use 'docker run' to start the Pi emulator",
        )
        self.assertIn(
            "PI_CI_IMAGE",
            content,
            "vm.sh should use the PI_CI_IMAGE variable for the Docker image name",
        )

    def test_vm_ssh_waits_for_ssh_readiness(self):
        """vm.sh must call _wait_for_ssh before connecting."""
        content = self.VM_SCRIPT.read_text()
        self.assertIn(
            "_wait_for_ssh",
            content,
            "vm.sh should define and call a _wait_for_ssh helper",
        )
        self.assertIn(
            "ssh-keyscan",
            content,
            "vm.sh _wait_for_ssh should use ssh-keyscan to detect a live sshd",
        )

    def test_pi_start_captures_docker_output_to_log(self):
        """vm.sh must redirect docker startup output to VM_LOG_FILE so the
        user can inspect it for troubleshooting."""
        content = self.VM_SCRIPT.read_text()
        self.assertIn(
            "VM_LOG_FILE",
            content,
            "vm.sh should define a VM_LOG_FILE variable",
        )
        self.assertIn(
            '"$VM_LOG_FILE"',
            content,
            "vm.sh should redirect docker output to VM_LOG_FILE",
        )

    def test_pi_start_prints_log_info(self):
        """cmd_start must print the log file path so the user knows where to
        look for startup output."""
        content = self.VM_SCRIPT.read_text()
        self.assertRegex(
            content,
            r'echo.*VM_LOG_FILE',
            "vm.sh should echo the VM_LOG_FILE path in cmd_start",
        )


class TestDockerSetup(unittest.TestCase):
    """Validate that the pi-ci Docker-based architecture is correctly wired."""

    def test_vm_sh_uses_docker_not_qemu(self):
        """vm.sh must use Docker/pi-ci, not QEMU directly."""
        content = (REPO_ROOT / "scripts" / "vm.sh").read_text()
        self.assertIn(
            "docker",
            content,
            "vm.sh should use Docker to manage the Pi emulator",
        )
        self.assertNotIn(
            "qemu-system-aarch64",
            content,
            "vm.sh must not invoke qemu-system-aarch64 directly",
        )

    def test_pi_dist_dir_is_gitignored(self):
        """pi/dist/ must be in .gitignore (contains large qcow2 images)."""
        gitignore = (REPO_ROOT / ".gitignore").read_text()
        self.assertIn(
            "pi/dist",
            gitignore,
            ".gitignore should exclude the Pi emulator dist directory",
        )

    def test_vm_build_uses_docker_pull(self):
        """make vm-build must pull the pi-ci Docker image."""
        makefile = (REPO_ROOT / "Makefile").read_text()
        self.assertIn(
            "docker pull",
            makefile,
            "Makefile vm-build target should pull the pi-ci Docker image",
        )

    def test_makefile_references_pi_ci_image(self):
        """Makefile must reference ptrsr/pi-ci as the Docker image."""
        makefile = (REPO_ROOT / "Makefile").read_text()
        self.assertIn(
            "ptrsr/pi-ci",
            makefile,
            "Makefile should reference ptrsr/pi-ci as the Pi emulator image",
        )

    def test_makefile_has_pi_dist_dir_variable(self):
        """Makefile must define PI_DIST_DIR for the persistent disk directory."""
        makefile = (REPO_ROOT / "Makefile").read_text()
        self.assertIn(
            "PI_DIST_DIR",
            makefile,
            "Makefile should define PI_DIST_DIR for the Pi emulator dist directory",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
