# Agent Skill

The repository includes a portable Agent Skill at
[`skills/syzqemuctl`](https://github.com/QGrain/syzqemuctl/tree/main/skills/syzqemuctl).
It gives coding agents a concise workflow for using syzqemuctl's public CLI and
Python API without depending on private SSH, process, or runtime details.

## Contents

```text
skills/syzqemuctl/
|-- SKILL.md
|-- agents/
|   `-- openai.yaml
`-- references/
    |-- failure-handling.md
    `-- workflows.md
```

`SKILL.md` follows the Agent Skills convention: YAML metadata determines when
the skill applies, and the Markdown body provides the core workflow. Detailed
examples and recovery guidance are loaded from `references/` only when needed.
`agents/openai.yaml` supplies optional Codex-facing display metadata.

## Install for Codex

Clone the repository, then link the skill into the active Codex skills
directory:

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
ln -s /path/to/syzqemuctl/skills/syzqemuctl \
  "${CODEX_HOME:-$HOME/.codex}/skills/syzqemuctl"
```

Start a new Codex session after installation so the skill can be discovered.
Use a copy instead of a symbolic link when the agent environment cannot follow
links.

Other agents that support directory-based skills can load the same `SKILL.md`;
place the `syzqemuctl` directory in that agent's configured skill search path.
The `agents/openai.yaml` file is optional outside Codex.

## Typical triggers

The skill is intended for requests such as:

- create an image, boot a kernel, and wait for SSH;
- append a case-specific kernel command-line argument safely;
- run a PoC with explicit command and transfer timeouts;
- recover stale `screen`, pidfile, port, or exact-image QEMU runtime;
- diagnose why start, stop, or deletion did not complete;
- replace external access to `vm._ssh` or private cleanup helpers.

The skill does not install QEMU, create a Linux kernel build, or decide whether
an experiment reproduced a target crash. Those remain host setup and
application-level responsibilities.
