import os
import re
import signal
import subprocess
import logging
import socket
import threading
import paramiko
from pathlib import Path
from contextlib import contextmanager

def set_paramiko_logging(level: int = logging.CRITICAL) -> None:
    """Control paramiko log level. Use logging.WARNING or logging.DEBUG to re-enable."""
    logging.getLogger("paramiko").setLevel(level)


# Default: suppress noisy SSH error tracebacks during VM boot polling
set_paramiko_logging(logging.CRITICAL)

from dataclasses import dataclass
from typing import Optional, Tuple
from scp import SCPClient, SCPException
import time

from . import __title__
from . import utils

@dataclass
class VMConfig:
    """Virtual machine configuration"""
    DEFAULT_MEM = "4G"
    DEFAULT_SMP = 2
    
    kernel: str
    port: int
    memory: str = DEFAULT_MEM
    smp: int = DEFAULT_SMP
    snapshot: bool = False
    
    @classmethod
    def from_boot_script(cls, script_path: Path) -> Optional["VMConfig"]:
        """Parse configuration from boot script"""
        if not script_path.exists():
            return None
            
        try:
            content = script_path.read_text()
            # Extract config from qemu command line args
            kernel_match = re.search(r'-kernel ([^\s]+)/arch/x86', content)
            port_match = re.search(r'hostfwd=tcp::(\d+)-:22', content)
            mem_match = re.search(r'-m ([^\s]+)', content)
            smp_match = re.search(r'-smp ([^\s]+)', content)
            
            if not all([kernel_match, port_match]):
                return None
                
            return cls(
                kernel=kernel_match.group(1),
                port=int(port_match.group(1)),
                memory=mem_match.group(1) if mem_match else cls.DEFAULT_MEM,
                smp=int(smp_match.group(1)) if smp_match else cls.DEFAULT_SMP
            )
        except Exception:
            return None

class VM:
    """Virtual machine manager for running, stopping, and SSH operations"""
    PORT_START = 20000
    PORT_END = 30000
    
    def __init__(self, image_path: str, verbose: bool = False):
        self.image_path = Path(image_path)
        self.pid_file = self.image_path / "vm.pid"
        self.log_file = self.image_path / "vm.log"
        self.boot_script = self.image_path / "boot.sh"
        self.screen_name = f"{__title__}-{self.image_path.name}"
        self.verbose = verbose

        # SSH related attributes
        self._ssh = None
        self._scp = None
        self._key_file = self.image_path / "bullseye.id_rsa"
        
    def _find_available_port(self) -> Optional[int]:
        """Find an available port"""
        try:
            # Get all used ports using netstat
            result = subprocess.run(
                ["netstat", "-tuln"],
                capture_output=True,
                text=True,
                check=True
            )
            # Parse used ports
            used_ports = set()
            for line in result.stdout.splitlines():
                if "LISTEN" in line:
                    if match := re.search(r':(\d+)\s', line):
                        used_ports.add(int(match.group(1)))
                        
            # Get ports used by other running VMs
            for path in self.image_path.parent.iterdir():
                if path.is_dir():
                    vm = VM(str(path))
                    if vm_conf := vm.get_last_vm_config():
                        if vm.is_running():
                            used_ports.add(vm_conf.port)
                            
            # First try last used port
            if last_vm_conf := self.get_last_vm_config():
                if last_vm_conf.port not in used_ports:
                    return last_vm_conf.port
                    
            # Find new available port
            for port in range(self.PORT_START, self.PORT_END):
                if port not in used_ports:
                    return port
                    
        except subprocess.SubprocessError:
            pass
        return None
        
    def get_last_vm_config(self) -> Optional[VMConfig]:
        """Get last boot configuration"""
        return VMConfig.from_boot_script(self.boot_script)
        
    def _generate_boot_script(self, vm_conf: VMConfig) -> None:
        """Generate boot script"""
        snapshot_arg = " -snapshot \\\n" if vm_conf.snapshot else ""
        kernel_args = "net.ifnames=0 console=ttyS0 root=/dev/sda debug earlyprintk=serial slub_debug=QUZ"
        script_content = f"""#!/bin/bash
exec > >(tee {self.log_file}) 2>&1
exec qemu-system-x86_64 \\
 -kernel {vm_conf.kernel}/arch/x86/boot/bzImage \\
 -append "{kernel_args}" \\
 -hda {self.image_path}/bullseye.img \\
{snapshot_arg} -net user,hostfwd=tcp::{vm_conf.port}-:22 -net nic \\
 -enable-kvm \\
 -cpu host,migratable=off \\
 -nographic \\
 -m {vm_conf.memory} \\
 -smp {vm_conf.smp} \\
 -pidfile {self.pid_file}
"""
        self.boot_script.write_text(script_content)
        self.boot_script.chmod(0o755)
        
    def start(self, kernel: str = None, port: int = None, mem: str = None, smp: int = None, snapshot: bool = False) -> bool:
        """Start virtual machine"""
        if self.is_running():
            print("VM is already running")
            return False

        # Load last boot vm config
        last_vm_conf = self.get_last_vm_config()
        if last_vm_conf:
            kernel = kernel or last_vm_conf.kernel
            port = port or last_vm_conf.port
            mem = mem or last_vm_conf.memory
            smp = smp or last_vm_conf.smp
        else:
            port = port or self._find_available_port()
            mem = mem or VMConfig.DEFAULT_MEM
            smp = smp or VMConfig.DEFAULT_SMP
        assert kernel, "Kernel path is required for the first boot"
        # Generate boot script and run in screen
        self._generate_boot_script(VMConfig(kernel, port, mem, smp, snapshot))
        utils.log_info(f"Write boot script to {self.boot_script} with kernel={kernel}, port={port}, mem={mem}, smp={smp}, snapshot={snapshot}", self.verbose)
        
        try:
            # Clean up old screen session
            subprocess.run(
                ["screen", "-S", self.screen_name, "-X", "quit"],
                capture_output=True, text=True, check=True
            )
            utils.log_info(f"Cleaned up old screen session: {self.screen_name}", self.verbose)
        except Exception:
            pass

        try:
            # Start new screen session
            subprocess.run(
                ["screen", "-dmS", self.screen_name, str(self.boot_script)],
                check=True
            )

            # Wait for PID file and process readiness (max 30 seconds)
            deadline = time.time() + 30
            while time.time() < deadline:
                if self.pid_file.exists() and self.is_running():
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError("Failed to start VM: PID file not generated")

            utils.log_info(f"Tip: Use 'screen -r {self.screen_name}' to view VM console", self.verbose)
            utils.log_info(f"     Use Ctrl+A,D to detach from console", self.verbose)
            return True
        except Exception as e:
            print(f"Failed to start VM: {e}")
            # Best-effort cleanup on failure
            try:
                subprocess.run(
                    ["screen", "-S", self.screen_name, "-X", "quit"],
                    capture_output=True, timeout=5
                )
            except Exception:
                pass
            try:
                if self.pid_file.exists():
                    self.pid_file.unlink()
            except Exception:
                pass
            return False
            
    def _screen_session_ids(self) -> list[str]:
        """Return screen session ids that belong to this VM"""
        try:
            result = subprocess.run(
                ["screen", "-ls"],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except Exception:
            return []

        sessions = []
        for line in result.stdout.splitlines():
            if self.screen_name not in line:
                continue
            token = line.strip().split()
            if token:
                sessions.append(token[0])
        return sessions

    def _qemu_pids_for_image(self) -> list[int]:
        """Return qemu-system pids whose cmdline points at this VM image"""
        image_file = self.image_path / "bullseye.img"
        candidates = {str(image_file), str(image_file.resolve())}
        pids = []

        for proc_dir in Path("/proc").iterdir():
            if not proc_dir.name.isdigit():
                continue
            try:
                cmdline = (proc_dir / "cmdline").read_bytes().split(b"\0")
            except (FileNotFoundError, ProcessLookupError, PermissionError, OSError):
                continue
            if not cmdline or not cmdline[0]:
                continue

            executable = Path(cmdline[0].decode(errors="ignore")).name
            if not executable.startswith("qemu-system-"):
                continue

            args = {arg.decode(errors="ignore") for arg in cmdline[1:] if arg}
            if candidates.intersection(args):
                pids.append(int(proc_dir.name))

        return pids

    def _runtime_is_clean(self, port: Optional[int] = None) -> bool:
        """Check whether all runtime artifacts for this VM have been removed"""
        if self._screen_session_ids():
            return False
        if self._qemu_pids_for_image():
            return False
        if self.pid_file.exists():
            return False
        if port is None:
            return True

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.2)
                return sock.connect_ex(("127.0.0.1", port)) != 0
        except OSError:
            return True

    def _terminate_runtime_once(self, force: bool = False) -> None:
        """Best-effort cleanup pass for this VM runtime"""
        try:
            self.disconnect()
        except Exception:
            pass

        pids_to_kill = set()
        if self.pid_file.exists():
            try:
                pids_to_kill.add(int(self.pid_file.read_text().strip()))
            except (ValueError, OSError):
                pass

        if force:
            pids_to_kill.update(self._qemu_pids_for_image())

        for pid in pids_to_kill:
            utils.kill_process(pid)

        for session_id in self._screen_session_ids():
            try:
                subprocess.run(
                    ["screen", "-S", session_id, "-X", "quit"],
                    capture_output=True,
                    timeout=5,
                )
            except Exception:
                pass

        try:
            if self.pid_file.exists():
                self.pid_file.unlink()
        except Exception:
            pass

    def stop(self, wait: bool = False, timeout: int = 20, force: bool = False) -> bool:
        """Stop virtual machine and optionally wait for runtime cleanup"""
        vm_conf = self.get_last_vm_config()
        port = vm_conf.port if vm_conf else None

        self._terminate_runtime_once(force=force)

        if not wait:
            return self._runtime_is_clean(port=port)

        start_time = time.monotonic()
        while time.monotonic() - start_time < timeout:
            if self._runtime_is_clean(port=port):
                return True
            self._terminate_runtime_once(force=force)
            time.sleep(0.5)

        return self._runtime_is_clean(port=port)

    def cleanup_runtime(self, timeout: int = 20) -> bool:
        """Force cleanup all runtime artifacts and wait until they disappear"""
        return self.stop(wait=True, timeout=timeout, force=True)
            
    def is_running(self) -> bool:
        """Check if VM is running"""
        try:
            return self.pid_file.exists() and os.kill(int(self.pid_file.read_text().strip()), 0) is None
        except (ValueError, ProcessLookupError, OSError):
            return False
            
    def is_ready(self) -> bool:
        """Check if VM is fully started (SSH available)"""
        if not self.is_running():
            return False
            
        try:
            vm_conf = self.get_last_vm_config()
            if not vm_conf:
                return False
                
            # Try SSH connection
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(
                hostname="localhost",
                port=vm_conf.port,
                username="root",
                key_filename=str(self._key_file),
                timeout=5,
                banner_timeout=5,
                auth_timeout=5,
            )
            ssh.close()
            return True
        except Exception:
            return False
            
    def wait_until_ready(self, timeout: int = 120, interval: int = 3) -> bool:
        """Wait for VM to be fully started, return False on timeout"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.is_ready():
                return True
            time.sleep(interval)
        return False
            
    def connect(self, username: str = "root") -> bool:
        """Connect to VM"""
        if not self.is_running():
            print("VM is not running")
            return False
            
        if not self.is_ready():
            utils.log_info("VM is starting, please wait...", self.verbose)
            return False
            
        if not self._key_file.exists():
            print(f"SSH key not found: {self._key_file}")
            return False
            
        try:
            vm_conf = self.get_last_vm_config()
            if not vm_conf:
                print("Failed to get VM config")
                return False
                
            self._ssh = paramiko.SSHClient()
            self._ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self._ssh.connect(
                hostname="localhost",
                port=vm_conf.port,
                username=username,
                key_filename=str(self._key_file),
                timeout=15,
                banner_timeout=10,
                auth_timeout=10,
            )
            return True
        except Exception as e:
            print(f"Failed to connect to VM: {e}")
            return False
            
    def disconnect(self) -> None:
        """Disconnect from VM"""
        if self._ssh:
            self._ssh.close()
            self._ssh = None

    def _abort_ssh(self, channel=None) -> None:
        """Best-effort hard stop for the current SSH connection"""
        if channel is not None:
            try:
                channel.close()
            except Exception:
                pass

        transport = None
        if self._ssh:
            try:
                transport = self._ssh.get_transport()
            except Exception:
                transport = None
        sock = getattr(transport, "sock", None) if transport else None

        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass

        if transport is not None:
            try:
                transport.close()
            except Exception:
                pass

        self.disconnect()

    def _is_ssh_io_error(self, exc: Exception) -> bool:
        """Return True when the exception suggests the SSH connection is no longer healthy"""
        return isinstance(exc, (socket.timeout, EOFError, ConnectionError, paramiko.SSHException, SCPException))

    @contextmanager
    def _timeout_guard(self, timeout: Optional[int], channel_getter=None):
        """Abort the SSH connection when an operation exceeds the timeout"""
        if timeout is None:
            yield lambda: False
            return

        expired = threading.Event()
        finished = threading.Event()
        lock = threading.Lock()

        def on_timeout():
            with lock:
                if finished.is_set():
                    return
                expired.set()
                channel = channel_getter() if channel_getter is not None else None
                self._abort_ssh(channel)

        timer = threading.Timer(timeout, on_timeout)
        timer.daemon = True
        timer.start()
        try:
            yield expired.is_set
        finally:
            with lock:
                finished.set()
                timer.cancel()

    def execute(self, command: str, silent: bool = False, timeout: Optional[int] = None) -> Tuple[str, str]:
        """Execute command in VM"""
        if not self._ssh:
            raise RuntimeError("Not connected to VM")

        channel_holder = {"channel": None}
        outputs = {"stdout": b"", "stderr": b""}
        errors = {"stdout": None, "stderr": None}

        def safe_decode(data: bytes) -> str:
            try:
                return data.decode("utf-8")
            except UnicodeDecodeError:
                try:
                    return data.decode("utf-8", errors="backslashreplace")
                except UnicodeDecodeError:
                    return data.decode("utf-8", errors="replace")

        def read_stream(name: str, stream) -> None:
            try:
                outputs[name] = stream.read()
            except Exception as exc:
                errors[name] = exc

        with self._timeout_guard(timeout, lambda: channel_holder["channel"]) as timed_out:
            try:
                _stdin, stdout, stderr = self._ssh.exec_command(command)
                channel_holder["channel"] = stdout.channel

                if silent:
                    return None, None

                readers = [
                    threading.Thread(target=read_stream, args=("stdout", stdout)),
                    threading.Thread(target=read_stream, args=("stderr", stderr)),
                ]
                for reader in readers:
                    reader.daemon = True
                    reader.start()
                for reader in readers:
                    reader.join()

                if timed_out():
                    raise TimeoutError(f"Command timed out after {timeout} seconds")

                for name in ("stdout", "stderr"):
                    if errors[name] is None:
                        continue
                    if timed_out():
                        raise TimeoutError(f"Command timed out after {timeout} seconds") from errors[name]
                    raise errors[name]

                stdout.channel.recv_exit_status()
                if timed_out():
                    raise TimeoutError(f"Command timed out after {timeout} seconds")

                return safe_decode(outputs["stdout"]), safe_decode(outputs["stderr"])
            except TimeoutError:
                self._abort_ssh(channel_holder["channel"])
                raise
            except Exception as exc:
                if timed_out():
                    raise TimeoutError(f"Command timed out after {timeout} seconds") from exc
                if self._is_ssh_io_error(exc):
                    self._abort_ssh(channel_holder["channel"])
                raise

    def copy_to_vm(self, local_path: str, remote_path: str, timeout: Optional[int] = None) -> None:
        """Copy file to VM"""
        if not self._ssh:
            raise RuntimeError("Not connected to VM")

        transport = self._ssh.get_transport()
        if transport is None:
            raise RuntimeError("SSH transport is not available")

        with self._timeout_guard(timeout) as timed_out:
            try:
                with SCPClient(transport) as scp:
                    scp.put(local_path, remote_path, recursive=True)
                if timed_out():
                    raise TimeoutError(f"SCP put timed out after {timeout} seconds")
            except TimeoutError:
                self._abort_ssh()
                raise
            except Exception as exc:
                if timed_out():
                    raise TimeoutError(f"SCP put timed out after {timeout} seconds") from exc
                if self._is_ssh_io_error(exc):
                    self._abort_ssh()
                raise

    def copy_from_vm(self, remote_path: str, local_path: str, timeout: Optional[int] = None) -> None:
        """Copy file from VM"""
        if not self._ssh:
            raise RuntimeError("Not connected to VM")

        transport = self._ssh.get_transport()
        if transport is None:
            raise RuntimeError("SSH transport is not available")

        with self._timeout_guard(timeout) as timed_out:
            try:
                with SCPClient(transport) as scp:
                    scp.get(remote_path, local_path, recursive=True)
                if timed_out():
                    raise TimeoutError(f"SCP get timed out after {timeout} seconds")
            except TimeoutError:
                self._abort_ssh()
                raise
            except Exception as exc:
                if timed_out():
                    raise TimeoutError(f"SCP get timed out after {timeout} seconds") from exc
                if self._is_ssh_io_error(exc):
                    self._abort_ssh()
                raise
            
    def __enter__(self):
        self.connect()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect() 
