import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from syzqemuctl.vm import VM, VMConfig


class BindSocket:
    def __init__(self, error=None):
        self.error = error
        self.address = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def bind(self, address):
        self.address = address
        if self.error is not None:
            raise self.error


class VMBootTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)

    def test_boot_script_quotes_values_and_round_trips_config(self):
        image_path = Path(self.tempdir.name) / "image dir;$(host-command)"
        image_path.mkdir()
        vm = VM(str(image_path))
        config = VMConfig(
            kernel=str(Path(self.tempdir.name) / "kernel dir"),
            port=2233,
            memory="6G",
            smp=3,
            snapshot=True,
            kernel_args="console=ttyS0 init=/bin/sh;echo 'guest value'",
        )

        vm._generate_boot_script(config)

        subprocess.run(["bash", "-n", str(vm.boot_script)], check=True)
        parsed = VMConfig.from_boot_script(vm.boot_script)
        self.assertEqual(parsed, config)
        script = vm.boot_script.read_text()
        self.assertIn(
            shlex.quote(str(image_path / "bullseye.img")),
            script,
        )
        self.assertIn(shlex.quote(config.kernel_args), script)

    def test_legacy_boot_script_remains_parseable(self):
        script = Path(self.tempdir.name) / "boot.sh"
        script.write_text(
            "#!/bin/bash\n"
            "exec qemu-system-x86_64 \\\n"
            " -kernel /kernels/linux/arch/x86/boot/bzImage \\\n"
            " -append \"console=ttyS0 root=/dev/sda\" \\\n"
            " -hda ./bullseye.img \\\n"
            " -net user,hostfwd=tcp::2233-:22 -net nic \\\n"
            " -m 4G -smp 2 -pidfile vm.pid\n"
        )

        config = VMConfig.from_boot_script(script)

        self.assertIsNotNone(config)
        self.assertEqual(config.kernel, "/kernels/linux")
        self.assertEqual(config.port, 2233)
        self.assertEqual(config.kernel_args, "console=ttyS0 root=/dev/sda")

    def test_start_appends_extra_args_to_defaults_and_precleans(self):
        image_path = Path(self.tempdir.name) / "image"
        image_path.mkdir()
        vm = VM(str(image_path))

        with patch.object(vm, "is_running", side_effect=[False, True]), patch.object(
            vm, "get_last_vm_config", return_value=None
        ), patch.object(
            vm, "_stop_runtime", return_value=True
        ) as cleanup, patch.object(
            vm, "_generate_boot_script"
        ) as generate, patch(
            "syzqemuctl.vm.Path.exists", return_value=True
        ), patch(
            "syzqemuctl.vm.subprocess.run"
        ), patch(
            "syzqemuctl.vm.time.monotonic", side_effect=[0.0, 0.0]
        ):
            result = vm.start(
                kernel="/kernel",
                port=2233,
                extra_kernel_args="systemd.unified_cgroup_hierarchy=0",
            )

        self.assertTrue(result)
        cleanup.assert_called_once_with(
            wait=True,
            timeout=20,
            force=False,
            check_port=False,
        )
        generated_config = generate.call_args.args[0]
        self.assertEqual(
            generated_config.kernel_args,
            f"{VMConfig.DEFAULT_KERNEL_ARGS} "
            "systemd.unified_cgroup_hierarchy=0",
        )

    def test_start_refuses_active_qemu_before_precleanup(self):
        image_path = Path(self.tempdir.name) / "active-image"
        image_path.mkdir()
        vm = VM(str(image_path))

        with patch.object(vm, "is_running", return_value=True), patch.object(
            vm, "_stop_runtime"
        ) as stop:
            result = vm.start(kernel="/kernel")

        self.assertFalse(result)
        stop.assert_not_called()

    def test_start_returns_false_when_boot_script_cannot_be_written(self):
        image_path = Path(self.tempdir.name) / "image"
        image_path.mkdir()
        vm = VM(str(image_path))

        with patch.object(vm, "is_running", return_value=False), patch.object(
            vm, "get_last_vm_config", return_value=None
        ), patch.object(
            vm, "_stop_runtime", side_effect=[True, True]
        ) as cleanup, patch.object(
            vm, "_generate_boot_script", side_effect=OSError("read-only")
        ):
            result = vm.start(kernel="/kernel", port=2233)

        self.assertFalse(result)
        self.assertEqual(cleanup.call_count, 2)

    def test_start_combines_explicit_and_extra_kernel_args(self):
        image_path = Path(self.tempdir.name) / "image"
        image_path.mkdir()
        vm = VM(str(image_path))

        with patch.object(vm, "is_running", side_effect=[False, True]), patch.object(
            vm, "get_last_vm_config", return_value=None
        ), patch.object(
            vm, "_stop_runtime", return_value=True
        ), patch.object(
            vm, "_generate_boot_script"
        ) as generate, patch(
            "syzqemuctl.vm.Path.exists", return_value=True
        ), patch(
            "syzqemuctl.vm.subprocess.run"
        ), patch(
            "syzqemuctl.vm.time.monotonic", side_effect=[0.0, 0.0]
        ):
            result = vm.start(
                kernel="/kernel",
                port=2233,
                kernel_args="root=/dev/vda",
                extra_kernel_args="panic=1",
            )

        self.assertTrue(result)
        self.assertEqual(
            generate.call_args.args[0].kernel_args,
            "root=/dev/vda panic=1",
        )

    def test_start_inherits_last_kernel_args_when_unspecified(self):
        image_path = Path(self.tempdir.name) / "image"
        image_path.mkdir()
        vm = VM(str(image_path))
        last_config = VMConfig(
            kernel="/old-kernel",
            port=2233,
            kernel_args="root=/dev/vda custom=1",
        )

        with patch.object(vm, "is_running", side_effect=[False, True]), patch.object(
            vm, "get_last_vm_config", return_value=last_config
        ), patch.object(
            vm, "_stop_runtime", return_value=True
        ), patch.object(
            vm, "_find_available_port", return_value=2233
        ), patch.object(
            vm, "_generate_boot_script"
        ) as generate, patch(
            "syzqemuctl.vm.Path.exists", return_value=True
        ), patch(
            "syzqemuctl.vm.subprocess.run"
        ), patch(
            "syzqemuctl.vm.time.monotonic", side_effect=[0.0, 0.0]
        ):
            result = vm.start()

        self.assertTrue(result)
        self.assertEqual(
            generate.call_args.args[0].kernel_args,
            last_config.kernel_args,
        )

    def test_start_appends_extra_args_to_last_kernel_args(self):
        image_path = Path(self.tempdir.name) / "image"
        image_path.mkdir()
        vm = VM(str(image_path))
        last_config = VMConfig(
            kernel="/old-kernel",
            port=2233,
            kernel_args="root=/dev/vda custom=1",
        )

        with patch.object(vm, "is_running", side_effect=[False, True]), patch.object(
            vm, "get_last_vm_config", return_value=last_config
        ), patch.object(
            vm, "_stop_runtime", return_value=True
        ), patch.object(
            vm, "_find_available_port", return_value=2233
        ), patch.object(
            vm, "_generate_boot_script"
        ) as generate, patch(
            "syzqemuctl.vm.Path.exists", return_value=True
        ), patch(
            "syzqemuctl.vm.subprocess.run"
        ), patch(
            "syzqemuctl.vm.time.monotonic", side_effect=[0.0, 0.0]
        ):
            result = vm.start(extra_kernel_args="panic=1")

        self.assertTrue(result)
        self.assertEqual(
            generate.call_args.args[0].kernel_args,
            "root=/dev/vda custom=1 panic=1",
        )

    def test_find_available_port_uses_socket_bind(self):
        image_path = Path(self.tempdir.name) / "image"
        image_path.mkdir()
        vm = VM(str(image_path))
        vm.PORT_START = 24000
        vm.PORT_END = 24002
        occupied = BindSocket(OSError("in use"))
        available = BindSocket()

        with patch.object(vm, "get_last_vm_config", return_value=None), patch(
            "syzqemuctl.vm.socket.socket",
            side_effect=[occupied, available],
        ):
            port = vm._find_available_port()

        self.assertEqual(port, 24001)
        self.assertEqual(occupied.address, ("0.0.0.0", 24000))
        self.assertEqual(available.address, ("0.0.0.0", 24001))

    def test_connect_uses_one_ssh_handshake(self):
        image_path = Path(self.tempdir.name) / "image"
        image_path.mkdir()
        vm = VM(str(image_path))
        vm._key_file.touch()
        ssh = Mock()

        with patch.object(vm, "is_running", return_value=True), patch.object(
            vm,
            "get_last_vm_config",
            return_value=SimpleNamespace(port=2233),
        ), patch.object(vm, "is_ready") as is_ready, patch(
            "syzqemuctl.vm.paramiko.SSHClient", return_value=ssh
        ) as ssh_client:
            result = vm.connect()

        self.assertTrue(result)
        ssh_client.assert_called_once_with()
        ssh.connect.assert_called_once()
        is_ready.assert_not_called()
        self.assertIs(vm._ssh, ssh)

    def test_failed_reconnect_preserves_existing_connection(self):
        image_path = Path(self.tempdir.name) / "image"
        image_path.mkdir()
        vm = VM(str(image_path))
        vm._key_file.touch()
        old_ssh = Mock()
        vm._ssh = old_ssh
        new_ssh = Mock()
        new_ssh.connect.side_effect = OSError("connection failed")

        with patch.object(vm, "is_running", return_value=True), patch.object(
            vm,
            "get_last_vm_config",
            return_value=SimpleNamespace(port=2233),
        ), patch(
            "syzqemuctl.vm.paramiko.SSHClient", return_value=new_ssh
        ):
            result = vm.connect()

        self.assertFalse(result)
        self.assertIs(vm._ssh, old_ssh)
        old_ssh.close.assert_not_called()
        new_ssh.close.assert_called_once_with()

    def test_context_manager_raises_when_connect_fails(self):
        image_path = Path(self.tempdir.name) / "image"
        image_path.mkdir()
        vm = VM(str(image_path))

        with patch.object(vm, "connect", return_value=False):
            with self.assertRaises(ConnectionError):
                with vm:
                    self.fail("context body must not run")


if __name__ == "__main__":
    unittest.main()
