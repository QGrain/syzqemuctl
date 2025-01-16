# qemuctl

A command-line tool for managing QEMU virtual machines.

## Features

- Easy VM creation and management
- Automated template image creation using syzkaller's create-image.sh
- SSH and file transfer support
- Command execution in VMs
- Screen session management for VM console access

## Installation

```bash
pip install qemuctl
```

## Requirements

- Python 3.8+
- QEMU
- screen
- SSH client

## Usage

1. Initialize qemuctl:
```bash
qemuctl init --images-home /path/to/images
```

2. Create a new VM:
```bash
qemuctl create my-vm
```

3. Run the VM:
```bash
qemuctl run my-vm --kernel /path/to/kernel
```

4. Check VM status:
```bash
qemuctl status my-vm
```

5. Copy files to/from VM:
```bash
qemuctl cp local-file my-vm:/remote/path  # Copy to VM
qemuctl cp my-vm:/remote/file local-path  # Copy from VM
```

6. Execute commands in VM:
```bash
qemuctl exec my-vm "uname -a"
```

7. Stop the VM:
```bash
qemuctl stop my-vm
```

8. List all VMs:
```bash
qemuctl list
```

## Configuration

The configuration file is stored in `~/.config/qemuctl/config.json`. It contains:
- Images home directory path
- Default VM settings

## License

MIT License

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.