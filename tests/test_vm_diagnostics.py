import json
import math
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from syzqemuctl import RuntimeDiagnostics
from syzqemuctl.cli import cli
from syzqemuctl.config import global_conf
from syzqemuctl.vm import VM


class RuntimeDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.vm = VM(str(Path(self.tempdir.name) / "image"))
        self.vm.image_path.mkdir(parents=True)

    def test_clean_runtime(self):
        with patch.object(
            self.vm, "_screen_session_ids", return_value=[]
        ), patch.object(
            self.vm, "_qemu_pids_for_image", return_value=[]
        ), patch.object(
            self.vm, "get_last_vm_config", return_value=None
        ):
            diagnostics = self.vm.runtime_diagnostics(timeout=2)

        self.assertTrue(diagnostics.runtime_clean)
        self.assertEqual(diagnostics.screen_sessions, [])
        self.assertEqual(diagnostics.qemu_pids, [])
        self.assertFalse(diagnostics.pidfile_exists)
        self.assertIsNone(diagnostics.port_open)
        self.assertFalse(diagnostics.errors)

    def test_running_vm_reports_owned_runtime_resources(self):
        self.vm.pid_file.write_text("123")
        self.vm.log_file.write_text("booting")
        sock = MagicMock()
        sock.__enter__.return_value = sock
        sock.connect_ex.return_value = 0

        with patch.object(
            self.vm, "_screen_session_ids", return_value=["7.session"]
        ), patch.object(
            self.vm, "_qemu_pids_for_image", return_value=[123]
        ), patch.object(
            self.vm,
            "get_last_vm_config",
            return_value=SimpleNamespace(port=2222),
        ), patch("syzqemuctl.vm.socket.socket", return_value=sock):
            diagnostics = self.vm.runtime_diagnostics(timeout=2)

        self.assertFalse(diagnostics.runtime_clean)
        self.assertEqual(diagnostics.screen_sessions, ["7.session"])
        self.assertEqual(diagnostics.qemu_pids, [123])
        self.assertEqual(diagnostics.pidfile_pid, 123)
        self.assertTrue(diagnostics.pidfile_pid_valid)
        self.assertEqual(diagnostics.port, 2222)
        self.assertTrue(diagnostics.port_checked)
        self.assertTrue(diagnostics.port_open)
        self.assertTrue(diagnostics.log_file_exists)

    def test_stale_pidfile_is_reported_without_modification(self):
        self.vm.pid_file.write_text("999")

        with patch.object(
            self.vm, "_screen_session_ids", return_value=[]
        ), patch.object(
            self.vm, "_qemu_pids_for_image", return_value=[123]
        ), patch.object(
            self.vm, "get_last_vm_config", return_value=None
        ), patch.object(
            self.vm, "_terminate_runtime_once"
        ) as terminate:
            diagnostics = self.vm.runtime_diagnostics(timeout=2)

        self.assertFalse(diagnostics.runtime_clean)
        self.assertEqual(diagnostics.pidfile_pid, 999)
        self.assertFalse(diagnostics.pidfile_pid_valid)
        self.assertEqual(self.vm.pid_file.read_text(), "999")
        terminate.assert_not_called()

    def test_malformed_pidfile_is_explicitly_invalid(self):
        self.vm.pid_file.write_text("not-a-pid")

        with patch.object(
            self.vm, "_screen_session_ids", return_value=[]
        ), patch.object(
            self.vm, "_qemu_pids_for_image", return_value=[]
        ), patch.object(
            self.vm, "get_last_vm_config", return_value=None
        ):
            diagnostics = self.vm.runtime_diagnostics(timeout=2)

        self.assertFalse(diagnostics.runtime_clean)
        self.assertIsNone(diagnostics.pidfile_pid)
        self.assertFalse(diagnostics.pidfile_pid_valid)
        self.assertIn("pidfile contains an invalid PID", diagnostics.errors)

    def test_screen_inspection_failure_returns_unknown_state(self):
        with patch.object(
            self.vm, "_screen_session_ids", return_value=None
        ), patch.object(
            self.vm, "_qemu_pids_for_image", return_value=[]
        ), patch.object(
            self.vm, "get_last_vm_config", return_value=None
        ):
            diagnostics = self.vm.runtime_diagnostics(timeout=2)

        self.assertIsNone(diagnostics.screen_sessions)
        self.assertIsNone(diagnostics.runtime_clean)
        self.assertTrue(
            any("screen inspection" in error for error in diagnostics.errors)
        )

    def test_qemu_inspection_timeout_returns_unknown_state(self):
        with patch.object(
            self.vm, "_screen_session_ids", return_value=[]
        ), patch.object(
            self.vm,
            "_qemu_pids_for_image",
            side_effect=TimeoutError("timed out"),
        ) as qemu_pids, patch.object(
            self.vm, "get_last_vm_config", return_value=None
        ):
            diagnostics = self.vm.runtime_diagnostics(timeout=2)

        self.assertIsNone(diagnostics.qemu_pids)
        self.assertIsNone(diagnostics.runtime_clean)
        self.assertIsNotNone(qemu_pids.call_args.kwargs["deadline"])
        self.assertTrue(qemu_pids.call_args.kwargs["strict"])
        self.assertIn(
            "QEMU process inspection timed out",
            diagnostics.errors,
        )

    def test_qemu_inspection_permission_failure_is_not_reported_as_clean(self):
        with patch.object(
            self.vm, "_screen_session_ids", return_value=[]
        ), patch.object(
            self.vm,
            "_qemu_pids_for_image",
            side_effect=PermissionError("denied"),
        ), patch.object(
            self.vm, "get_last_vm_config", return_value=None
        ):
            diagnostics = self.vm.runtime_diagnostics(timeout=2)

        self.assertIsNone(diagnostics.qemu_pids)
        self.assertIsNone(diagnostics.runtime_clean)
        self.assertTrue(
            any("QEMU process inspection failed" in error
                for error in diagnostics.errors)
        )

    def test_strict_qemu_inspection_surfaces_proc_permission_errors(self):
        proc_root = Path(self.tempdir.name) / "proc"
        (proc_root / "123").mkdir(parents=True)
        self.vm.PROC_ROOT = proc_root

        with patch.object(
            Path,
            "read_bytes",
            side_effect=PermissionError("denied"),
        ):
            self.assertEqual(self.vm._qemu_pids_for_image(), [])
            with self.assertRaises(PermissionError):
                self.vm._qemu_pids_for_image(strict=True)

    def test_invalid_timeouts_are_rejected(self):
        for timeout in (0, -1, math.inf, math.nan):
            with self.subTest(timeout=timeout):
                with self.assertRaises(ValueError):
                    self.vm.runtime_diagnostics(timeout=timeout)

    def test_port_check_can_be_skipped_and_missing_config_is_allowed(self):
        with patch.object(
            self.vm, "_screen_session_ids", return_value=[]
        ), patch.object(
            self.vm, "_qemu_pids_for_image", return_value=[]
        ), patch.object(
            self.vm,
            "get_last_vm_config",
            return_value=SimpleNamespace(port=2222),
        ), patch("syzqemuctl.vm.socket.socket") as socket_factory:
            diagnostics = self.vm.runtime_diagnostics(
                timeout=2,
                check_port=False,
            )

        self.assertEqual(diagnostics.port, 2222)
        self.assertFalse(diagnostics.port_checked)
        self.assertIsNone(diagnostics.port_open)
        self.assertTrue(diagnostics.runtime_clean)
        socket_factory.assert_not_called()

        with patch.object(
            self.vm, "_screen_session_ids", return_value=[]
        ), patch.object(
            self.vm, "_qemu_pids_for_image", return_value=[]
        ), patch.object(
            self.vm, "get_last_vm_config", return_value=None
        ):
            diagnostics = self.vm.runtime_diagnostics(timeout=2)

        self.assertIsNone(diagnostics.port)
        self.assertIsNone(diagnostics.port_open)
        self.assertTrue(diagnostics.runtime_clean)

    def test_unparseable_saved_config_makes_port_state_unknown(self):
        self.vm.boot_script.write_text("not a QEMU boot script")

        with patch.object(
            self.vm, "_screen_session_ids", return_value=[]
        ), patch.object(
            self.vm, "_qemu_pids_for_image", return_value=[]
        ):
            diagnostics = self.vm.runtime_diagnostics(timeout=2)

        self.assertIsNone(diagnostics.port_open)
        self.assertIsNone(diagnostics.runtime_clean)
        self.assertIn(
            "saved VM configuration could not be parsed",
            diagnostics.errors,
        )

    def test_dataclass_supports_dict_and_summary_output(self):
        diagnostics = RuntimeDiagnostics(
            image_path="/images/test",
            screen_sessions=[],
            qemu_pids=[],
            pidfile_exists=False,
            pidfile_pid=None,
            pidfile_pid_valid=None,
            port=2222,
            port_open=False,
            port_checked=True,
            log_file_exists=True,
            runtime_clean=True,
            errors=[],
        )

        self.assertEqual(diagnostics.to_dict()["image_path"], "/images/test")
        self.assertIn("runtime=clean", diagnostics.summary())
        self.assertIn("port=2222 (closed)", diagnostics.summary())


class DiagnoseCLITests(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()
        self.old_settings = dict(global_conf._settings)
        global_conf._settings = {"images_home": "/tmp/images"}
        self.addCleanup(self._restore_settings)

    def _restore_settings(self):
        global_conf._settings = self.old_settings

    def test_diagnose_json_outputs_structured_result(self):
        manager = MagicMock()
        manager.get_image_info.return_value = SimpleNamespace(
            path=Path("/tmp/images/image")
        )
        diagnostics = RuntimeDiagnostics(
            image_path="/tmp/images/image",
            screen_sessions=[],
            qemu_pids=[],
            pidfile_exists=False,
            pidfile_pid=None,
            pidfile_pid_valid=None,
            port=None,
            port_open=None,
            port_checked=False,
            log_file_exists=False,
            runtime_clean=True,
            errors=[],
        )
        vm = MagicMock()
        vm.runtime_diagnostics.return_value = diagnostics

        with patch.object(global_conf, "load", return_value=True), patch(
            "syzqemuctl.cli.ImageManager", return_value=manager
        ), patch("syzqemuctl.cli.VM", return_value=vm):
            result = self.runner.invoke(
                cli,
                [
                    "diagnose",
                    "image",
                    "--timeout",
                    "3",
                    "--no-check-port",
                    "--json",
                ],
            )

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(json.loads(result.output), diagnostics.to_dict())
        vm.runtime_diagnostics.assert_called_once_with(
            timeout=3.0,
            check_port=False,
        )

    def test_diagnose_rejects_nonfinite_timeout(self):
        manager = MagicMock()
        manager.get_image_info.return_value = SimpleNamespace(
            path=Path("/tmp/images/image")
        )

        with patch.object(global_conf, "load", return_value=True), patch(
            "syzqemuctl.cli.ImageManager", return_value=manager
        ):
            result = self.runner.invoke(
                cli,
                ["diagnose", "image", "--timeout", "nan"],
            )

        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("finite value greater than zero", result.output)


if __name__ == "__main__":
    unittest.main()
