# syzqemuctl

`syzqemuctl` manages QEMU disk images created with Syzkaller's
`create-image.sh` and starts virtual machines from those images. It provides a
command-line interface for interactive use and a Python API for automation and
agent-driven workflows.

The tool owns the host-side runtime associated with an image:

- template and per-case image directories;
- generated QEMU boot scripts;
- `screen` sessions and QEMU processes;
- host-forwarded SSH ports;
- SSH command execution and SCP transfers;
- cleanup and read-only runtime diagnostics.

## Start here

- Follow [Getting started](getting-started.md) for installation and a first VM.
- Read [Concepts](concepts.md) before automating image and VM lifecycles.
- Use the [CLI reference](reference/cli.md) for shell workflows.
- Use the [Python API reference](reference/python-api.md) for programs and
  agents.
- Consult [Troubleshooting](troubleshooting.md) after start, SSH, transfer, or
  cleanup failures.

## Documentation versions

The site header shows both the package version and, where applicable, the
Read the Docs channel. `stable` follows the latest released version, `latest`
follows the current `main` branch, and a numbered version is a snapshot of its
corresponding release tag. Use `stable` unless you need unreleased changes.

## Supported environment

`syzqemuctl` is a Linux host tool. It requires Python 3.8 or newer, QEMU,
`screen`, and access to KVM for the generated default boot configuration.
Guest images are based on the files produced by the pinned Syzkaller
`create-image.sh` workflow.

!!! note
    The Python compatibility floor applies to the package. The documentation
    build uses a newer Python version independently.
