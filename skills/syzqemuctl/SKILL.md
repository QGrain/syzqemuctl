---
name: syzqemuctl
description: Manage Syzkaller QEMU images and virtual machines with syzqemuctl. Use when an agent needs to install or configure syzqemuctl, create or delete images, start or stop QEMU guests, set kernel command-line arguments, execute SSH commands, copy files, enforce I/O timeouts, recover stale runtime, inspect diagnostics, or integrate the public Python API into automation and PoC reproduction workflows.
---

# syzqemuctl

Manage one Syzkaller-style disk image and its QEMU runtime as a single ownership
unit. Prefer syzqemuctl's public lifecycle, I/O, cleanup, and diagnostics APIs
over host-specific process, `screen`, socket, or SSH handling.

## Establish context

1. Confirm the host is Linux and has Python 3.8+, `qemu-system-x86_64`, GNU
   Screen, and usable KVM access.
2. Check `syzqemuctl --version`. Install or upgrade with
   `python3 -m pip install --upgrade syzqemuctl` when needed.
3. Identify the image home, image name, Linux kernel build directory, and
   whether persistent guest disk changes are required.
4. Inspect current state before changing it. Use `syzqemuctl status NAME` for a
   quick check or `syzqemuctl diagnose NAME --json` for machine-readable facts.

## Select the interface

- Use the CLI for interactive work, shell scripts, and isolated operations.
- Use the Python API for orchestration that needs typed results, exception
  handling, retries, context-managed SSH, or structured diagnostics.
- Use only documented public methods. Never access `vm._ssh`, reconstruct
  private screen names, call underscore-prefixed helpers, or edit `boot.sh`
  while a VM is starting.
- When producing an implementation, show concrete syzqemuctl CLI commands or
  public Python calls first. Use `VM.execute()` for guest shell commands and
  `copy_to_vm()` or `copy_from_vm()` for SCP transfers; do not replace the
  requested integration with unrelated raw SSH tooling.

Read [references/workflows.md](references/workflows.md) before generating or
modifying CLI or Python orchestration code.

## Follow the lifecycle

1. Initialize the image home once and wait until its template is ready.
2. Create a separate image for each persistent workload.
3. Start the VM, then wait for SSH readiness; successful `start()` does not
   imply that SSH is ready.
4. Connect before `execute()` or copy operations. Prefer `with vm:` in Python.
5. Stop with waiting when later work depends on complete cleanup.
6. Delete only after runtime and image-creation activity have stopped.

Use `extra_kernel_args` or `--extra-kernel-args` to append case-specific boot
arguments. Use `kernel_args` or `--kernel-args` only when replacing the complete
guest command line. Pass unquoted argument text to the Python API; syzqemuctl
quotes generated shell commands.

## Bound operations deliberately

Treat `execute()` and copy timeouts as total wall-clock limits, not inactivity
timeouts. Choose them per workload:

- use a short limit for control commands;
- allow enough time for large transfers;
- use `None` or omit the CLI option when duration is intentionally unbounded;
- launch a long-running guest workload in the background, then poll its state.

A timeout hard-aborts the SSH transport. Reconnect before another I/O
operation. Keep command failure (`subprocess.CalledProcessError`), transport
failure, timeout, guest crash, and target-crash classification distinct.

syzqemuctl's copy methods use recursive SCP. They do not provide resumable
transfers or progress checkpoints. A timeout can leave a partial destination;
inspect or remove it before retrying the complete copy. Do not claim that the
library resumes a transfer automatically.

## Recover conservatively

Collect `runtime_diagnostics()` or `diagnose --json` before destructive
recovery. Try normal `stop(wait=True)` first. Use `cleanup_runtime()` or
`stop --wait --force` for failed starts and verified stale runtime. Forced
cleanup targets QEMU processes whose command line references the exact image;
do not replace it with broad `pkill`, basename matching, or manual pidfile
deletion.

Do not use `force=True` as the routine finalizer for a healthy VM. First call
`stop(wait=True)`, capture diagnostics if it returns `False`, and only then
escalate to forced cleanup when stale owned runtime must be removed.

Read [references/failure-handling.md](references/failure-handling.md) when an
operation times out, cleanup returns `False`, deletion is refused, or runtime
state is unknown.

## Verify outcomes

- Re-run `status` or `diagnose` after lifecycle changes.
- Treat `runtime_clean=None` as unknown, not clean.
- Preserve diagnostic JSON with experiment results when start or cleanup fails.
- Report the installed syzqemuctl version, QEMU version, diagnostics, and the
  tail of `vm.log` when escalating a reproducible failure.
