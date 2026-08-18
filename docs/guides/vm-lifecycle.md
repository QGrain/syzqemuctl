# VM lifecycle

## Create and validate an image

Initialize the image home once, then create a separate image for each workload
that needs independent persistent disk state:

```python
from syzqemuctl import ImageManager, global_conf

images_home = "/home/user/syz-images"
global_conf.initialize(images_home, force=False)

manager = ImageManager(images_home)
manager.initialize(blocking=True)
if not manager.create("case-22"):
    raise RuntimeError("image creation failed")
if not manager.is_image_ready("case-22"):
    raise RuntimeError("image is not ready")
```

`initialize()` and custom-size `create()` can be asynchronous. Do not start a
VM until `is_image_ready()` returns `True`.

## Start and wait for SSH

```python
from syzqemuctl import VM

vm = VM("/home/user/syz-images/case-22")
if not vm.start(kernel="/home/user/linux"):
    raise RuntimeError(vm.runtime_diagnostics().summary())
if not vm.wait_until_ready(timeout=180, interval=3):
    raise RuntimeError(vm.runtime_diagnostics().summary())
```

Before launch, `start()` performs non-forced cleanup of stale runtime owned by
the image. It refuses to start if a matching QEMU process is already running.

## Use SSH safely

The context manager opens one SSH connection and always disconnects on exit:

```python
with vm:
    vm.copy_to_vm("./poc", "/root/poc", timeout=600)
    stdout, stderr = vm.execute(
        "chmod +x /root/poc && /root/poc",
        timeout=120,
        check=True,
    )
```

`check=True` raises `subprocess.CalledProcessError` for a non-zero remote exit
status. Without it, the exit status is not returned and output is still
available as `(stdout, stderr)`.

## Stop and converge

```python
if not vm.stop(wait=True, timeout=20):
    diagnostics = vm.runtime_diagnostics(timeout=5)
    print(diagnostics.summary())
```

Normal stop targets the validated pidfile process and the exact screen session.
For recovery after a failed start or before reusing an image, request strong
cleanup:

```python
if not vm.cleanup_runtime(timeout=20):
    raise RuntimeError(vm.runtime_diagnostics().summary())
```

`cleanup_runtime()` is equivalent to
`stop(wait=True, force=True, timeout=timeout)`. Forced cleanup additionally
terminates orphan QEMU processes whose command line references the exact image.

## Delete only stopped images

```python
if not manager.delete("case-22"):
    raise RuntimeError("image is running, being created, or cannot be verified")
```

Deletion refuses active VM and image-creation screen sessions. It also refuses
to proceed when the runtime state cannot be verified.
