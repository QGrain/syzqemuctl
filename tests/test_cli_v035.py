import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from syzqemuctl.cli import cli
from syzqemuctl.config import global_conf


class CLIV035Tests(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()
        self.old_settings = dict(global_conf._settings)
        global_conf._settings = {"images_home": "/tmp/images"}
        self.addCleanup(self._restore_settings)

    def _restore_settings(self):
        global_conf._settings = self.old_settings

    def test_subcommand_help_does_not_require_configuration(self):
        global_conf._settings = {}
        with patch.object(global_conf, "load", return_value=False):
            result = self.runner.invoke(cli, ["run", "--help"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("--extra-kernel-args", result.output)

    def test_init_rejects_invalid_size_with_nonzero_exit(self):
        result = self.runner.invoke(
            cli,
            ["init", "--images-home", "/tmp/images", "--size", "0"],
        )

        self.assertNotEqual(result.exit_code, 0)

    def test_init_propagates_template_initialization_failure(self):
        manager = MagicMock()
        manager.initialize.return_value = False

        with patch.object(global_conf, "is_initialized", return_value=False), patch.object(
            global_conf, "initialize"
        ), patch("syzqemuctl.cli.ImageManager", return_value=manager):
            result = self.runner.invoke(
                cli,
                ["init", "--images-home", "/tmp/images"],
            )

        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Failed to initialize", result.output)

    def test_run_accepts_omitted_optional_values_and_kernel_args(self):
        manager = MagicMock()
        manager.get_image_info.return_value = SimpleNamespace(
            path=Path("/tmp/images/image"),
            running=False,
            image_ready=True,
        )
        vm = MagicMock()
        vm.start.return_value = True

        with patch.object(global_conf, "load", return_value=True), patch(
            "syzqemuctl.cli.ImageManager", return_value=manager
        ), patch("syzqemuctl.cli.VM", return_value=vm):
            result = self.runner.invoke(
                cli,
                [
                    "run",
                    "image",
                    "--kernel",
                    "/kernel",
                    "--extra-kernel-args",
                    "systemd.unified_cgroup_hierarchy=0",
                ],
            )

        self.assertEqual(result.exit_code, 0, result.output)
        vm.start.assert_called_once_with(
            kernel="/kernel",
            port=None,
            mem=None,
            smp=None,
            snapshot=False,
            kernel_args=None,
            extra_kernel_args="systemd.unified_cgroup_hierarchy=0",
        )

    def test_stop_force_cleans_nonrunning_image(self):
        manager = MagicMock()
        manager.get_image_info.return_value = SimpleNamespace(
            path=Path("/tmp/images/image"),
            running=False,
        )
        vm = MagicMock()
        vm.stop.return_value = True

        with patch.object(global_conf, "load", return_value=True), patch(
            "syzqemuctl.cli.ImageManager", return_value=manager
        ), patch("syzqemuctl.cli.VM", return_value=vm):
            result = self.runner.invoke(
                cli,
                ["stop", "image", "--force", "--wait", "--timeout", "9"],
            )

        self.assertEqual(result.exit_code, 0, result.output)
        vm.stop.assert_called_once_with(wait=True, timeout=9, force=True)

    def test_copy_timeout_is_forwarded(self):
        manager = MagicMock()
        manager.get_image_info.return_value = SimpleNamespace(
            path=Path("/tmp/images/image"),
            running=True,
            image_ready=True,
        )
        vm = MagicMock()
        vm.__enter__.return_value = vm

        with self.runner.isolated_filesystem():
            Path("source").write_text("data")
            with patch.object(global_conf, "load", return_value=True), patch(
                "syzqemuctl.cli.ImageManager", return_value=manager
            ), patch("syzqemuctl.cli.VM", return_value=vm):
                result = self.runner.invoke(
                    cli,
                    ["cp", "--timeout", "12", "source", "image:/root/dst"],
                )

        self.assertEqual(result.exit_code, 0, result.output)
        vm.copy_to_vm.assert_called_once_with(
            "source", "/root/dst", timeout=12
        )

    def test_exec_timeout_failure_returns_nonzero(self):
        manager = MagicMock()
        manager.get_image_info.return_value = SimpleNamespace(
            path=Path("/tmp/images/image"),
            running=True,
            image_ready=True,
        )
        vm = MagicMock()
        vm.__enter__.return_value = vm
        vm.execute.side_effect = TimeoutError("timed out")

        with patch.object(global_conf, "load", return_value=True), patch(
            "syzqemuctl.cli.ImageManager", return_value=manager
        ), patch("syzqemuctl.cli.VM", return_value=vm):
            result = self.runner.invoke(
                cli,
                ["exec", "--timeout", "7", "image", "sleep 99"],
            )

        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("timed out", result.output)
        vm.execute.assert_called_once_with("sleep 99", timeout=7, check=True)

    def test_exec_remote_failure_returns_nonzero(self):
        manager = MagicMock()
        manager.get_image_info.return_value = SimpleNamespace(
            path=Path("/tmp/images/image"),
            running=True,
            image_ready=True,
        )
        vm = MagicMock()
        vm.__enter__.return_value = vm
        vm.execute.side_effect = subprocess.CalledProcessError(
            2,
            "false",
            stderr="failed",
        )

        with patch.object(global_conf, "load", return_value=True), patch(
            "syzqemuctl.cli.ImageManager", return_value=manager
        ), patch("syzqemuctl.cli.VM", return_value=vm):
            result = self.runner.invoke(cli, ["exec", "image", "false"])

        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("failed", result.output)
        self.assertIn("status 2", result.output)
        vm.execute.assert_called_once_with("false", timeout=None, check=True)


if __name__ == "__main__":
    unittest.main()
