import requests
from packaging import version
from typing import Optional, Tuple
from functools import lru_cache
import os
import signal
import time
import subprocess

from ._version import __version__, __title__
from .config import global_conf

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
    except:
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
    except:
        return False

def get_proxy_settings() -> dict:
    """Get system proxy settings"""
    proxies = {}
    if os.environ.get("http_proxy"):
        proxies["http"] = os.environ["http_proxy"]
    if os.environ.get("https_proxy"):
        proxies["https"] = os.environ["https_proxy"]
    return proxies

def download_file(url: str, target_path: str, executable: bool = False) -> None:
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
        print(f"Download failed: {e}")
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

def kill_process(pid: int, force: bool = True) -> bool:
    """
    Kill process
    Args:
        pid: Process ID
        force: Force kill if needed
    Returns:
        bool: Whether process was killed
    """
    try:
        os.kill(pid, signal.SIGTERM)
        if wait_for_process_end(pid, timeout=5.0):
            return True
            
        if force:
            os.kill(pid, signal.SIGKILL)
            return wait_for_process_end(pid, timeout=1.0)
            
        return False
    except ProcessLookupError:
        return True
    except OSError:
        return False

def check_screen_exists(screen_name: str) -> bool:
    """Check if a screen session exists"""
    try:
        result = subprocess.run(['screen', '-ls'], capture_output=True, text=True)
        return screen_name in result.stdout
    except subprocess.SubprocessError:
        return False

def check_command_injection(input_str: str) -> bool:
    """
    Check if the user controlled string is safe from command injection
    
    Args:
        input_str: string to check
    Returns:
        bool: True for insecure, False for secure
    """
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