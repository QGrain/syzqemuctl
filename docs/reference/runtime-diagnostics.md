# Runtime diagnostics

`VM.runtime_diagnostics()` returns a stable, read-only view of runtime resources
owned by one image. It does not disconnect SSH, terminate processes, close
screen sessions, or delete files.

```python
diagnostics = vm.runtime_diagnostics(timeout=5, check_port=True)
print(diagnostics.summary())
record = diagnostics.to_dict()
```

The CLI exposes the same data:

```bash
syzqemuctl diagnose my-image --timeout 5 --json
```

## Fields

| Field | Type | Meaning |
| --- | --- | --- |
| `image_path` | `str` | Canonical image directory. |
| `screen_sessions` | `Optional[List[str]]` | Exact matching session IDs, or `None` when inspection failed. |
| `qemu_pids` | `Optional[List[int]]` | Exact-image QEMU PIDs, or `None` when inspection failed. |
| `pidfile_exists` | `bool` | Whether `vm.pid` exists. |
| `pidfile_pid` | `Optional[int]` | Parsed pidfile value. |
| `pidfile_pid_valid` | `Optional[bool]` | Whether the pidfile PID is an exact-image QEMU process; `None` means unverified. |
| `port` | `Optional[int]` | SSH host-forward port parsed from the saved boot configuration. |
| `port_open` | `Optional[bool]` | Port probe result, or `None` when skipped or unavailable. |
| `port_checked` | `bool` | Whether a port probe was attempted. |
| `log_file_exists` | `bool` | Whether `vm.log` exists. |
| `runtime_clean` | `Optional[bool]` | Clean, dirty, or unknown runtime state. |
| `errors` | `List[str]` | Inspection failures and malformed artifacts. |

The type notation uses `typing.Optional` and `typing.List`, which are available
on Python 3.8.

## Three-state cleanliness

- `True`: all inspected runtime artifacts are absent and the requested port
  check found no open port.
- `False`: at least one known runtime artifact remains, such as a screen
  session, QEMU PID, pidfile, or open saved port.
- `None`: no known dirty artifact was found, but at least one required check
  failed or could not be completed.

Known dirty state takes precedence over unknown checks. For example, an
existing pidfile keeps `runtime_clean=False` even if screen inspection fails.

## Recommended failure record

Persist `to_dict()` output immediately after `start()` or
`cleanup_runtime()` returns `False`. The snapshot is sequential rather than an
atomic host transaction, so collect it close to the failure being analyzed.

Do not infer runtime ownership from image basenames or reconstruct screen names
in external projects. Those rules remain internal to syzqemuctl.
