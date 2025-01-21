import os
import re
import signal
import subprocess
import paramiko
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Tuple
from scp import SCPClient
import time

from . import __title__

@dataclass
class VMConfig:
    """Virtual machine configuration"""
    DEFAULT_MEM = "4G"
    DEFAULT_SMP = 2
    
    kernel: str
    port: int
    memory: str = DEFAULT_MEM
    smp: int = DEFAULT_SMP
    
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
    
    def __init__(self, image_path: str):
        self.image_path = Path(image_path)
        self.pid_file = self.image_path / "vm.pid"
        self.log_file = self.image_path / "vm.log"
        self.boot_script = self.image_path / "boot.sh"
        self.screen_name = f"{__title__}-{self.image_path.name}"
        
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
        script_content = f"""#!/bin/bash
exec qemu-system-x86_64 \\
 -kernel {vm_conf.kernel}/arch/x86/boot/bzImage \\
 -append "console=ttyS0 root=/dev/sda debug earlyprintk=serial slub_debug=QUZ" \\
 -hda {self.image_path}/bullseye.img \\
 -net user,hostfwd=tcp::{vm_conf.port}-:22 -net nic \\
 -enable-kvm \\
 -nographic \\
 -m {vm_conf.memory} \\
 -smp {vm_conf.smp} \\
 -pidfile {self.pid_file} \\
 2>&1 | tee {self.log_file}
"""
        self.boot_script.write_text(script_content)
        self.boot_script.chmod(0o755)
        
    def start(self, kernel: str, port: int = None, mem: str = None, smp: int = None) -> bool:
        """Start virtual machine"""
        if self.is_running():
            print("VM is already running")
            return False
        
        # Load last boot vm config
        last_vm_conf = self.get_last_vm_config()
        if last_vm_conf:
            port = port or last_vm_conf.port
            mem = mem or last_vm_conf.memory
            smp = smp or last_vm_conf.smp
        else:
            port = port or self._find_available_port()
            mem = mem or VMConfig.DEFAULT_MEM
            smp = smp or VMConfig.DEFAULT_SMP
            
        # Generate boot script and run in screen
        self._generate_boot_script(VMConfig(kernel, port, mem, smp))
        
        try:
            # Clean up old screen session
            subprocess.run(
                ["screen", "-S", self.screen_name, "-X", "quit"],
                capture_output=True, text=True, check=True
            )
            print(f"Cleaned up old screen session: {self.screen_name}")
        except:
            pass

        try:
            # Start new screen session
            subprocess.run(
                ["screen", "-dmS", self.screen_name, str(self.boot_script)],
                check=True
            )
            
            # Wait for PID file (max 5 seconds)
            for _ in range(50):
                if self.pid_file.exists():
                    break
                time.sleep(0.1)
            
            if not self.is_running():
                raise RuntimeError("Failed to start VM: PID file not generated")
                
            print(f"Tip: Use 'screen -r {self.screen_name}' to view VM console")
            print(f"     Use Ctrl+A,D to detach from console")
            return True
        except Exception as e:
            print(f"Failed to start VM: {e}")
            return False
            
    def stop(self) -> bool:
        """Stop virtual machine"""
        if not self.pid_file.exists():
            return False
            
        try:
            # Disconnect SSH
            self.disconnect()
            
            # Read and terminate QEMU process
            pid = int(self.pid_file.read_text().strip())
            os.kill(pid, signal.SIGTERM)
            
            # Wait for process to end
            for _ in range(50):
                try:
                    os.kill(pid, 0)
                    time.sleep(0.1)
                except ProcessLookupError:
                    break
            
            # Force kill if needed
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
                
            return True
        except (ValueError, OSError) as e:
            print(f"Failed to stop VM: {e}")
            return False
            
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
                timeout=3  # Short timeout
            )
            ssh.close()
            return True
        except Exception:
            print("VM is not ready, please wait...")
            print("And you would possibly see errors from paramiko, which can be ignored.")
            return False
            
    def wait_until_ready(self, timeout: int = 120, interval: int = 60) -> bool:
        """Wait for VM to be fully started, return False on timeout"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.is_ready():
                return True
            time.sleep(interval)  # Check every interval seconds
        return False
            
    def connect(self, username: str = "root") -> bool:
        """Connect to VM"""
        if not self.is_running():
            print("VM is not running")
            return False
            
        if not self.is_ready():
            print("VM is starting, please wait...")
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
                timeout=10
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
            
    def execute(self, command: str) -> Tuple[str, str]:
        """Execute command in VM"""
        if not self._ssh:
            raise RuntimeError("Not connected to VM")
        
        if not self.is_ready():
            raise RuntimeError("VM is not ready, please wait...")
            
        stdin, stdout, stderr = self._ssh.exec_command(command)
        return stdout.read().decode(), stderr.read().decode()
        
    def copy_to_vm(self, local_path: str, remote_path: str) -> None:
        """Copy file to VM"""
        if not self._ssh:
            raise RuntimeError("Not connected to VM")
            
        with SCPClient(self._ssh.get_transport()) as scp:
            scp.put(local_path, remote_path, recursive=True)
            
    def copy_from_vm(self, remote_path: str, local_path: str) -> None:
        """Copy file from VM"""
        if not self._ssh:
            raise RuntimeError("Not connected to VM")
            
        with SCPClient(self._ssh.get_transport()) as scp:
            scp.get(remote_path, local_path, recursive=True)
            
    def __enter__(self):
        self.connect()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect() 