# Python API reference

The package exports `global_conf`, `ImageManager`, `RuntimeDiagnostics`, `VM`,
and `VMConfig` from `syzqemuctl`.

## Configuration

```python
from syzqemuctl import global_conf

global_conf.initialize(
    "/home/user/syz-images",
    force=False,
    verbose=False,
)
global_conf.load()
print(global_conf.images_home)
```

API mode is quiet by default. Pass `verbose=True` to configuration,
`ImageManager`, or `VM` when informational messages are desired.

## `ImageManager`

```python
manager = ImageManager(images_home, verbose=False)
```

| Method | Result | Purpose |
| --- | --- | --- |
| `initialize(force=False, blocking=False, size=3072)` | `bool` | Download the pinned creation script and create the default template. |
| `create(name, size=None, force=False)` | `bool` | Create a persistent image. |
| `is_image_ready(name)` | `bool` | Test the ready marker. |
| `get_image_info(name)` | `Optional[ImageInfo]` | Return image, creation, and runtime metadata. |
| `list_images()` | `List[ImageInfo]` | List managed images. |
| `delete(name)` | `bool` | Delete a stopped, verified image. |

The result notation uses `typing.Optional` and `typing.List`, which are
available on Python 3.8.

## `VM.start`

```python
started = vm.start(
    kernel=None,
    port=None,
    mem=None,
    smp=None,
    snapshot=False,
    kernel_args=None,
    extra_kernel_args=None,
)
```

The method returns `True` after QEMU has produced a valid owned pidfile, not
after SSH becomes available. Call `wait_until_ready()` separately.

When omitted, kernel, memory, CPU count, and kernel arguments are reused from
the last boot configuration where supported. An available saved SSH port is
preferred; otherwise a port in the host range 20000-29999 is selected.

## Runtime state

| Method | Result | Purpose |
| --- | --- | --- |
| `get_last_vm_config()` | `Optional[VMConfig]` | Parse the generated boot script. |
| `is_running()` | `bool` | Find an exact-image QEMU process. |
| `is_ready()` | `bool` | Perform one SSH readiness probe. |
| `wait_until_ready(timeout=120, interval=3)` | `bool` | Poll SSH readiness. |
| `stop(wait=False, timeout=20, force=False)` | `bool` | Request cleanup and optionally wait. |
| `cleanup_runtime(timeout=20)` | `bool` | Force cleanup and wait. |
| `runtime_diagnostics(timeout=5, check_port=True)` | `RuntimeDiagnostics` | Return a read-only snapshot. |

## SSH connection and I/O

```python
if not vm.connect(username="root"):
    raise ConnectionError("SSH connection failed")
try:
    stdout, stderr = vm.execute("uname -a", timeout=30, check=True)
    vm.copy_to_vm("./input", "/root/input", timeout=600)
    vm.copy_from_vm("/root/output", "./output", timeout=600)
finally:
    vm.disconnect()
```

Prefer the equivalent context-manager form:

```python
with vm:
    stdout, stderr = vm.execute("uname -a", timeout=30, check=True)
```

`execute()` and copy timeouts default to `None`. A configured timeout limits
the total operation duration and aborts the SSH transport when it expires. A
subsequent operation requires a new `connect()`.

`execute(check=True)` raises `subprocess.CalledProcessError` for a non-zero
remote exit. SSH/SCP I/O failures can also disconnect a transport whose health
can no longer be confirmed.
