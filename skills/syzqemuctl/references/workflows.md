# Workflows

## CLI lifecycle

Initialize an image home and wait for the default template:

```bash
syzqemuctl init --images-home /home/user/syz-images --wait
```

Create, start, inspect, use, and stop one image:

```bash
syzqemuctl create case-22
syzqemuctl run case-22 \
  --kernel /home/user/linux \
  --extra-kernel-args "systemd.unified_cgroup_hierarchy=0"
syzqemuctl status case-22
syzqemuctl exec --timeout 30 case-22 "uname -a"
syzqemuctl cp --timeout 600 ./poc case-22:/root/poc
syzqemuctl stop case-22 --wait --timeout 20
```

Copy from the guest by placing the VM endpoint first:

```bash
syzqemuctl cp --timeout 600 case-22:/root/vm.log ./vm.log
```

Use `--snapshot` when guest disk writes must be discarded. Snapshot mode is not
inherited by later starts or restarts.

## Python lifecycle

```python
from syzqemuctl import ImageManager, VM, global_conf

images_home = "/home/user/syz-images"
global_conf.initialize(images_home, force=False)

manager = ImageManager(images_home)
manager.initialize(blocking=True)
if not manager.create("case-22"):
    raise RuntimeError("image creation failed")
if not manager.is_image_ready("case-22"):
    raise RuntimeError("image is not ready")

vm = VM(f"{images_home}/case-22")
if not vm.start(
    kernel="/home/user/linux",
    extra_kernel_args="systemd.unified_cgroup_hierarchy=0",
):
    raise RuntimeError(vm.runtime_diagnostics().summary())

try:
    if not vm.wait_until_ready(timeout=180, interval=3):
        raise RuntimeError(vm.runtime_diagnostics().summary())
    with vm:
        vm.copy_to_vm("./poc", "/root/poc", timeout=600)
        stdout, stderr = vm.execute(
            "chmod +x /root/poc && /root/poc",
            timeout=120,
            check=True,
        )
finally:
    if not vm.stop(wait=True, timeout=20):
        print(vm.runtime_diagnostics().to_dict())
```

For a multi-gigabyte copy, select a total timeout from measured transfer time
with sufficient margin, or pass `timeout=None` when no library-level deadline
is wanted. SCP does not resume a partial transfer.

`execute()` returns `(stdout, stderr)`. With `check=True`, a non-zero remote
exit status raises `subprocess.CalledProcessError` and preserves captured
output.

## Background guest workload

Keep the SSH control operation bounded while allowing the workload to run:

```python
with vm:
    vm.execute(
        "nohup /root/poc >/root/poc.log 2>&1 &",
        timeout=30,
        check=True,
    )
```

Poll with later bounded commands. Do not use a short foreground timeout for a
workload expected to run for minutes.

## Runtime inspection

Use JSON from a shell workflow:

```bash
syzqemuctl diagnose case-22 --timeout 5 --json
```

Use structured values from Python:

```python
diagnostics = vm.runtime_diagnostics(timeout=5, check_port=True)
print(diagnostics.runtime_clean)
print(diagnostics.errors)
record = diagnostics.to_dict()
```
