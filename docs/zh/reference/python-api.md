# Python API 参考

软件包从 `syzqemuctl` 导出 `global_conf`、`ImageManager`、
`RuntimeDiagnostics`、`VM` 和 `VMConfig`。

## 配置

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

API 模式默认保持安静。需要输出信息时，可向配置、`ImageManager` 或 `VM` 传入
`verbose=True`。

## `ImageManager`

```python
manager = ImageManager(images_home, verbose=False)
```

| 方法 | 结果 | 用途 |
| --- | --- | --- |
| `initialize(force=False, blocking=False, size=3072)` | `bool` | 下载固定版本的创建脚本并创建默认模板。 |
| `create(name, size=None, force=False)` | `bool` | 创建持久镜像。 |
| `is_image_ready(name)` | `bool` | 检查就绪标记。 |
| `get_image_info(name)` | `Optional[ImageInfo]` | 返回镜像、创建过程和运行时元数据。 |
| `list_images()` | `List[ImageInfo]` | 列出受管镜像。 |
| `delete(name)` | `bool` | 删除已停止且状态经过验证的镜像。 |

结果类型使用 Python 3.8 可用的 `typing.Optional` 和 `typing.List` 表示。

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

该方法会在 QEMU 生成有效且归属于当前镜像的 pidfile 后返回 `True`，而不是等到
SSH 就绪。之后应单独调用 `wait_until_ready()`。

省略参数时，会尽可能复用上一次启动配置中的内核、内存、CPU 数量和内核参数。
工具优先使用可用的已保存 SSH 端口，否则从宿主机 20000 至 29999 范围内选择
端口。

## 运行时状态

| 方法 | 结果 | 用途 |
| --- | --- | --- |
| `get_last_vm_config()` | `Optional[VMConfig]` | 解析生成的启动脚本。 |
| `is_running()` | `bool` | 查找准确匹配镜像的 QEMU 进程。 |
| `is_ready()` | `bool` | 执行一次 SSH 就绪探测。 |
| `wait_until_ready(timeout=120, interval=3)` | `bool` | 轮询 SSH 就绪状态。 |
| `stop(wait=False, timeout=20, force=False)` | `bool` | 请求清理，并可选择等待完成。 |
| `cleanup_runtime(timeout=20)` | `bool` | 强制清理并等待完成。 |
| `runtime_diagnostics(timeout=5, check_port=True)` | `RuntimeDiagnostics` | 返回只读快照。 |

## SSH 连接和 I/O

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

也可以使用等价的上下文管理器形式：

```python
with vm:
    stdout, stderr = vm.execute("uname -a", timeout=30, check=True)
```

`execute()` 和复制操作的 timeout 默认为 `None`。设置后，它会限制操作总时长，
并在到期时中止 SSH transport。后续操作需要重新 `connect()`。

远端命令以非零状态退出时，`execute(check=True)` 会抛出
`subprocess.CalledProcessError`。SSH/SCP I/O 失败也可能断开无法确认健康状态的
transport。
