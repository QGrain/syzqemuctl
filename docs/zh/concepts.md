# 核心概念

## 镜像主目录

镜像主目录是所有受管镜像的父目录。CLI 从
`~/.config/syzqemuctl/settings.json` 读取该路径；Python API 也可以直接使用
一个路径构造 `ImageManager`。

## 模板和镜像

一个**镜像**是至少包含 Syzkaller 生成的 Guest 磁盘和 SSH 密钥材料的目录：

```text
my-image/
├── bullseye.img
├── bullseye.id_rsa
├── bullseye.id_rsa.pub
└── .image_ready
```

`image-template` 是 `ImageManager.create()` 默认复制的源模板。名为
`image-template-SIZE` 的目录用于缓存自定义磁盘大小的模板。

镜像是持久化的。启动或停止虚拟机通常不会删除镜像目录。

## 虚拟机运行时

**VM** 是从一个镜像启动的宿主机运行时。`VM.start()` 会在镜像目录中添加：

- `boot.sh`：生成的 QEMU 命令和最近一次启动配置；
- `vm.pid`：运行时存在期间由 QEMU 写入的 pidfile；
- `vm.log`：通过 `tee` 写入的串口控制台输出。

QEMU 进程运行在与镜像路径绑定的 `screen` 会话中。screen 名称属于实现细节；
应使用 `VM.screen_name`、`status` 或 `runtime_diagnostics()`，不要在外部重新
构造该名称。

## 已保存的启动配置

`boot.sh` 记录最近一次启动所使用的内核路径、SSH 端口、内存、CPU 数量和
Guest 内核命令行。后续 `start()` 或 CLI `restart` 可以复用这些配置。

快照模式不会被自动继承。每次需要丢弃磁盘改动时，都应显式传入
`snapshot=True` 或 `--snapshot`。

## 资源归属和锁

运行时进程匹配要求 QEMU 命令行引用准确的 `bullseye.img` 路径。start、stop
和 delete 操作通过镜像级宿主机锁串行执行，不同镜像仍可并行运行。

不要访问 `_qemu_pids_for_image()` 等私有方法或 `_ssh` 属性。公开的生命周期、
I/O、清理和诊断 API 才是受支持的集成接口。
