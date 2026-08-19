# Troubleshooting

## Template creation does not finish

Check its status and creation screen:

```bash
syzqemuctl status image-template
screen -ls
```

Verify QEMU image-creation dependencies, free disk space, network access to the
pinned Syzkaller script, and permissions on the configured image home. Re-run
`init --force --wait` only after deciding that the incomplete template can be
recreated.

## `run` reports that the VM is already running

The process matcher found QEMU referencing the image's exact `bullseye.img`.
Inspect it before cleanup:

```bash
syzqemuctl diagnose my-image --json
syzqemuctl stop my-image --wait --force --timeout 20
```

Do not kill a process based only on a partial path or image basename.

## QEMU starts but SSH does not become ready

Inspect the serial log and runtime state:

```bash
tail -n 200 /path/to/images/my-image/vm.log
syzqemuctl diagnose my-image
```

Typical causes include a guest kernel panic, incompatible kernel command line,
missing root device, KVM or CPU incompatibility, and SSH startup failure inside
the guest. Use `--extra-kernel-args` for case-specific boot requirements instead
of editing `boot.sh` externally.

## Execute or copy times out

The timeout is the total operation duration. A legitimate long command or large
transfer needs a larger value or no timeout. After a timeout, reconnect because
the transport was deliberately aborted:

```python
try:
    vm.copy_to_vm("large-directory", "/root/data", timeout=1800)
except TimeoutError:
    if vm.is_running() and vm.connect():
        # The new connection is usable for a retry or status check.
        vm.disconnect()
    raise
```

For a long-running workload, start it in the background with a short bounded
command and poll its status separately.

## Cleanup returns `False`

Collect diagnostics before another cleanup attempt:

```python
if not vm.cleanup_runtime(timeout=20):
    diagnostics = vm.runtime_diagnostics(timeout=5)
    print(diagnostics.summary())
```

An open saved port may belong to an unrelated process that reused the port.
Compare `screen_sessions`, `qemu_pids`, and `pidfile_pid_valid` before taking
host-level action.

## Delete refuses an image

Deletion is blocked when the VM is running, image creation is active, or a
screen state cannot be verified. Stop and diagnose the VM first. Do not remove
the directory directly while QEMU may still be writing to its disk.

## Collecting a useful report

Include these items in an issue:

```bash
syzqemuctl --version
python3 --version
qemu-system-x86_64 --version
syzqemuctl diagnose my-image --json
tail -n 200 /path/to/images/my-image/vm.log
```

Remove local paths or guest data that should not be disclosed before posting
the output publicly.
