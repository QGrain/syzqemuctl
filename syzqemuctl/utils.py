import fcntl
import hashlib
import requests
import re
from packaging import version
from typing import Iterator, Optional, Tuple
from contextlib import contextmanager
from functools import lru_cache, wraps
from pathlib import Path
import os
import signal
import time
import subprocess

from ._version import __title__
from .config import global_conf


def make_screen_name(image_path: Path, suffix: Optional[str] = None) -> str:
    """Build a shell-safe, path-specific screen session name."""
    path = Path(image_path).expanduser().resolve()
    image_id = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:8]
    image_label = re.sub(
        r"[^A-Za-z0-9_.-]+",
        "_",
        path.name,
    ).strip("._-")
    parts = [__title__, image_label[:48] or "image", image_id]
    if suffix:
        parts.append(suffix)
    return "-".join(parts)


@contextmanager
def image_operation_lock(image_path: Path) -> Iterator[None]:
    """Serialize destructive operations for one image across processes."""
    path = Path(image_path).expanduser().resolve()
    image_id = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:16]
    lock_file = path.parent / f".{__title__}-{image_id}.lock"
    with lock_file.open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def locked_image_operation(method):
    """Serialize a VM method using its image path."""
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with image_operation_lock(self.image_path):
            return method(self, *args, **kwargs)

    return wrapped


def log_info(msg: str, verbose: bool = True) -> None:
    """Print informational message only when verbose is enabled"""
    if verbose:
        print(msg)

def log_error(msg: str) -> None:
    """Always print error messages"""
    print(msg)

def format_size(size: int) -> str:
    """Format file size"""
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"

@lru_cache(maxsize=1)
def check_latest_version() -> Tuple[Optional[str], Optional[str]]:
    """
    Check latest version from PyPI with cache
    Returns: (latest_version, error_message)
    """
    cache_file = os.path.join(global_conf.DEFAULT_CACHE_DIR, "latest_version")
    cache_ttl = 60 * 60 * 24  # 1 day
    try:
        if os.path.exists(cache_file) and time.time() - os.path.getmtime(cache_file) < cache_ttl:
            with open(cache_file, 'r', encoding='utf-8') as f:
                return f.read().strip(), None
    except OSError:
        pass

    try:
        response = requests.get(f"https://pypi.org/pypi/{__title__}/json", timeout=1)
        if response.status_code == 200:
            latest_version = response.json()["info"]["version"]
            with open(cache_file, 'w', encoding='utf-8') as f:
                f.write(latest_version)
            return latest_version, None
    except Exception as e:
        return None, f"Failed to check update: {str(e)}"
    return None, "Unable to get version info"

def needs_update(current: str, latest: str) -> bool:
    """Check if update is needed"""
    try:
        return version.parse(latest) > version.parse(current)
    except Exception:
        return False

def get_proxy_settings() -> dict:
    """Get system proxy settings"""
    proxies = {}
    if os.environ.get("http_proxy"):
        proxies["http"] = os.environ["http_proxy"]
    if os.environ.get("https_proxy"):
        proxies["https"] = os.environ["https_proxy"]
    return proxies

def download_file(url: str, target_path: str, executable: bool = False) -> bool:
    """
    Download file and save
    Args:
        url: Download URL
        target_path: Save path
        executable: Set executable permission
    """
    try:
        response = requests.get(url, proxies=get_proxy_settings(), timeout=10)
        response.raise_for_status()
        
        with open(target_path, 'w') as f:
            f.write(response.text)
            
        if executable:
            os.chmod(target_path, 0o755)
            
        return True
    except Exception as e:
        log_error(f"Download failed: {e}")
        return False

def wait_for_process_end(pid: int, timeout: float = 5.0, check_interval: float = 0.1) -> bool:
    """
    Wait for process to end
    Args:
        pid: Process ID
        timeout: Timeout in seconds
        check_interval: Check interval in seconds
    Returns:
        bool: Whether process has ended
    """
    end_time = time.time() + timeout
    while time.time() < end_time:
        try:
            os.kill(pid, 0)  # Check if process exists
            time.sleep(check_interval)
        except ProcessLookupError:
            return True
    return False

def kill_process(
    pid: int,
    force: bool = True,
    timeout: Optional[float] = None,
) -> bool:
    """
    Kill process
    Args:
        pid: Process ID
        force: Force kill if needed
        timeout: Maximum total seconds to wait, or None for the legacy limit
    Returns:
        bool: Whether process was killed
    """
    try:
        deadline = None if timeout is None else time.monotonic() + max(timeout, 0)

        os.kill(pid, signal.SIGTERM)
        term_timeout = 5.0
        if deadline is not None:
            term_timeout = min(term_timeout, max(deadline - time.monotonic(), 0))
        if wait_for_process_end(pid, timeout=term_timeout):
            return True
            
        if force:
            os.kill(pid, signal.SIGKILL)
            kill_timeout = 1.0
            if deadline is not None:
                kill_timeout = min(
                    kill_timeout,
                    max(deadline - time.monotonic(), 0),
                )
            return wait_for_process_end(pid, timeout=kill_timeout)
            
        return False
    except ProcessLookupError:
        return True
    except OSError:
        return False

def check_screen_exists(screen_name: str) -> Optional[bool]:
    """Check if a screen session exists"""
    try:
        result = subprocess.run(
            ['screen', '-ls'],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for line in result.stdout.splitlines():
            parts = line.strip().split()
            if not parts:
                continue
            session_id = parts[0]
            session_name = (
                session_id.split(".", 1)[1]
                if "." in session_id
                else session_id
            )
            if session_name == screen_name:
                return True
        return False
    except (OSError, subprocess.SubprocessError):
        return None

def check_command_injection(input_str: Optional[str]) -> bool:
    """
    Check if the user controlled string is safe from command injection
    
    Args:
        input_str: string to check
    Returns:
        bool: True for insecure, False for secure
    """
    if input_str is None:
        return False

    # Define dangerous characters and patterns
    dangerous_chars = {
        '&',        # command1 & command2
        ';',        # command1; command2
        '|',        # command1 | command2
        '`',        # `command`
        '$',        # $(command) or $VAR
        '(',        # sub command
        ')',        # sub command
        '<',        # redirect
        '>',        # redirect
        '*',        # willcard
        '?',        # willcard
        '\\',       # escape
        '\n',       # break line
        '\r',       # back line
    }
    
    # Check dangerous characters
    if any(char in input_str for char in dangerous_chars):
        return True
        
    return False
