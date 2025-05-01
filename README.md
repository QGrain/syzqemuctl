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

> See details in Usage section    :)

## Change Log

Each version without `BUG` tag is usable.

<details>
<summary>v0.1.0 ~ v0.1.10</summary>
- 0.1.0: 2025-01-16
    - Initial release (BUG: entry_point is wrong)
- 0.1.1: 2025-01-16
    - Update README.md (BUG: entry_point is wrong)
- 0.1.2: 2025-01-17
    - Fix bug of entry point (**CLI USABLE NOW!**)
- 0.1.3: 2025-01-17
    - Add badges
- 0.1.4: 2025-01-20
    - Fix the inconsistencies of README and code (**API USABLE NOW!**)
- 0.1.5: 2025-01-21
    - Complete vm.wait_until_ready and update README
- 0.1.6: 2025-01-21
    - Update version info and try to solve the installation dependency problem
- 0.1.7: 2025-01-21
    - Fix the installation dependency problem
- 0.1.8: 2025-01-22
    - Add smart option --version and move some functions to utils.py
- 0.1.9: 2025-01-22
    - Add safe_decode in execute in vm.py
- 0.1.10: 2025-01-22
    - Use the kernel in last vm config to start vm by default
</details>

<details>
<summary>v0.2.0 ~ progressing</summary>
- 0.2.0: 2025-04-25
    - Add user friendly instruction for running image and update email
- 0.2.1: 2025-04-26
    - Add documentation for copy dirs from local to vm
- 0.2.2: 2025-04-27
    - Add restart for vm and update README
- 0.2.3: 2025-04-27
    - Set default image size of image-template to 5GB and support --size for creating vm (BUG: size it doesn't work)
- 0.2.4: 2025-04-27
    - Fix a missing file in creating vm with specified size and optimize printing
- 0.2.5: 2025-05-01
    - Add security check for command injection
</details>

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

### ⭐ As a command-line tool (CLI)

You can check the usage of `syzqemuctl` or `syzqemuctl CMD` by adding `--help`. Here are some common uses:

1. Initialize syzqemuctl:
```bash
syzqemuctl init --images-home /path/to/images
```

2. Create a new VM:
```bash
syzqemuctl create my-vm [--size 5120]   # --size INT for specifying the VM disk size (5GB by default)
```

3. Run the VM:
```bash
syzqemuctl run my-vm --kernel /path/to/kernel
```

4. Check VM status:
```bash
syzqemuctl status my-vm
```

5. Copy files/dir to/from VM:
```bash
syzqemuctl cp local_file my-vm:/remote/path  # Copy to VM
syzqemuctl cp my-vm:/remote/file local_path  # Copy from VM

syzqemuctl cp local_dir my-vm:/remote/       # Copy local_dir to VM
syzqemuctl cp local_dir/ my-vm:/remote/      # Copy local_dir/* to VM

```

6. Execute commands in VM:
```bash
syzqemuctl exec my-vm "uname -a" # You'd better wrap the command with double quotes
```

7. Stop the VM:
```bash
syzqemuctl stop my-vm
```

8. Restart the VM:
```bash
syzqemuctl restart my-vm
```

9. List all VMs:
```bash
syzqemuctl list
```

10. Delete the VM:
```bash
syzqemuctl delete my-vm
```

### ⭐ As a Python package (API)

```python
from syzqemuctl import ImageManager, VM

manager = ImageManager("/path/to/images_home")
manager.initialize()
manager.create("my-vm")

# Or just direct specify a created VM and
vm = VM("/path/to/images_home/my-vm")
vm.start(kernel="/path/to/kernel")

# Wait several minutes for the VM to be ready, or you can check by:
if vm.is_ready():
    pass

# Or use this API to wait:
if vm.wait_until_ready(timeout=180, interval=60):
    pass

# You need to use this context manager to auto-connect/disconnect
with vm:
    vm.copy_to_vm("/path/to/local/file", "/path/to/vm/remote/file")
    stdout, stderr = vm.execute("uname -a")
    print(f"stdout: {stdout}\nstderr: {stderr}")
```

## License

Apache-2.0

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.