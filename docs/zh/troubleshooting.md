# 故障排查

## 模板创建长时间未完成

检查其状态和创建 screen：

```bash
syzqemuctl status image-template
screen -ls
```

检查 QEMU 镜像创建依赖、可用磁盘空间、访问固定版本 Syzkaller 脚本的网络连接，
以及配置的镜像主目录权限。仅在确认未完成模板可以重建后，才重新执行
`init --force --wait`。

## `run` 报告虚拟机已经运行

进程匹配器发现 QEMU 引用了该镜像准确的 `bullseye.img` 路径。清理前先检查：

```bash
syzqemuctl diagnose my-image --json
syzqemuctl stop my-image --wait --force --timeout 20
```

不要仅根据部分路径或镜像 basename 终止进程。

## QEMU 已启动但 SSH 未就绪

检查串口日志和运行时状态：

```bash
tail -n 200 /path/to/images/my-image/vm.log
syzqemuctl diagnose my-image
```

常见原因包括 Guest 内核 panic、不兼容的内核命令行、缺少 root 设备、KVM 或
CPU 不兼容，以及 Guest 内部 SSH 启动失败。任务有特殊启动要求时应使用
`--extra-kernel-args`，不要在外部修改 `boot.sh`。

## 执行或复制操作超时

timeout 限制操作总时长。正常的长命令或大规模传输需要更大的值，也可以不设置
timeout。超时后 transport 会被主动中止，因此需要重新连接：

```python
try:
    vm.copy_to_vm("large-directory", "/root/data", timeout=1800)
except TimeoutError:
    if vm.is_running() and vm.connect():
        # The new connection is usable for a retry or status check.
        vm.disconnect()
    raise
```

对于长时间运行的工作负载，可通过一条有较短时限的命令在后台启动它，再单独
轮询状态。

## 清理返回 `False`

再次尝试清理前先采集诊断：

```python
if not vm.cleanup_runtime(timeout=20):
    diagnostics = vm.runtime_diagnostics(timeout=5)
    print(diagnostics.summary())
```

开放的已保存端口可能属于复用了该端口的无关进程。执行宿主机级操作前，应比较
`screen_sessions`、`qemu_pids` 和 `pidfile_pid_valid`。

## 删除操作拒绝镜像

虚拟机仍在运行、镜像创建仍在进行或 screen 状态无法验证时，删除会被阻止。
先停止并诊断虚拟机。QEMU 可能仍在写入磁盘时，不要直接删除镜像目录。

## 收集有效的问题报告

提交 issue 时请包含：

```bash
syzqemuctl --version
python3 --version
qemu-system-x86_64 --version
syzqemuctl diagnose my-image --json
tail -n 200 /path/to/images/my-image/vm.log
```

公开输出前，请移除不应披露的本地路径或 Guest 数据。
