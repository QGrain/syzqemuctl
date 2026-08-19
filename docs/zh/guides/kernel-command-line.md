# 内核命令行

`VM.start()` 支持在运行时替换或扩展 Guest 内核命令行，因此外部项目无需修改
自动生成的 `boot.sh`。

## 追加任务特定参数

需要保留普通默认参数时，使用 `extra_kernel_args`：

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

附加字符串会追加到已保存的命令行；首次启动时则追加到内置默认值。

## 替换完整命令行

仅当调用方负责提供完整 Guest 命令行时使用 `kernel_args`：

```python
vm.start(
    kernel="/home/user/linux",
    kernel_args=(
        "root=/dev/sda console=ttyS0 net.ifnames=0 "
        "earlyprintk=serial"
    ),
)
```

生成启动脚本时，工具会将完整 `-append` 值进行 Shell 引用，并作为一个 QEMU
参数传入。不要预先引用 Python 值；应提供 Guest 内核实际需要接收的文本。

## 优先级和持久化

有效命令行按以下顺序选择：

1. 显式传入的 `kernel_args`；
2. 从上一次 `boot.sh` 解析出的命令行；
3. 首次启动时使用 `VMConfig.DEFAULT_KERNEL_ARGS`；
4. 如果提供了 `extra_kernel_args`，将其追加到选定值。

最终结果写入新生成的 `boot.sh`，供后续启动复用。如需移除之前持久化的任务
特定参数，请传入新的 `kernel_args`。

!!! warning "警告"
    不要在虚拟机启动期间修改 `boot.sh`。应使用公开的启动参数，确保配置解析和
    重启行为保持一致。
