# 虚拟机生命周期

## 创建并验证镜像

镜像主目录只需初始化一次。对于每个需要独立持久磁盘状态的工作负载，分别创建
一个镜像：

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

`initialize()` 和指定自定义大小的 `create()` 可能异步执行。在
`is_image_ready()` 返回 `True` 之前不要启动虚拟机。

## 启动并等待 SSH

```python
from syzqemuctl import VM

vm = VM("/home/user/syz-images/case-22")
if not vm.start(kernel="/home/user/linux"):
    raise RuntimeError(vm.runtime_diagnostics().summary())
if not vm.wait_until_ready(timeout=180, interval=3):
    raise RuntimeError(vm.runtime_diagnostics().summary())
```

启动前，`start()` 会对镜像所属的陈旧运行时执行非强制清理。如果已有匹配的
QEMU 进程在运行，它会拒绝启动。

## 安全使用 SSH

上下文管理器会建立一个 SSH 连接，并在退出时始终断开：

```python
with vm:
    vm.copy_to_vm("./poc", "/root/poc", timeout=600)
    stdout, stderr = vm.execute(
        "chmod +x /root/poc && /root/poc",
        timeout=120,
        check=True,
    )
```

远端命令以非零状态退出时，`check=True` 会抛出
`subprocess.CalledProcessError`。未启用该参数时不会返回退出状态，但仍可通过
`(stdout, stderr)` 获取输出。

## 停止并等待收敛

```python
if not vm.stop(wait=True, timeout=20):
    diagnostics = vm.runtime_diagnostics(timeout=5)
    print(diagnostics.summary())
```

普通停止只处理经过验证的 pidfile 进程和准确匹配的 screen 会话。在启动失败后
恢复，或者复用镜像之前，可以请求强清理：

```python
if not vm.cleanup_runtime(timeout=20):
    raise RuntimeError(vm.runtime_diagnostics().summary())
```

`cleanup_runtime()` 等价于 `stop(wait=True, force=True, timeout=timeout)`。
强制清理还会终止命令行中引用准确镜像路径的孤立 QEMU 进程。

## 仅删除已停止的镜像

```python
if not manager.delete("case-22"):
    raise RuntimeError("image is running, being created, or cannot be verified")
```

当虚拟机仍在运行或存在镜像创建 screen 会话时，删除操作会被拒绝。无法验证
运行时状态时同样不会继续删除。
