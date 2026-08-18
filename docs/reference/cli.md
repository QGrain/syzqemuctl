# CLI reference

Run `syzqemuctl COMMAND --help` for the options installed with your package.
Command failures return a non-zero process status.

## Global command

```text
syzqemuctl [--version] COMMAND [ARGS]
```

`--version` prints the installed version and checks PyPI for a newer release.

## Image commands

### `init`

```text
syzqemuctl init --images-home PATH [--force] [--wait] [--size MB]
```

Initialize configuration and create the default template. The default size is
3072 MB. `--wait` performs template creation in the foreground.

### `create`

```text
syzqemuctl create NAME [--size MB] [--force]
```

Create an image from the default or size-specific template. With a custom size,
`--force` bypasses the cache and creates the target from scratch.

### `list` and `status`

```text
syzqemuctl list
syzqemuctl status NAME
```

List managed images or inspect one image's creation and VM status.

### `delete`

```text
syzqemuctl delete NAME
```

Delete a stopped image. The command refuses active or unverifiable VM and
creation runtime.

## VM lifecycle commands

### `run`

```text
syzqemuctl run NAME [--kernel PATH] [--port PORT] [--mem SIZE] [--smp N]
                       [--snapshot] [--kernel-args TEXT]
                       [--extra-kernel-args TEXT]
```

The kernel path is required on first boot and reused from the last boot script
thereafter. `--kernel-args` replaces the complete guest command line;
`--extra-kernel-args` appends to the saved or default value.

### `stop`

```text
syzqemuctl stop NAME [--wait] [--force] [--timeout SECONDS]
```

`--wait` polls until runtime artifacts disappear. `--force` additionally
targets exact-image orphan QEMU processes. The default wait timeout is 20
seconds and matters only with `--wait`.

### `restart`

```text
syzqemuctl restart NAME
```

Stop a running VM and start it with the saved boot configuration. Snapshot mode
is not inherited.

## Guest I/O commands

### `exec`

```text
syzqemuctl exec [--timeout SECONDS] NAME "COMMAND"
```

Execute a command through SSH. The CLI treats a non-zero remote exit status as
a failure and prints captured stdout and stderr.

### `cp`

```text
syzqemuctl cp [--timeout SECONDS] LOCAL_PATH NAME:REMOTE_PATH
syzqemuctl cp [--timeout SECONDS] NAME:REMOTE_PATH LOCAL_PATH
```

Copy files or directories recursively between the host and one VM. Direct
VM-to-VM copies are not supported.

## Diagnostics

```text
syzqemuctl diagnose NAME [--timeout SECONDS] [--no-check-port] [--json]
```

Inspect runtime state without modifying it. `--json` is intended for scripts
and agents. See [Runtime diagnostics](runtime-diagnostics.md) for field
semantics.
