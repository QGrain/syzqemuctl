# syzqemuctl

`syzqemuctl` 用于管理由 Syzkaller `create-image.sh` 创建的 QEMU 磁盘镜像，
并从这些镜像启动虚拟机。它既提供面向交互操作的命令行接口，也提供适用于
自动化程序和智能体工作流的 Python API。

该工具管理与镜像关联的宿主机运行时资源：

- 模板镜像目录和各任务的镜像目录；
- 自动生成的 QEMU 启动脚本；
- `screen` 会话和 QEMU 进程；
- SSH 宿主机转发端口；
- SSH 命令执行和 SCP 文件传输；
- 运行时清理和只读诊断。

## 从这里开始

- 按照[快速开始](getting-started.md)安装工具并启动第一台虚拟机。
- 在自动化镜像和虚拟机生命周期之前阅读[核心概念](concepts.md)。
- 在 Shell 工作流中查阅 [CLI 参考](reference/cli.md)。
- 在程序和智能体中查阅 [Python API 参考](reference/python-api.md)。
- 启动、SSH、传输或清理失败时查阅[故障排查](troubleshooting.md)。

## 支持环境

`syzqemuctl` 是 Linux 宿主机工具，需要 Python 3.8 或更高版本、QEMU、
`screen`，默认启动配置还需要 KVM 访问权限。Guest 镜像基于项目固定版本的
Syzkaller `create-image.sh` 工作流所生成的文件。

!!! note "说明"
    Python 最低版本要求适用于软件包本身。文档构建独立使用更高版本的 Python。
