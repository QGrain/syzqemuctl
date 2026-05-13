<h1 align="center">
    syzqemuctl
</h1>

<p align="center">A command-line tool for managing QEMU disk images and virtual machines created through <a href="https://github.com/google/syzkaller" target="_blank">Syzkaller</a>'s `create-image.sh`.</p>

<p align="center">
<img src="https://img.shields.io/pypi/v/syzqemuctl?label=version" alt="PyPI - Version">
<img src="https://img.shields.io/pypi/dm/syzqemuctl" alt="PyPI - Downloads">
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
<summary>v0.2.0 ~ v0.2.9</summary>

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
- 0.2.6: 2025-05-12
    - Add blocking mode for init command
- 0.2.7: 2025-05-14
    - Improve API usage
- 0.2.8: 2026-05-05
    - Fix a vm booting bug caused by the cpu inconsistency by adding params in boot_script
- 0.2.9: 2026-05-11
      - Suppress paramiko SSH noise and expose `set_paramiko_logging()` for log control
      - Reduce `wait_until_ready()` default polling interval to 3s and remove redundant `is_ready()` checks
      - Improve `stop()` cleanup (screen session, stale pidfile) and fix return semantics
      - Fix bare `except:` clauses in `start()` and `utils.py`, remove noisy prints from `is_ready()`
</details>

<details open>
<summary>v0.3.0 ~ progressing</summary>

- 0.3.0: 2026-05-12
      - Reduce default template size from 5120MB to 3072MB and add `--size` to `init`
      - Add template-size cache (`image-template-SIZE`) for faster `create` with custom sizes
      - Add `--force` to `create` to bypass cache and create from scratch
      - Add `is_image_ready()` API and `.image_ready` flag for monitoring image creation
      - Distinguish image vs VM concepts in README and unify examples to `my-image`
- 0.3.1: 2026-05-13
      - Add `--snapshot` flag to `run` for ephemeral VM sessions (changes discarded on shutdown)
      - Snapshot flag is not inherited from previous boots; specify it explicitly when needed
</details open>

<details>
<summary>TODOs</summary>

- Merge global_conf into ImageManager

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

## Concepts

- **Image**: A QEMU disk image (e.g., `bullseye.img`) created by `create-image.sh`. Images are stored as directories under `IMAGES_HOME`.
- **VM**: A running QEMU virtual machine booted from an image with a specified kernel. A VM shares the same name as its underlying image directory.

## Usage

### ⭐ As a command-line tool (CLI)

You can check the usage of `syzqemuctl` or `syzqemuctl CMD` by adding `--help`. Here are some common uses:

1. Initialize syzqemuctl:
```bash
syzqemuctl init --images-home /path/to/images
```

2. Create a new disk image:
```bash
syzqemuctl create my-image [--size 3072]   # --size INT for specifying a custom disk size in MB (copies from default template if omitted)
```

3. Run a VM from the image:
```bash
syzqemuctl run my-image --kernel /path/to/kernel
```

   Run with snapshot mode (all disk changes discarded on shutdown):
```bash
syzqemuctl run my-image --kernel /path/to/kernel --snapshot
```

4. Check image/VM status:
```bash
syzqemuctl status my-image
```

5. Copy files/dir to/from VM:
```bash
syzqemuctl cp local_file my-image:/remote/path  # Copy to VM
syzqemuctl cp my-image:/remote/file local_path  # Copy from VM

syzqemuctl cp local_dir my-image:/remote/       # Copy local_dir to VM
syzqemuctl cp local_dir/ my-image:/remote/      # Copy local_dir/* to VM

```

6. Execute commands in VM:
```bash
syzqemuctl exec my-image "uname -a" # You'd better wrap the command with double quotes
```

7. Stop the VM:
```bash
syzqemuctl stop my-image
```

8. Restart the VM:
```bash
syzqemuctl restart my-image
```

9. List all images:
```bash
syzqemuctl list
```

10. Delete the image:
```bash
syzqemuctl delete my-image
```

### ⭐ As a Python package (API)

```python
from syzqemuctl import global_conf, ImageManager, VM

images_home = "/path/to/images_home"
global_conf.initialize(images_home, force=False) # This could be skipped if you have run `syzqemuctl init --images-home=IMAGES_HOME` in CLI
manager = ImageManager(images_home)
manager.initialize(force=False)
manager.create("my-image")

# Or just direct specify a created image and run a VM from it
vm = VM("/path/to/images_home/my-image")
vm.start(kernel="/path/to/kernel")

# Wait several minutes for the VM to be ready, or you can check by:
if vm.is_ready():
    pass

# Or use this API to wait:
if vm.wait_until_ready(timeout=180):
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