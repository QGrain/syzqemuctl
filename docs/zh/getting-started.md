# 快速开始

## 宿主机依赖

安装 Python 3.8 或更高版本、x86 QEMU 和 GNU Screen。在 Debian 或 Ubuntu
宿主机上，典型安装方式如下：

```bash
sudo apt update
sudo apt install qemu-system-x86 screen
test -r /dev/kvm && test -w /dev/kvm
```

最后一条命令检查当前用户是否有权访问 KVM。如果检查失败，请先配置宿主机的
KVM 权限，再启动虚拟机。

## 安装软件包

```bash
python3 -m pip install --upgrade syzqemuctl
syzqemuctl --version
```

## 初始化镜像主目录

选择一个目录，用于保存下载的 `create-image.sh`、模板镜像以及所有派生镜像：

```bash
syzqemuctl init --images-home /home/user/syz-images --wait
```

`--wait` 会让命令保持前台运行，直到模板创建完成。不使用该参数时，模板创建会
在后台 `screen` 会话中执行。可使用以下命令查看进度：

```bash
syzqemuctl status image-template
```

选定的镜像主目录保存在 `~/.config/syzqemuctl/settings.json`。

## 创建镜像

```bash
syzqemuctl create my-image
```

该命令复制默认的就绪模板。若要指定其他磁盘大小（MB）：

```bash
syzqemuctl create my-image-4096 --size 4096
```

指定大小的模板会被缓存。第一次创建可能继续在后台运行，因此使用镜像前应检查
`syzqemuctl status my-image-4096`。

## 启动虚拟机

传入已经完成编译的 Linux 内核源码目录。工具期望在该目录下找到
`arch/x86/boot/bzImage`。

```bash
syzqemuctl run my-image --kernel /home/user/linux
syzqemuctl status my-image
```

请等待状态变为 `Running` 后再执行 SSH 操作。根据 Guest 和宿主机性能，首次
启动可能需要数分钟。

## 执行命令和复制文件

```bash
syzqemuctl exec --timeout 30 my-image "uname -a"
syzqemuctl cp --timeout 600 ./poc my-image:/root/poc
syzqemuctl cp --timeout 600 my-image:/root/vm.log ./vm.log
```

timeout 是操作总时长限制。如果操作时长有意不设上限，请省略该参数。

## 停止和删除

```bash
syzqemuctl stop my-image --wait --timeout 20
syzqemuctl delete my-image
```

仅当普通清理无法移除陈旧运行时资源时使用 `--force`：

```bash
syzqemuctl stop my-image --wait --force --timeout 20
```
