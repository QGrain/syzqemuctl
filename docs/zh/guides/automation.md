# 自动化

## 编排任务优先使用 Python API

CLI 适合交互命令和 Shell 管道。当 runner 需要类型明确的结果、异常处理、重试
或结构化运行时诊断时，应使用 Python API。

```python
import subprocess

from syzqemuctl import VM

vm = VM("/home/user/syz-images/case-10")
if not vm.start(kernel="/home/user/linux"):
    raise RuntimeError(vm.runtime_diagnostics().summary())

try:
    if not vm.wait_until_ready(timeout=180):
        raise RuntimeError("VM did not become SSH-ready")
    with vm:
        vm.copy_to_vm("./poc", "/root/poc", timeout=600)
        stdout, stderr = vm.execute(
            "chmod +x /root/poc && /root/poc",
            timeout=120,
            check=True,
        )
except TimeoutError:
    # A hard timeout disconnects the current SSH transport.
    if vm.is_running() and vm.connect():
        vm.disconnect()
    raise
except subprocess.CalledProcessError as error:
    print(error.returncode, error.output, error.stderr)
    raise
finally:
    if not vm.cleanup_runtime(timeout=20):
        print(vm.runtime_diagnostics().to_dict())
```

## 按操作类型选择 timeout

I/O timeout 是总墙上时钟限制，不是无响应时间限制：

- 短控制命令可使用 15 至 60 秒；
- 大文件或目录应使用更大的值；
- 有意不限制操作时长时使用 `None`；
- 长时间运行的 Guest 工作负载应在后台启动，再轮询其状态。

例如：

```python
with vm:
    vm.execute(
        "nohup /root/poc >/root/poc.log 2>&1 &",
        timeout=30,
        check=True,
    )
```

`execute()` 或复制操作抛出 `TimeoutError` 后，底层 transport 已被中止。下一次
SSH 操作前应再次调用 `connect()`。

## 并发范围限制在镜像级

同一镜像的 start、stop 和 delete 操作会在不同宿主机进程之间串行执行。并行
worker 应使用不同镜像目录，使 Guest 磁盘、端口、pidfile 和日志相互独立。

## 保留应用领域的失败分类

`syzqemuctl` 报告传输和运行时事实。实验 runner 应保留自己对 Guest 崩溃、
目标崩溃匹配、启动阶段和结果聚合的定义，不应将所有情况都归为 timeout：

- `TimeoutError`：配置的 I/O 总时长限制已到期；
- SSH、SCP 或 I/O 异常：传输失败；
- `subprocess.CalledProcessError`：远端命令以非零状态退出；
- 生命周期 API 返回 `False`：重试前应检查运行时诊断。

不要通过 `vm._ssh` 设置 timeout 或关闭 socket。公开 I/O API 已负责硬中断和
连接清理。
