<h1 align="center">
    syzqemuctl
</h1>

<p align="center">A command-line tool for managing QEMU virtual machines created through <a href="https://github.com/google/syzkaller" target="_blank">Syzkaller</a>'s `create-image.sh`.</p>

<p align="center">
<img src="https://img.shields.io/pypi/v/syzqemuctl?label=version" alt="PyPI - Version">
<img src="https://img.shields.io/pypi/dw/syzqemuctl" alt="PyPI - Downloads">
<img src="https://img.shields.io/github/license/QGrain/syzqemuctl" alt="GitHub License">
<img src="https://img.shields.io/codacy/grade/683d9c6a11d2492fbaf59ff069b275f2" alt="Codacy grade">
</p>

## Features

- Easy VM creation and management
- Automated template image creation using syzkaller's create-image.sh
- SSH and file transfer support
- Command execution in VMs
- Screen session management for VM console access

## Change Log

- 0.1.0: 2025-01-16
    - Initial release (BUG: entry_point is wrong)
- 0.1.1: 2025-01-16
    - Update README.md (BUG: entry_point is wrong)
- 0.1.2: 2025-01-17
    - Fix bug of entry point (USABLE!)
- 0.1.3: 2025-01-17
    - Add badges

## Installation

```bash
pip install syzqemuctl
```

## Requirements

```bash
python3.8+ qemu screen ssh  
```

## Configuration

The configuration file is stored in `~/.config/syzqemuctl/config.json`. It contains:
- Images home directory path
- Default VM settings

## Usage

### ⭐ As a command-line tool

1. Initialize syzqemuctl:
```bash
syzqemuctl init --images-home /path/to/images
```

2. Create a new VM:
```bash
syzqemuctl create my-vm
```

3. Run the VM:
```bash
syzqemuctl run my-vm --kernel /path/to/kernel
```

4. Check VM status:
```bash
syzqemuctl status my-vm
```

5. Copy files to/from VM:
```bash
syzqemuctl cp local-file my-vm:/remote/path  # Copy to VM
syzqemuctl cp my-vm:/remote/file local-path  # Copy from VM
```

6. Execute commands in VM:
```bash
syzqemuctl exec my-vm "uname -a"
```

7. Stop the VM:
```bash
syzqemuctl stop my-vm
```

8. List all VMs:
```bash
syzqemuctl list
```

### ⭐ As a Python package

```python
from syzqemuctl import VM, ImageManager, VMConfig

manager = ImageManager("/path/to/images_home")
manager.initialize()
manager.create_image("my-vm")
vm = VM("/path/to/images_home/my-vm")
vm.start(kernel_path="/path/to/kernel")
# Wait several minutes for the VM to be ready
with vm:
    vm.copy_to_vm("/path/to/local/file", "/path/to/vm/remote/file")
    vm.execute("uname -a")
```

## License

Apache-2.0

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.