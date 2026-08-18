import re
import shlex
import subprocess
import logging
import math
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

from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple
from scp import SCPClient, SCPException
import time

from . import utils

@dataclass
class VMConfig:
    """Virtual machine configuration"""
    DEFAULT_MEM = "4G"
    DEFAULT_SMP = 2
    DEFAULT_KERNEL_ARGS = (
        "net.ifnames=0 console=ttyS0 root=/dev/sda debug "
        "earlyprintk=serial slub_debug=QUZ"
    )
    
    kernel: str
    port: int
    memory: str = DEFAULT_MEM
    smp: int = DEFAULT_SMP
    snapshot: bool = False
    kernel_args: str = DEFAULT_KERNEL_ARGS
    
    @classmethod
    def from_boot_script(cls, script_path: Path) -> Optional["VMConfig"]:
        """Parse configuration from boot script"""
        if not script_path.exists():
            return None
            
        try:
            content = script_path.read_text()
            command_match = re.search(
                r"(?m)^exec\s+qemu-system-[^\s]+(?P<args>.*)",
                content.replace("\\\n", " "),
                re.DOTALL,
            )
            if command_match is None:
                return None

            args = shlex.split(command_match.group("args"))

            def argument_value(name: str) -> Optional[str]:
                try:
                    return args[args.index(name) + 1]
                except (ValueError, IndexError):
                    return None

            kernel_image = argument_value("-kernel")
            kernel_suffix = "/arch/x86/boot/bzImage"
            network_args = [
                args[index + 1]
                for index, value in enumerate(args[:-1])
                if value == "-net"
            ]
            port_match = None
            for value in network_args:
                match = re.search(r"hostfwd=tcp::(\d+)-:22", value)
                if match is not None:
                    port_match = match
                    break
            if (
                kernel_image is None
                or not kernel_image.endswith(kernel_suffix)
                or port_match is None
            ):
                return None

            memory = argument_value("-m") or cls.DEFAULT_MEM
            smp = argument_value("-smp") or str(cls.DEFAULT_SMP)
            parsed_kernel_args = argument_value("-append")
            return cls(
                kernel=kernel_image[:-len(kernel_suffix)],
                port=int(port_match.group(1)),
                memory=memory,
                smp=int(smp),
                snapshot="-snapshot" in args,
                kernel_args=(
                    parsed_kernel_args
                    if parsed_kernel_args is not None
                    else cls.DEFAULT_KERNEL_ARGS
                ),
            )
        except (OSError, ValueError):
            return None


@dataclass
class RuntimeDiagnostics:
    """Read-only snapshot of runtime resources associated with one VM image."""

    image_path: str
    screen_sessions: Optional[List[str]]
    qemu_pids: Optional[List[int]]
    pidfile_exists: bool
    pidfile_pid: Optional[int]
    pidfile_pid_valid: Optional[bool]
    port: Optional[int]
    port_open: Optional[bool]
    port_checked: bool
    log_file_exists: bool
    runtime_clean: Optional[bool]
    errors: List[str]

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable representation."""
        return asdict(self)

    def summary(self) -> str:
        """Return a compact human-readable summary."""
        runtime = {
            True: "clean",
            False: "dirty",
            None: "unknown",
        }[self.runtime_clean]
        screens = (
            "unknown"
            if self.screen_sessions is None
            else ",".join(self.screen_sessions) or "none"
        )
        qemu = (
            "unknown"
            if self.qemu_pids is None
            else ",".join(str(pid) for pid in self.qemu_pids) or "none"
        )
        if not self.pidfile_exists:
            pidfile = "absent"
        elif self.pidfile_pid is None:
            pidfile = "invalid"
        elif self.pidfile_pid_valid is True:
            pidfile = f"{self.pidfile_pid} (valid)"
        elif self.pidfile_pid_valid is False:
            pidfile = f"{self.pidfile_pid} (stale)"
        else:
            pidfile = f"{self.pidfile_pid} (unverified)"

        if self.port is None:
            port = "unavailable"
        elif not self.port_checked:
            port = f"{self.port} (not checked)"
        elif self.port_open is None:
            port = f"{self.port} (unknown)"
        else:
            port = f"{self.port} ({'open' if self.port_open else 'closed'})"

        parts = [
            f"runtime={runtime}",
            f"screen={screens}",
            f"qemu={qemu}",
            f"pidfile={pidfile}",
            f"port={port}",
            f"log={'present' if self.log_file_exists else 'absent'}",
        ]
        if self.errors:
            parts.append(f"errors={'; '.join(self.errors)}")
        return "; ".join(parts)

class VM:
    """Virtual machine manager for running, stopping, and SSH operations"""
    PORT_START = 20000
    PORT_END = 30000
    PROC_ROOT = Path("/proc")
    
    def __init__(self, image_path: str, verbose: bool = False):
        self.image_path = Path(image_path).expanduser().resolve()
        self.pid_file = self.image_path / "vm.pid"
        self.log_file = self.image_path / "vm.log"
        self.boot_script = self.image_path / "boot.sh"
        self.screen_name = utils.make_screen_name(self.image_path)
        self.verbose = verbose

        # SSH related attributes
        self._ssh = None
        self._scp = None
        self._key_file = self.image_path / "bullseye.id_rsa"
        
    def _find_available_port(self) -> Optional[int]:
        """Find an available port"""
        candidates = []
        last_vm_conf = self.get_last_vm_config()
        if last_vm_conf is not None:
            candidates.append(last_vm_conf.port)
        candidates.extend(
            port
            for port in range(self.PORT_START, self.PORT_END)
            if port not in candidates
        )

        for port in candidates:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.bind(("0.0.0.0", port))
                    return port
            except OSError:
                continue
        return None
        
    def get_last_vm_config(self) -> Optional[VMConfig]:
        """Get last boot configuration"""
        return VMConfig.from_boot_script(self.boot_script)
        
    def _generate_boot_script(self, vm_conf: VMConfig) -> None:
        """Generate boot script"""
        qemu_options = [
            ["-kernel", str(Path(vm_conf.kernel) / "arch/x86/boot/bzImage")],
            ["-append", vm_conf.kernel_args],
            ["-hda", str(self.image_path / "bullseye.img")],
            ["-net", f"user,hostfwd=tcp::{vm_conf.port}-:22"],
            ["-net", "nic"],
            ["-enable-kvm"],
            ["-cpu", "host,migratable=off"],
            ["-nographic"],
            ["-m", vm_conf.memory],
            ["-smp", str(vm_conf.smp)],
            ["-pidfile", str(self.pid_file)],
        ]
        if vm_conf.snapshot:
            qemu_options.append(["-snapshot"])

        command_parts = ["qemu-system-x86_64"]
        command_parts.extend(
            " ".join(shlex.quote(argument) for argument in option)
            for option in qemu_options
        )
        qemu_command = " \\\n  ".join(command_parts)
        script_content = (
            "#!/bin/bash\n"
            f"exec > >(tee -- {shlex.quote(str(self.log_file))}) 2>&1\n"
            f"exec {qemu_command}\n"
        )
        self.boot_script.write_text(script_content)
        self.boot_script.chmod(0o755)
        
    @utils.locked_image_operation
    def start(
        self,
        kernel: Optional[str] = None,
        port: Optional[int] = None,
        mem: Optional[str] = None,
        smp: Optional[int] = None,
        snapshot: bool = False,
        kernel_args: Optional[str] = None,
        extra_kernel_args: Optional[str] = None,
    ) -> bool:
        """Start virtual machine"""
        if not self.image_path.is_dir():
            print(f"Image directory not found: {self.image_path}")
            return False
        if self.is_running():
            print("VM is already running")
            return False

        # Load last boot vm config
        last_vm_conf = self.get_last_vm_config()
        if last_vm_conf is not None:
            kernel = kernel if kernel is not None else last_vm_conf.kernel
            mem = mem if mem is not None else last_vm_conf.memory
            smp = smp if smp is not None else last_vm_conf.smp

        if kernel is None:
            print("Kernel path is required for the first boot")
            return False
        mem = mem if mem is not None else VMConfig.DEFAULT_MEM
        smp = smp if smp is not None else VMConfig.DEFAULT_SMP
        if smp <= 0:
            print("CPU cores must be greater than zero")
            return False

        if not self._stop_runtime(
            wait=True,
            timeout=20,
            force=False,
            check_port=False,
        ):
            print("Failed to clean up the previous VM runtime")
            return False

        port = port if port is not None else self._find_available_port()
        if port is None or not 1 <= port <= 65535:
            print("No available SSH port found")
            return False

        if kernel_args is not None:
            resolved_kernel_args = kernel_args
        elif last_vm_conf is not None:
            resolved_kernel_args = last_vm_conf.kernel_args
        else:
            resolved_kernel_args = VMConfig.DEFAULT_KERNEL_ARGS
        if extra_kernel_args:
            resolved_kernel_args = (
                f"{resolved_kernel_args} {extra_kernel_args}".strip()
            )

        # Generate boot script and run in screen
        vm_conf = VMConfig(
            kernel=kernel,
            port=port,
            memory=mem,
            smp=smp,
            snapshot=snapshot,
            kernel_args=resolved_kernel_args,
        )
        try:
            self._generate_boot_script(vm_conf)
            utils.log_info(
                f"Write boot script to {self.boot_script} with kernel={kernel}, "
                f"port={port}, mem={mem}, smp={smp}, snapshot={snapshot}, "
                f"kernel_args={resolved_kernel_args}",
                self.verbose,
            )

            # Start new screen session
            subprocess.run(
                ["screen", "-dmS", self.screen_name, str(self.boot_script)],
                check=True
            )

            # Wait for PID file and process readiness (max 30 seconds)
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if self.pid_file.exists() and self.is_running():
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError("Failed to start VM: PID file not generated")

            utils.log_info(f"Tip: Use 'screen -r {self.screen_name}' to view VM console", self.verbose)
            utils.log_info("     Use Ctrl+A,D to detach from console", self.verbose)
            return True
        except Exception as e:
            print(f"Failed to start VM: {e}")
            self._stop_runtime(
                wait=True,
                timeout=20,
                force=True,
                check_port=False,
            )
            return False
            
    def _screen_session_ids(
        self,
        timeout: float = 5.0,
    ) -> Optional[List[str]]:
        """Return screen session ids that belong to this VM"""
        if timeout <= 0:
            return None
        try:
            result = subprocess.run(
                ["screen", "-ls"],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except Exception:
            return None

        sessions = []
        for line in result.stdout.splitlines():
            token = line.strip().split()
            if not token:
                continue
            session_id = token[0]
            session_name = session_id.split(".", 1)[1] if "." in session_id else session_id
            if session_name == self.screen_name:
                sessions.append(session_id)
        return sessions

    def _qemu_pids_for_image(
        self,
        candidate_pids: Optional[List[int]] = None,
        deadline: Optional[float] = None,
        strict: bool = False,
    ) -> List[int]:
        """Return qemu-system pids whose cmdline points at this VM image"""
        image_file = (self.image_path / "bullseye.img").resolve()
        pids = []

        proc_dirs: Iterable[Path]
        if candidate_pids is None:
            proc_dirs = self.PROC_ROOT.iterdir()
        else:
            proc_dirs = [
                self.PROC_ROOT / str(pid)
                for pid in candidate_pids
            ]

        for proc_dir in proc_dirs:
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError("QEMU process inspection timed out")
            if not proc_dir.name.isdigit():
                continue
            try:
                cmdline = (proc_dir / "cmdline").read_bytes().split(b"\0")
            except PermissionError:
                if strict:
                    raise
                continue
            except (FileNotFoundError, ProcessLookupError, OSError):
                continue
            if not cmdline or not cmdline[0]:
                continue

            executable = Path(cmdline[0].decode(errors="ignore")).name
            if not executable.startswith("qemu-system-"):
                continue

            args = [arg.decode(errors="ignore") for arg in cmdline[1:] if arg]
            cwd_link = proc_dir / "cwd"
            try:
                cwd = cwd_link.resolve() if cwd_link.exists() else None
            except (OSError, RuntimeError):
                cwd = None

            def references_image(path: str) -> bool:
                candidate = Path(path)
                if not candidate.is_absolute():
                    if cwd is None:
                        return False
                    candidate = cwd / candidate
                try:
                    return candidate.resolve() == image_file
                except (OSError, RuntimeError):
                    return False

            image_arguments = []
            for index, argument in enumerate(args[:-1]):
                value = args[index + 1]
                if argument in ("-hda", "-hdb", "-hdc", "-hdd"):
                    image_arguments.append(value)
                elif argument in ("-drive", "-blockdev"):
                    for part in value.split(","):
                        if part.startswith("file="):
                            image_arguments.append(part[5:])
                        elif part.startswith("filename="):
                            image_arguments.append(part[9:])

            matches_image = any(references_image(path) for path in image_arguments)
            if matches_image:
                pids.append(int(proc_dir.name))

        if deadline is not None and time.monotonic() >= deadline:
            raise TimeoutError("QEMU process inspection timed out")
        return pids

    def _pidfile_qemu_pid(self) -> Optional[int]:
        """Return the pidfile PID only when it belongs to this VM's QEMU"""
        if not self.pid_file.exists():
            return None
        try:
            pid = int(self.pid_file.read_text().strip())
        except (ValueError, OSError):
            return None
        return pid if self._qemu_pids_for_image([pid]) else None

    def _runtime_is_clean(
        self,
        port: Optional[int] = None,
        deadline: Optional[float] = None,
    ) -> bool:
        """Check whether all runtime artifacts for this VM have been removed"""
        screen_timeout = 5.0
        if deadline is not None:
            screen_timeout = max(deadline - time.monotonic(), 0)
            if screen_timeout <= 0:
                return False
        screen_sessions = self._screen_session_ids(
            timeout=min(screen_timeout, 5.0)
        )
        if screen_sessions is None or screen_sessions:
            return False
        if deadline is not None and time.monotonic() >= deadline:
            return False
        if self._qemu_pids_for_image():
            return False
        if deadline is not None and time.monotonic() >= deadline:
            return False
        if self.pid_file.exists():
            return False
        if port is None:
            return True

        socket_timeout = 0.2
        if deadline is not None:
            socket_timeout = min(
                socket_timeout,
                max(deadline - time.monotonic(), 0),
            )
            if socket_timeout <= 0:
                return False
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(socket_timeout)
                return sock.connect_ex(("127.0.0.1", port)) != 0
        except OSError:
            return True

    def _terminate_runtime_once(
        self,
        force: bool = False,
        deadline: Optional[float] = None,
    ) -> None:
        """Best-effort cleanup pass for this VM runtime"""
        try:
            self.disconnect()
        except Exception:
            pass

        pids_to_kill = set()
        pidfile_pid = self._pidfile_qemu_pid()
        if pidfile_pid is not None:
            pids_to_kill.add(pidfile_pid)

        if force:
            pids_to_kill.update(self._qemu_pids_for_image())

        kill_results = {}
        for pid in pids_to_kill:
            if deadline is None:
                kill_results[pid] = utils.kill_process(pid)
                continue
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            kill_results[pid] = utils.kill_process(pid, timeout=remaining)

        screen_timeout = 5.0
        if deadline is not None:
            screen_timeout = min(screen_timeout, max(deadline - time.monotonic(), 0))
        session_ids = (
            self._screen_session_ids(timeout=screen_timeout)
            if screen_timeout > 0
            else None
        )
        for session_id in session_ids or []:
            try:
                command_timeout = 5.0
                if deadline is not None:
                    command_timeout = min(
                        command_timeout,
                        max(deadline - time.monotonic(), 0),
                    )
                    if command_timeout <= 0:
                        break
                subprocess.run(
                    ["screen", "-S", session_id, "-X", "quit"],
                    capture_output=True,
                    timeout=command_timeout,
                )
            except Exception:
                pass

        try:
            pidfile_can_be_removed = (
                pidfile_pid is None or kill_results.get(pidfile_pid, False)
            )
            if pidfile_can_be_removed and self.pid_file.exists():
                self.pid_file.unlink()
        except Exception:
            pass

    def _stop_runtime(
        self,
        wait: bool,
        timeout: int,
        force: bool,
        check_port: bool = True,
    ) -> bool:
        vm_conf = self.get_last_vm_config() if check_port else None
        port = vm_conf.port if vm_conf is not None else None
        deadline = time.monotonic() + max(timeout, 0) if wait else None
        self._terminate_runtime_once(force=force, deadline=deadline)

        if not wait:
            return self._runtime_is_clean(port=port)

        assert deadline is not None
        while time.monotonic() < deadline:
            if self._runtime_is_clean(port=port, deadline=deadline):
                return True
            self._terminate_runtime_once(force=force, deadline=deadline)
            remaining = deadline - time.monotonic()
            if remaining > 0:
                time.sleep(min(0.5, remaining))

        return False

    @utils.locked_image_operation
    def stop(self, wait: bool = False, timeout: int = 20, force: bool = False) -> bool:
        """Stop virtual machine and optionally wait for runtime cleanup"""
        return self._stop_runtime(wait, timeout, force)

    def cleanup_runtime(self, timeout: int = 20) -> bool:
        """Force cleanup all runtime artifacts and wait until they disappear"""
        return self.stop(wait=True, timeout=timeout, force=True)

    def runtime_diagnostics(
        self,
        timeout: float = 5.0,
        check_port: bool = True,
    ) -> RuntimeDiagnostics:
        """Inspect this VM's runtime resources without changing their state."""
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be a finite value greater than zero")

        deadline = time.monotonic() + timeout
        errors = []

        try:
            log_file_exists = self.log_file.exists()
        except OSError as error:
            log_file_exists = False
            errors.append(f"log file inspection failed: {error}")

        pidfile_known = True
        try:
            pidfile_exists = self.pid_file.exists()
        except OSError as error:
            pidfile_exists = False
            pidfile_known = False
            errors.append(f"pidfile inspection failed: {error}")

        pidfile_pid = None
        if pidfile_exists:
            try:
                pidfile_pid = int(self.pid_file.read_text().strip())
            except ValueError:
                errors.append("pidfile contains an invalid PID")
            except OSError as error:
                pidfile_known = False
                errors.append(f"pidfile read failed: {error}")

        boot_script_exists = False
        port_state_known = True
        vm_conf = None
        try:
            boot_script_exists = self.boot_script.exists()
            vm_conf = self.get_last_vm_config()
            if check_port and boot_script_exists and vm_conf is None:
                port_state_known = False
                errors.append("saved VM configuration could not be parsed")
        except OSError as error:
            port_state_known = not check_port
            errors.append(f"saved VM configuration inspection failed: {error}")
        port = vm_conf.port if vm_conf is not None else None

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            screen_sessions = None
            errors.append("screen inspection timed out")
        else:
            screen_sessions = self._screen_session_ids(
                timeout=min(remaining, 5.0)
            )
            if screen_sessions is None:
                errors.append("screen inspection failed or timed out")

        try:
            qemu_pids = self._qemu_pids_for_image(
                deadline=deadline,
                strict=True,
            )
        except TimeoutError:
            qemu_pids = None
            errors.append("QEMU process inspection timed out")
        except OSError as error:
            qemu_pids = None
            errors.append(f"QEMU process inspection failed: {error}")

        pidfile_pid_valid = None
        if pidfile_exists and pidfile_known:
            if pidfile_pid is None:
                pidfile_pid_valid = False
            elif qemu_pids is not None:
                pidfile_pid_valid = pidfile_pid in qemu_pids

        port_open = None
        port_checked = check_port and port is not None
        if port_checked:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                errors.append("SSH port inspection timed out")
            else:
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                        sock.settimeout(min(remaining, 0.2))
                        port_open = sock.connect_ex(("127.0.0.1", port)) == 0
                except OSError as error:
                    errors.append(f"SSH port inspection failed: {error}")

        dirty = (
            bool(screen_sessions)
            or bool(qemu_pids)
            or pidfile_exists
            or port_open is True
        )
        unknown = (
            screen_sessions is None
            or qemu_pids is None
            or not pidfile_known
            or not port_state_known
            or (port_checked and port_open is None)
        )
        runtime_clean = False if dirty else None if unknown else True

        return RuntimeDiagnostics(
            image_path=str(self.image_path),
            screen_sessions=screen_sessions,
            qemu_pids=qemu_pids,
            pidfile_exists=pidfile_exists,
            pidfile_pid=pidfile_pid,
            pidfile_pid_valid=pidfile_pid_valid,
            port=port,
            port_open=port_open,
            port_checked=port_checked,
            log_file_exists=log_file_exists,
            runtime_clean=runtime_clean,
            errors=errors,
        )
            
    def is_running(self) -> bool:
        """Check if VM is running"""
        return bool(self._qemu_pids_for_image())
            
    def is_ready(self) -> bool:
        """Check if VM is fully started (SSH available)"""
        if not self.is_running():
            return False
            
        ssh = None
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
            return True
        except Exception:
            return False
        finally:
            if ssh is not None:
                try:
                    ssh.close()
                except Exception:
                    pass
            
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
            
        if not self._key_file.exists():
            print(f"SSH key not found: {self._key_file}")
            return False
            
        ssh = None
        try:
            vm_conf = self.get_last_vm_config()
            if not vm_conf:
                print("Failed to get VM config")
                return False
                
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(
                hostname="localhost",
                port=vm_conf.port,
                username=username,
                key_filename=str(self._key_file),
                timeout=15,
                banner_timeout=10,
                auth_timeout=10,
            )
            old_ssh = self._ssh
            self._ssh = ssh
            if old_ssh is not None:
                try:
                    old_ssh.close()
                except Exception:
                    pass
            return True
        except Exception as e:
            if ssh is not None:
                try:
                    ssh.close()
                except Exception:
                    pass
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

    def execute(
        self,
        command: str,
        silent: bool = False,
        timeout: Optional[int] = None,
        check: bool = False,
    ) -> Tuple[str, str]:
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

                returncode = stdout.channel.recv_exit_status()
                if timed_out():
                    raise TimeoutError(f"Command timed out after {timeout} seconds")

                decoded_stdout = safe_decode(outputs["stdout"])
                decoded_stderr = safe_decode(outputs["stderr"])
                if check and returncode != 0:
                    raise subprocess.CalledProcessError(
                        returncode,
                        command,
                        output=decoded_stdout,
                        stderr=decoded_stderr,
                    )
                return decoded_stdout, decoded_stderr
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
        if not self.connect():
            raise ConnectionError("Failed to connect to VM")
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect() 
