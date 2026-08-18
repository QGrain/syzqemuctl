# Getting started

## Host prerequisites

Install Python 3.8 or newer, QEMU for x86, and GNU Screen. On Debian or Ubuntu,
a typical host setup is:

```bash
sudo apt update
sudo apt install qemu-system-x86 screen
test -r /dev/kvm && test -w /dev/kvm
```

The final command checks whether the current user can access KVM. Configure the
host's KVM permissions before starting a VM if it fails.

## Install the package

```bash
python3 -m pip install --upgrade syzqemuctl
syzqemuctl --version
```

## Initialize an image home

Choose a directory that will contain the downloaded `create-image.sh`, the
template image, and all derived images:

```bash
syzqemuctl init --images-home /home/user/syz-images --wait
```

`--wait` keeps the command attached until template creation finishes. Without
it, template creation runs in a background `screen` session. Inspect progress
with:

```bash
syzqemuctl status image-template
```

The selected image home is stored in
`~/.config/syzqemuctl/settings.json`.

## Create an image

```bash
syzqemuctl create my-image
```

This copies the default ready template. To request a different disk size in
megabytes:

```bash
syzqemuctl create my-image-4096 --size 4096
```

Size-specific templates are cached. Their first creation can continue in the
background, so check `syzqemuctl status my-image-4096` before using the image.

## Start a VM

Pass the directory containing a built Linux kernel tree. The expected kernel
image is `arch/x86/boot/bzImage` below this directory.

```bash
syzqemuctl run my-image --kernel /home/user/linux
syzqemuctl status my-image
```

Wait for the status to become `Running` before using SSH operations. The first
boot can take several minutes depending on the guest and host.

## Execute and copy

```bash
syzqemuctl exec --timeout 30 my-image "uname -a"
syzqemuctl cp --timeout 600 ./poc my-image:/root/poc
syzqemuctl cp --timeout 600 my-image:/root/vm.log ./vm.log
```

The timeout is a total operation limit. Omit it for an operation whose duration
is intentionally unbounded.

## Stop and delete

```bash
syzqemuctl stop my-image --wait --timeout 20
syzqemuctl delete my-image
```

Use `--force` only when normal cleanup cannot remove stale runtime state:

```bash
syzqemuctl stop my-image --wait --force --timeout 20
```
