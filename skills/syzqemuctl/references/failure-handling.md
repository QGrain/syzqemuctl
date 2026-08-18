# Failure handling

## Classify before retrying

Keep these outcomes separate:

| Outcome | Meaning | Next action |
| --- | --- | --- |
| `TimeoutError` | The configured total I/O limit expired. | Reconnect before more SSH I/O; increase or remove the limit only when expected duration justifies it. |
| `subprocess.CalledProcessError` | The remote command exited non-zero. | Inspect its return code, stdout, and stderr; do not treat it as a transport failure. |
| SSH, SCP, or I/O exception | The transport failed or became unreliable. | Reconnect if the VM still runs; retain the original exception. |
| Lifecycle method returns `False` | Start, stop, cleanup, or deletion did not complete safely. | Collect runtime diagnostics before retrying. |
| Guest crash or boot failure | QEMU may run while the guest is unusable. | Inspect `vm.log` and runtime diagnostics; keep experiment-specific crash classification outside syzqemuctl. |

## Recover after an I/O timeout

Timeout handling aborts and disconnects the underlying SSH transport so a
blocked command or SCP call can be interrupted. Establish a new connection:

```python
try:
    with vm:
        vm.copy_to_vm("large-directory", "/root/data", timeout=1800)
except TimeoutError:
    if vm.is_running() and vm.connect():
        try:
            vm.execute("true", timeout=15, check=True)
        finally:
            vm.disconnect()
    raise
```

Do not reach into `vm._ssh` to change socket timeouts or close its transport.
The copy API uses SCP and has no resume operation. After a transfer timeout,
treat the destination as potentially partial; inspect or remove it before
retrying the complete transfer. Use an external resumable protocol only when
the application explicitly requires it, and do not present that protocol as a
syzqemuctl feature.

## Escalate cleanup

Use this order:

1. Capture `vm.runtime_diagnostics(timeout=5)`.
2. Call `vm.stop(wait=True, timeout=20)`.
3. If stale owned runtime remains, call `vm.cleanup_runtime(timeout=20)`.
4. Capture diagnostics again when cleanup returns `False`.
5. Take manual host action only after validating exact process ownership.

The CLI equivalents are:

```bash
syzqemuctl diagnose case-22 --json
syzqemuctl stop case-22 --wait --timeout 20
syzqemuctl stop case-22 --wait --force --timeout 20
syzqemuctl diagnose case-22 --json
```

Never use broad process-name matching such as `pkill qemu-system-x86_64` on a
host that may run unrelated VMs.

## Interpret runtime cleanliness

- `runtime_clean=True`: inspected runtime resources are absent.
- `runtime_clean=False`: at least one known runtime resource remains.
- `runtime_clean=None`: no dirty resource was confirmed, but one or more checks
  failed; treat the result as unknown.

Known dirty state takes precedence over unknown checks. Review `errors`,
`screen_sessions`, `qemu_pids`, `pidfile_pid_valid`, and `port_open` together.

## Handle refused deletion

`ImageManager.delete()` refuses an image when QEMU is active, image creation is
active, or the relevant runtime state cannot be verified. Stop and diagnose
first. Do not remove the directory manually while QEMU may still write to the
guest disk.
