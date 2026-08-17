import subprocess
import time
import unittest
from unittest.mock import patch

from syzqemuctl.vm import VM


class FakeSocket:
    def __init__(self, channel=None):
        self.timeout = None
        self.closed = False
        self.channel = channel

    def gettimeout(self):
        return self.timeout

    def settimeout(self, value):
        self.timeout = value

    def close(self):
        self.closed = True
        if self.channel is not None:
            self.channel.close()


class FakeTransport:
    def __init__(self, sock=None, channel=None):
        self.sock = sock or FakeSocket(channel=channel)
        self.closed = False

    def close(self):
        self.closed = True
        self.sock.close()


class FakeChannel:
    def __init__(
        self,
        stdout_chunks=None,
        stderr_chunks=None,
        exit_status=0,
        block_stdout=False,
        block_stderr=False,
        sync_reads=False,
    ):
        self.stdout_chunks = list(stdout_chunks or [])
        self.stderr_chunks = list(stderr_chunks or [])
        self.exit_status = exit_status
        self.block_stdout = block_stdout
        self.block_stderr = block_stderr
        self.sync_reads = sync_reads
        self.closed = False
        self.stdout_started = False
        self.stderr_started = False

    def recv_exit_status(self):
        return self.exit_status

    def close(self):
        self.closed = True


class FakeStream:
    def __init__(self, channel, stream_name):
        self.channel = channel
        self.stream_name = stream_name

    def read(self):
        if self.stream_name == "stdout":
            chunks = self.channel.stdout_chunks
            should_block = self.channel.block_stdout
            peer_started = lambda: self.channel.stderr_started
            self.channel.stdout_started = True
        else:
            chunks = self.channel.stderr_chunks
            should_block = self.channel.block_stderr
            peer_started = lambda: self.channel.stdout_started
            self.channel.stderr_started = True

        while self.channel.sync_reads and not peer_started() and not self.channel.closed:
            time.sleep(0.001)

        while should_block and not self.channel.closed:
            time.sleep(0.001)

        if should_block and self.channel.closed:
            raise EOFError("channel closed")

        data = b"".join(chunks)
        chunks.clear()
        return data


class FakeSSHClient:
    def __init__(self, channel):
        self.transport = FakeTransport(channel=channel)
        self.channel = channel
        self.closed = False

    def get_transport(self):
        return self.transport

    def close(self):
        self.closed = True
        self.transport.close()

    def exec_command(self, _command, **_kwargs):
        return (
            object(),
            FakeStream(self.channel, "stdout"),
            FakeStream(self.channel, "stderr"),
        )


class RecordingSCPClient:
    instances = []

    def __init__(self, transport, socket_timeout=10.0, **_kwargs):
        self.transport = transport
        self.socket_timeout = socket_timeout
        self.calls = []
        RecordingSCPClient.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def put(self, local_path, remote_path, recursive=True):
        self.calls.append(("put", local_path, remote_path, recursive))

    def get(self, remote_path, local_path, recursive=True):
        self.calls.append(("get", remote_path, local_path, recursive))


class BlockingSCPClient(RecordingSCPClient):
    def put(self, local_path, remote_path, recursive=True):
        self.calls.append(("put", local_path, remote_path, recursive))
        while not self.transport.sock.closed:
            time.sleep(0.001)

    def get(self, remote_path, local_path, recursive=True):
        self.calls.append(("get", remote_path, local_path, recursive))
        while not self.transport.sock.closed:
            time.sleep(0.001)


class VMTimeoutTests(unittest.TestCase):
    def setUp(self):
        RecordingSCPClient.instances = []
        self.vm = VM("/tmp/test-image")

    def test_execute_without_timeout_returns_stdout_and_stderr(self):
        channel = FakeChannel(
            stdout_chunks=[b"hello ", b"world"],
            stderr_chunks=[b"warn"],
        )
        self.vm._ssh = FakeSSHClient(channel)

        stdout, stderr = self.vm.execute("echo hi")

        self.assertEqual(stdout, "hello world")
        self.assertEqual(stderr, "warn")
        self.assertIsNotNone(self.vm._ssh)

    def test_execute_timeout_disconnects_and_raises_timeout_error(self):
        channel = FakeChannel(block_stdout=True, block_stderr=True)
        ssh = FakeSSHClient(channel)
        self.vm._ssh = ssh

        with self.assertRaises(TimeoutError):
            self.vm.execute("sleep 999", timeout=0.01)

        self.assertTrue(channel.closed)
        self.assertTrue(ssh.closed)
        self.assertIsNone(self.vm._ssh)

    def test_execute_nonzero_exit_does_not_disconnect(self):
        channel = FakeChannel(
            stdout_chunks=[b"partial"],
            stderr_chunks=[b"failed"],
            exit_status=1,
        )
        ssh = FakeSSHClient(channel)
        self.vm._ssh = ssh

        stdout, stderr = self.vm.execute("false", timeout=5)

        self.assertEqual(stdout, "partial")
        self.assertEqual(stderr, "failed")
        self.assertFalse(ssh.closed)
        self.assertIs(self.vm._ssh, ssh)

    def test_execute_check_raises_for_nonzero_exit_without_disconnect(self):
        channel = FakeChannel(
            stdout_chunks=[b"partial"],
            stderr_chunks=[b"failed"],
            exit_status=2,
        )
        ssh = FakeSSHClient(channel)
        self.vm._ssh = ssh

        with self.assertRaises(subprocess.CalledProcessError) as raised:
            self.vm.execute("false", timeout=5, check=True)

        self.assertEqual(raised.exception.returncode, 2)
        self.assertEqual(raised.exception.output, "partial")
        self.assertEqual(raised.exception.stderr, "failed")
        self.assertFalse(ssh.closed)
        self.assertIs(self.vm._ssh, ssh)

    def test_execute_drains_stdout_and_stderr_in_parallel(self):
        channel = FakeChannel(
            stdout_chunks=[b"out"],
            stderr_chunks=[b"err"],
            sync_reads=True,
        )
        ssh = FakeSSHClient(channel)
        self.vm._ssh = ssh

        stdout, stderr = self.vm.execute("echo hi", timeout=0.05)

        self.assertEqual(stdout, "out")
        self.assertEqual(stderr, "err")
        self.assertFalse(ssh.closed)
        self.assertIs(self.vm._ssh, ssh)

    def test_execute_silent_returns_immediately_even_with_timeout(self):
        channel = FakeChannel(block_stdout=True)
        ssh = FakeSSHClient(channel)
        self.vm._ssh = ssh

        stdout, stderr = self.vm.execute("sleep 999", silent=True, timeout=0.01)

        self.assertIsNone(stdout)
        self.assertIsNone(stderr)
        self.assertIs(self.vm._ssh, ssh)

    def test_copy_without_timeout_keeps_existing_behavior(self):
        ssh = FakeSSHClient(FakeChannel())
        self.vm._ssh = ssh

        with patch("syzqemuctl.vm.SCPClient", RecordingSCPClient):
            self.vm.copy_to_vm("/tmp/local", "/remote/path")
            self.vm.copy_from_vm("/remote/file", "/tmp/local")

        self.assertEqual(len(RecordingSCPClient.instances), 2)
        self.assertEqual(
            RecordingSCPClient.instances[0].calls,
            [("put", "/tmp/local", "/remote/path", True)],
        )
        self.assertEqual(
            RecordingSCPClient.instances[1].calls,
            [("get", "/remote/file", "/tmp/local", True)],
        )
        self.assertIs(self.vm._ssh, ssh)

    def test_copy_timeout_disconnects_and_raises_timeout_error(self):
        for method_name, args in (
            ("copy_to_vm", ("/tmp/local", "/remote/path")),
            ("copy_from_vm", ("/remote/file", "/tmp/local")),
        ):
            with self.subTest(method=method_name):
                ssh = FakeSSHClient(FakeChannel())
                self.vm._ssh = ssh

                with patch("syzqemuctl.vm.SCPClient", BlockingSCPClient):
                    with self.assertRaises(TimeoutError):
                        getattr(self.vm, method_name)(*args, timeout=0.01)

                self.assertTrue(ssh.closed)
                self.assertIsNone(self.vm._ssh)

    def test_execute_can_recover_after_timeout_and_reconnect(self):
        timeout_ssh = FakeSSHClient(FakeChannel(block_stdout=True))
        self.vm._ssh = timeout_ssh

        with self.assertRaises(TimeoutError):
            self.vm.execute("sleep 999", timeout=0.01)

        recovered_ssh = FakeSSHClient(FakeChannel(stdout_chunks=[b"ok"], stderr_chunks=[]))
        self.vm._ssh = recovered_ssh

        stdout, stderr = self.vm.execute("echo ok", timeout=5)

        self.assertEqual(stdout, "ok")
        self.assertEqual(stderr, "")
        self.assertIs(self.vm._ssh, recovered_ssh)


if __name__ == "__main__":
    unittest.main()
