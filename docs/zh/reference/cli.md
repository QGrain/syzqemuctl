# CLI 参考

使用 `syzqemuctl COMMAND --help` 查看已安装版本提供的选项。命令失败时返回
非零进程状态。

## 全局命令

```text
syzqemuctl [--version] COMMAND [ARGS]
```

`--version` 输出已安装版本，并检查 PyPI 是否存在更新版本。

## 镜像命令

### `init`

```text
syzqemuctl init --images-home PATH [--force] [--wait] [--size MB]
```

初始化配置并创建默认模板。默认大小为 3072 MB。`--wait` 会在前台执行模板
创建。

### `create`

```text
syzqemuctl create NAME [--size MB] [--force]
```

从默认模板或指定大小的模板创建镜像。指定自定义大小时，`--force` 会绕过缓存，
从头创建目标镜像。

### `list` 和 `status`

```text
syzqemuctl list
syzqemuctl status NAME
```

列出受管镜像，或者查看一个镜像的创建状态和虚拟机状态。

### `delete`

```text
syzqemuctl delete NAME
```

删除已经停止的镜像。如果虚拟机或镜像创建运行时仍处于活动状态，或者其状态
无法验证，命令会拒绝删除。

## 虚拟机生命周期命令

### `run`

```text
syzqemuctl run NAME [--kernel PATH] [--port PORT] [--mem SIZE] [--smp N]
                       [--snapshot] [--kernel-args TEXT]
                       [--extra-kernel-args TEXT]
```

首次启动必须提供内核路径，后续启动会从上一次启动脚本复用该路径。
`--kernel-args` 替换完整 Guest 命令行；`--extra-kernel-args` 追加到已保存值
或默认值。

### `stop`

```text
syzqemuctl stop NAME [--wait] [--force] [--timeout SECONDS]
```

`--wait` 会轮询到运行时资源消失。`--force` 还会处理准确匹配镜像的孤立 QEMU
进程。默认等待 timeout 为 20 秒，并且只在使用 `--wait` 时生效。

### `restart`

```text
syzqemuctl restart NAME
```

停止正在运行的虚拟机，并使用已保存的启动配置重新启动。快照模式不会被继承。

## Guest I/O 命令

### `exec`

```text
syzqemuctl exec [--timeout SECONDS] NAME "COMMAND"
```

通过 SSH 执行命令。远端命令以非零状态退出时，CLI 将其视为失败，并输出捕获的
stdout 和 stderr。

### `cp`

```text
syzqemuctl cp [--timeout SECONDS] LOCAL_PATH NAME:REMOTE_PATH
syzqemuctl cp [--timeout SECONDS] NAME:REMOTE_PATH LOCAL_PATH
```

在宿主机和一台虚拟机之间递归复制文件或目录。不支持虚拟机之间直接复制。

## 诊断

```text
syzqemuctl diagnose NAME [--timeout SECONDS] [--no-check-port] [--json]
```

检查运行时状态而不修改它。`--json` 适用于脚本和智能体。字段含义参见
[运行时诊断](runtime-diagnostics.md)。
