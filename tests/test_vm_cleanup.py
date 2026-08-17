import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from syzqemuctl.vm import VM


class VMCleanupTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.vm = VM(str(Path(self.tempdir.name) / "image"))
        self.vm.image_path.mkdir(parents=True, exist_ok=True)

    def test_stop_default_flow_stays_compatible(self):
        with patch.object(
            self.vm, "_terminate_runtime_once", create=True
        ) as terminate_once, patch.object(
            self.vm, "_runtime_is_clean", create=True, return_value=True
        ) as runtime_is_clean, patch.object(
            self.vm, "get_last_vm_config", return_value=None
        ):
            result = self.vm.stop()

        self.assertTrue(result)
        terminate_once.assert_called_once_with(force=False, deadline=None)
        runtime_is_clean.assert_called_once_with(port=None)

    def test_stop_wait_true_retries_until_runtime_is_clean(self):
        with patch.object(
            self.vm, "_terminate_runtime_once", create=True
        ) as terminate_once, patch.object(
            self.vm, "_runtime_is_clean", create=True, side_effect=[False, False, True]
        ) as runtime_is_clean, patch.object(
            self.vm, "get_last_vm_config", return_value=None
        ), patch("syzqemuctl.vm.time.sleep") as sleep:
            result = self.vm.stop(wait=True, timeout=20, force=True)

        self.assertTrue(result)
        self.assertTrue(terminate_once.call_args_list[0].kwargs["force"])
        self.assertIsNotNone(
            terminate_once.call_args_list[0].kwargs["deadline"]
        )
        self.assertEqual(len(terminate_once.call_args_list), 3)
        self.assertEqual(runtime_is_clean.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_stop_wait_true_returns_false_on_timeout(self):
        with patch.object(
            self.vm, "_terminate_runtime_once", create=True
        ) as terminate_once, patch.object(
            self.vm, "_runtime_is_clean", create=True, return_value=False
        ), patch.object(
            self.vm, "get_last_vm_config", return_value=None
        ), patch("syzqemuctl.vm.time.sleep"), patch(
            "syzqemuctl.vm.time.monotonic", side_effect=[0.0, 21.0]
        ):
            result = self.vm.stop(wait=True, timeout=20, force=False)

        self.assertFalse(result)
        self.assertEqual(len(terminate_once.call_args_list), 1)
        self.assertEqual(
            terminate_once.call_args_list[0].kwargs["deadline"],
            20.0,
        )

    def test_cleanup_runtime_delegates_to_force_wait_stop(self):
        with patch.object(self.vm, "stop", return_value=True) as stop:
            result = self.vm.cleanup_runtime(timeout=9)

        self.assertTrue(result)
        stop.assert_called_once_with(wait=True, timeout=9, force=True)

    def test_terminate_runtime_once_force_kills_orphan_qemu(self):
        self.vm.pid_file.write_text("123")

        with patch.object(self.vm, "disconnect") as disconnect, patch(
            "syzqemuctl.vm.utils.kill_process", return_value=True
        ) as kill_process, patch.object(
            self.vm, "_screen_session_ids", create=True, return_value=["1111.syzqemuctl-test"]
        ), patch.object(
            self.vm, "_qemu_pids_for_image", create=True, return_value=[456, 789]
        ), patch.object(
            self.vm, "_pidfile_qemu_pid", create=True, return_value=123
        ), patch("syzqemuctl.vm.subprocess.run") as run:
            self.vm._terminate_runtime_once(force=True)

        disconnect.assert_called_once_with()
        kill_process.assert_any_call(123)
        kill_process.assert_any_call(456)
        kill_process.assert_any_call(789)
        self.assertFalse(self.vm.pid_file.exists())
        run.assert_called()

    def test_runtime_is_clean_detects_stale_resources(self):
        self.vm.pid_file.write_text("stale")

        with patch.object(self.vm, "_screen_session_ids", create=True, return_value=["1111.test"]), patch.object(
            self.vm, "_qemu_pids_for_image", create=True, return_value=[]
        ):
            clean = self.vm._runtime_is_clean()

        self.assertFalse(clean)

    def test_runtime_is_not_clean_when_screen_state_is_unknown(self):
        with patch.object(
            self.vm, "_screen_session_ids", return_value=None
        ), patch.object(
            self.vm, "_qemu_pids_for_image", return_value=[]
        ):
            clean = self.vm._runtime_is_clean()

        self.assertFalse(clean)

    def test_runtime_is_not_clean_while_saved_ssh_port_is_open(self):
        sock = MagicMock()
        sock.__enter__.return_value = sock
        sock.connect_ex.return_value = 0

        with patch.object(
            self.vm, "_screen_session_ids", return_value=[]
        ), patch.object(
            self.vm, "_qemu_pids_for_image", return_value=[]
        ), patch("syzqemuctl.vm.socket.socket", return_value=sock):
            clean = self.vm._runtime_is_clean(port=2233)

        self.assertFalse(clean)
        sock.settimeout.assert_called_once_with(0.2)

    def test_screen_session_matching_is_exact(self):
        output = (
            "There are screens on:\n"
            f"\t111.{self.vm.screen_name}\t(Detached)\n"
            f"\t222.{self.vm.screen_name}-copy\t(Detached)\n"
        )
        with patch(
            "syzqemuctl.vm.subprocess.run",
            return_value=SimpleNamespace(stdout=output),
        ):
            sessions = self.vm._screen_session_ids()

        self.assertEqual(sessions, [f"111.{self.vm.screen_name}"])

    def test_stale_pidfile_does_not_kill_unrelated_process(self):
        self.vm.pid_file.write_text("321")

        with patch.object(self.vm, "disconnect"), patch.object(
            self.vm, "_pidfile_qemu_pid", return_value=None
        ), patch.object(
            self.vm, "_qemu_pids_for_image", return_value=[]
        ), patch.object(
            self.vm, "_screen_session_ids", return_value=[]
        ), patch(
            "syzqemuctl.vm.utils.kill_process"
        ) as kill_process:
            self.vm._terminate_runtime_once(force=False)

        kill_process.assert_not_called()
        self.assertFalse(self.vm.pid_file.exists())

    def test_failed_qemu_termination_keeps_pidfile_for_retry(self):
        self.vm.pid_file.write_text("321")

        with patch.object(self.vm, "disconnect"), patch.object(
            self.vm, "_pidfile_qemu_pid", return_value=321
        ), patch.object(
            self.vm, "_screen_session_ids", return_value=[]
        ), patch(
            "syzqemuctl.vm.utils.kill_process", return_value=False
        ):
            self.vm._terminate_runtime_once(force=False)

        self.assertTrue(self.vm.pid_file.exists())

    def test_qemu_process_matching_requires_exact_image(self):
        proc_root = Path(self.tempdir.name) / "proc"
        proc_root.mkdir()
        self.vm.PROC_ROOT = proc_root
        image_file = str(self.vm.image_path / "bullseye.img")

        commands = {
            "100": ["qemu-system-x86_64", "-hda", image_file],
            "101": [
                "qemu-system-x86_64",
                "-hda",
                f"{image_file}-copy",
            ],
            "102": ["python3", image_file],
        }
        for pid, arguments in commands.items():
            proc_dir = proc_root / pid
            proc_dir.mkdir()
            (proc_dir / "cmdline").write_bytes(
                b"\0".join(arg.encode() for arg in arguments) + b"\0"
            )

        self.assertEqual(self.vm._qemu_pids_for_image(), [100])

        self.vm.pid_file.write_text("101")
        self.assertIsNone(self.vm._pidfile_qemu_pid())

    def test_qemu_process_matching_resolves_legacy_relative_image_path(self):
        proc_root = Path(self.tempdir.name) / "proc-relative"
        proc_root.mkdir()
        self.vm.PROC_ROOT = proc_root
        proc_dir = proc_root / "200"
        proc_dir.mkdir()
        (proc_dir / "cwd").symlink_to(self.vm.image_path)
        (proc_dir / "cmdline").write_bytes(
            b"qemu-system-x86_64\0-hda\0bullseye.img\0"
        )

        self.assertEqual(self.vm._qemu_pids_for_image(), [200])

    def test_screen_name_distinguishes_same_basename_in_different_homes(self):
        first = VM(str(Path(self.tempdir.name) / "a" / "image"))
        second = VM(str(Path(self.tempdir.name) / "b" / "image"))

        self.assertNotEqual(first.screen_name, second.screen_name)

    def test_screen_name_is_safe_for_unusual_image_paths(self):
        vm = VM(str(Path(self.tempdir.name) / "image dir;$(command)"))

        self.assertNotIn(" ", vm.screen_name)
        self.assertNotIn(";", vm.screen_name)
        self.assertNotIn("$", vm.screen_name)


if __name__ == "__main__":
    unittest.main()
