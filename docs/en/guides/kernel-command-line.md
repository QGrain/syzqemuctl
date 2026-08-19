# Kernel command line

`VM.start()` supports replacing or extending the guest kernel command line at
runtime. This avoids editing generated `boot.sh` files from another project.

## Append case-specific arguments

Use `extra_kernel_args` when the normal defaults should remain in place:

=== "CLI"

    ```bash
    syzqemuctl run case-22 \
      --kernel /home/user/linux \
      --extra-kernel-args "systemd.unified_cgroup_hierarchy=0"
    ```

=== "Python"

    ```python
    vm.start(
        kernel="/home/user/linux",
        extra_kernel_args="systemd.unified_cgroup_hierarchy=0",
    )
    ```

The extra string is appended to the saved command line, or to the built-in
default on first boot.

## Replace the complete command line

Use `kernel_args` only when the caller owns the complete guest command line:

```python
vm.start(
    kernel="/home/user/linux",
    kernel_args=(
        "root=/dev/sda console=ttyS0 net.ifnames=0 "
        "earlyprintk=serial"
    ),
)
```

The generated boot script shell-quotes the complete `-append` value as one QEMU
argument. Do not pre-quote the Python value; provide the exact text the guest
kernel should receive.

## Precedence and persistence

The effective command line is selected in this order:

1. explicit `kernel_args`;
2. the command line parsed from the last `boot.sh`;
3. `VMConfig.DEFAULT_KERNEL_ARGS` on first boot;
4. `extra_kernel_args`, when provided, is appended to the selected value.

The effective result is stored in the newly generated `boot.sh` and reused by
later starts. Pass a new `kernel_args` value to remove previously persisted
case-specific arguments.

!!! warning
    Do not monkey-patch `boot.sh` while a VM is starting. Use the public start
    arguments so configuration parsing and restart behavior remain consistent.
