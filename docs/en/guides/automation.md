# Automation

## Prefer the Python API for orchestration

Use the CLI for interactive commands and shell pipelines. Use the Python API
when a runner needs typed results, exception handling, retries, or structured
runtime diagnostics.

```python
import subprocess

from syzqemuctl import VM

vm = VM("/home/user/syz-images/case-10")
if not vm.start(kernel="/home/user/linux"):
    raise RuntimeError(vm.runtime_diagnostics().summary())

try:
    if not vm.wait_until_ready(timeout=180):
        raise RuntimeError("VM did not become SSH-ready")
    with vm:
        vm.copy_to_vm("./poc", "/root/poc", timeout=600)
        stdout, stderr = vm.execute(
            "chmod +x /root/poc && /root/poc",
            timeout=120,
            check=True,
        )
except TimeoutError:
    # A hard timeout disconnects the current SSH transport.
    if vm.is_running() and vm.connect():
        vm.disconnect()
    raise
except subprocess.CalledProcessError as error:
    print(error.returncode, error.output, error.stderr)
    raise
finally:
    if not vm.cleanup_runtime(timeout=20):
        print(vm.runtime_diagnostics().to_dict())
```

## Choose timeout values by operation

The I/O timeout is a total wall-clock limit, not an inactivity timeout:

- use 15-60 seconds for short control commands;
- use a larger value for large files or directories;
- use `None` when the operation duration is intentionally unbounded;
- start long-running guest workloads in the background and poll their state.

For example:

```python
with vm:
    vm.execute(
        "nohup /root/poc >/root/poc.log 2>&1 &",
        timeout=30,
        check=True,
    )
```

After `execute()` or copy raises `TimeoutError`, the underlying transport has
been aborted. Call `connect()` again before the next SSH operation.

## Keep concurrency image-scoped

Start, stop, and delete operations for one image are serialized across host
processes. Parallel workers should use distinct image directories so their
guest disks, ports, pidfiles, and logs remain independent.

## Preserve domain-specific failure classification

`syzqemuctl` reports transport and runtime facts. An experiment runner should
retain its own meanings for guest crashes, target-crash matching, boot stages,
and result aggregation. Do not collapse all of these conditions into a timeout:

- `TimeoutError`: the configured total I/O limit expired;
- SSH, SCP, or I/O exception: the transport failed;
- `subprocess.CalledProcessError`: the remote command exited non-zero;
- `False` from lifecycle APIs: inspect runtime diagnostics before retrying.

Never access `vm._ssh` to impose timeouts or close sockets. The public I/O APIs
perform hard interruption and connection cleanup.
